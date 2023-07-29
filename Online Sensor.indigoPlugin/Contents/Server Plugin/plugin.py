#! /usr/bin/env python
# -*- coding: utf-8 -*-
###############################################################################
# http://www.indigodomo.com

###############################################################################
#
# Speedtest code from:
#
# https://github.com/sivel/speedtest-cli
#
###############################################################################

import indigo
import threading
import queue
import time
import subprocess
import re
import socket
from urllib.parse import urlparse
from random import shuffle

try:
    from shlex import quote as cmd_quote
except ImportError:
    from pipes import quote as cmd_quote

SPEEDTEST_INSTALLED = False
try:
    import speedtest
    SPEEDTEST_INSTALLED = True
except:
    indigo.server.log("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!", isError=True)
    indigo.server.log("speedtest library must now be manually installed from terminal:", isError=True)
    indigo.server.log("    pip3 install speedtest-cli", isError=True)
    indigo.server.log("(can be ignored if you don't have any speedtest devices configured)")
    indigo.server.log("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!", isError=True)

###############################################################################
# these are used to create sample devices,
# and also to update existing devices when plugin changes.

defaultProps = {
    'onlineSensor': {
        'checkServer1':     "8.8.8.8",          # google dns
        'checkServer2':     "8.8.4.4",          # google dns
        'checkServer3':     "208.67.222.222",   # opneDNS
        'checkServer4':     "208.67.220.220",   # opneDNS
        'checkServer5':     "209.244.0.3",      # level3
        'checkServer6':     "209.244.0.4",      # level3
        'checkServer7':     "37.235.1.174",     # freeDNS
        'checkServer8':     "37.235.1.177",     # freeDNS
        'updateFrequency':  "300",
        'sensorLogic':      "ANY",
        'address':          "8.8.8.8",
        },
    'lanPing': {
        'checkServer1':     "127.0.0.1",        # localhost
        'updateFrequency':  "10",
        'address':          "127.0.0.1",
        },
    'publicIP': {
        'ipEchoService':    "http://ipecho.net/plain",
        'updateFrequency':  "900",
        'address':          "ipecho.net",
        },
    'lookupIP': {
        'domainName':       "localhost",
        'updateFrequency':  "900",
        'address':          "localhost",
        },
    'speedtest': {
        'testSelection':    "BOTH",
        'threshold_str':    "10.0",
        'threshold_float':  10.0,
        'distanceUnit':     "mi",
        'updateFrequency':  "21600",
        'address':          "speedtest.net",
        'shareResults':     False,
        },
    }

serverFields = ['checkServer1','checkServer2','checkServer3','checkServer4',
                'checkServer5','checkServer6','checkServer7','checkServer8']

kAutomaticUpdate = False
kRequestedUpdate = True
kStrftimeFormat = '%Y-%m-%d %H:%M:%S'

################################################################################
class Plugin(indigo.PluginBase):
    #-------------------------------------------------------------------------------
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        global PLUGIN_DEBUG, ALWAYS_UPDATE, SPEEDTEST_LOCK
        PLUGIN_DEBUG = self.debug = self.pluginPrefs.get('showDebugInfo',False)
        ALWAYS_UPDATE = self.pluginPrefs.get('alwaysUpdate',False)
        SPEEDTEST_LOCK = threading.Lock()

        self.deviceDict = dict()

    def __del__(self):
        indigo.PluginBase.__del__(self)

    #-------------------------------------------------------------------------------
    # Start, Stop and Config changes
    #-------------------------------------------------------------------------------
    def startup(self):
        self.logger.debug(f"startup v{self.pluginVersion}")
        if self.debug:
            self.logger.debug(u'Debug logging enabled')

    #-------------------------------------------------------------------------------
    def shutdown(self):
        self.logger.debug(u'shutdown')
        self.pluginPrefs['showDebugInfo'] = self.debug
        self.pluginPrefs['alwaysUpdate'] = ALWAYS_UPDATE

    #-------------------------------------------------------------------------------
    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.logger.debug(u'closedPrefsConfigUi')
        global PLUGIN_DEBUG, ALWAYS_UPDATE
        if not userCancelled:
            PLUGIN_DEBUG = self.debug = valuesDict.get('showDebugInfo',False)
            ALWAYS_UPDATE = valuesDict.get('alwaysUpdate',False)
            if self.debug:
                self.logger.debug(u'Debug logging enabled')

    #-------------------------------------------------------------------------------
    def runConcurrentThread(self):
        try:
            while True:
                loopTime = time.time()
                for devId, device in self.deviceDict.items():
                    device.loopAction(loopTime)

                self.sleep(loopTime+1-time.time())

        except self.StopThread:
            pass    # Optionally catch the StopThread exception and do any needed cleanup.

    #-------------------------------------------------------------------------------
    # Device Methods
    #-------------------------------------------------------------------------------
    def deviceStartComm(self, device):
        self.logger.debug(f"deviceStartComm: {device.name}")
        if device.version != self.pluginVersion:
            self.updateDeviceVersion(device)

        if device.configured:
            device.setErrorStateOnServer(None)
            try:
                if device.deviceTypeId == 'onlineSensor':
                    self.deviceDict[device.id] = OnlineSensorDevice(device, self.logger)
                elif device.deviceTypeId == 'lanPing':
                    self.deviceDict[device.id] = LanPingDevice(device, self.logger)
                elif device.deviceTypeId == 'publicIP':
                    self.deviceDict[device.id] = PublicIpDevice(device, self.logger)
                elif device.deviceTypeId == 'lookupIP':
                    self.deviceDict[device.id] = LookupIpDevice(device, self.logger)
                elif device.deviceTypeId == 'speedtest':
                    self.deviceDict[device.id] = SpeedtestDevice(device, self.logger)
                # start the thread
                self.deviceDict[device.id].start()
            except Exception as e:
                msg = f"'{device.name}' start error: {e}"
                if PLUGIN_DEBUG:
                    self.logger.exception(msg)
                else:
                    self.logger.error(msg)
                self.deviceDict[device.id].cancel()
                device.setErrorStateOnServer('error')

    #-------------------------------------------------------------------------------
    def deviceStopComm(self, device):
        self.logger.debug(f"deviceStopComm: {device.name}")
        if device.id in self.deviceDict:
            self.deviceDict[device.id].cancel()
            del self.deviceDict[device.id]

    #-------------------------------------------------------------------------------
    def validateDeviceConfigUi(self, valuesDict, typeId, devId, runtime=False):
        self.logger.debug(f"validateDeviceConfigUi: {typeId}")
        errorsDict = indigo.Dict()

        # ONLINE SENSOR
        if typeId == 'onlineSensor':
            address = ""
            i = 0
            for key in serverFields:
                value = valuesDict.get(key,"")
                if value:
                    if not any([is_valid_hostname(value),is_valid_ipv4_address(value),is_valid_ipv6_address(value)]):
                        errorsDict[key] = "Not valid IP or host name"
                    if not address:
                        address = value
                    else:
                        i += 1
            if i:
                address += f" (+{i})"
            valuesDict['address'] = address

        # LAN PING
        if typeId == 'lanPing':
            value = valuesDict['checkServer1']
            if not any([is_valid_ipv4_address(value),is_valid_ipv6_address(value)]):
                errorsDict['checkServer1'] = "Not valid IP addess"
            valuesDict['address'] = valuesDict['checkServer1']

        # PUBLIC IP
        elif typeId == 'publicIP':
            if not is_valid_url(valuesDict.get("ipEchoService")):
                errorsDict['ipEchoService'] = "Not a valid URL"
            valuesDict['address'] = f"{urlparse(valuesDict['ipEchoService']).netloc}"

        # LOOKUP IP
        elif typeId == 'lookupIP':
            if not is_valid_hostname(valuesDict.get('domainName')):
                errorsDict['domainName'] = "Not a valid domain"
            valuesDict['address'] = valuesDict['domainName']

        # SPEEDTEST
        elif typeId == 'speedtest':
            try:
                valuesDict['threshold_float'] = float(valuesDict.get('threshold_str',0.))
                if valuesDict['threshold_float'] < 0:
                    raise ValueError("negative value")
            except:
                errorsDict['threshold_str'] = "Must be a positive real number (or zero)."
            valuesDict['address'] = "speedtest.net"

        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        else:
            return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def updateDeviceVersion(self, device):
        self.logger.debug(f"updateDeviceVersion: {device.name}")
        # update states
        device.stateListOrDisplayStateIdChanged()

        # add new props
        theProps = device.pluginProps
        for key, value in defaultProps[device.deviceTypeId].items():
            if (key not in serverFields) and ((key not in theProps) or not theProps[key]):
                theProps[key] = value

        # update frequency from minutes to seconds
        if ver(theProps.get('version',"0.0.0")) < ver("0.0.9"):
            theProps['updateFrequency'] = str(zint(theProps['updateFrequency']) * 60)

        # delete obsolete props
        for key in theProps:
            if (key not in defaultProps[device.deviceTypeId]):
                del theProps[key]

        # push to server
        theProps['version'] = self.pluginVersion
        device.replacePluginPropsOnServer(theProps)

    #-------------------------------------------------------------------------------
    # Menu Methods
    #-------------------------------------------------------------------------------
    def createSampleDevice(self, valuesDict, typeId):
        self.logger.debug(f"createSampleDevice: {valuesDict['deviceName']}'")
        errorsDict = indigo.Dict()

        theName = valuesDict.get('deviceName',"")
        if not theName:
            errorsDict['deviceName'] = "Required"
        elif theName in indigo.devices:
            errorsDict['deviceName'] = "A device with that name already exists"

        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        else:
            indigo.device.create(
                protocol     = indigo.kProtocol.Plugin,
                name         = theName,
                description  = "",
                deviceTypeId = typeId,
                props        = defaultProps[typeId],
                )
            return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def toggleDebug(self):
        global PLUGIN_DEBUG
        if self.debug:
            self.logger.debug(u'Debug logging disabled')
            PLUGIN_DEBUG = self.debug = False
        else:
            PLUGIN_DEBUG = self.debug = True
            self.logger.debug(u'Debug logging enabled')

    #-------------------------------------------------------------------------------
    # Action Methods
    #-------------------------------------------------------------------------------
    def actionControlSensor(self, action, device):
        self.logger.debug(f"actionControlSensor: {device.name}")
        self.deviceDict[device.id].actionControl(action)

###############################################################################
# Classes
###############################################################################
class SensorBase(threading.Thread):

    #-------------------------------------------------------------------------------
    def __init__(self, device, logger):
        super(SensorBase, self).__init__()
        self.daemon     = True
        self.cancelled  = False
        self.queue      = queue.Queue()

        self.logger     = logger

        self.device     = device
        self.id         = device.id
        self.name       = device.name
        self.onState    = device.onState
        self.props      = device.pluginProps
        self.onFreq     = zint(self.props['updateFrequency'])
        if self.props.get('dualFrequency',False):
            self.offFreq = zint(self.props['updateFrequency2'])
        else:
            self.offFreq = self.onFreq

        self.newStates  = list()
        self.updateType = kAutomaticUpdate

        self.checkTime(time.mktime(device.lastChanged.timetuple()))

    #-------------------------------------------------------------------------------
    def run(self):
        self.logger.debug(f"Thread started: {self.name}")
        while not self.cancelled:
            try:
                self.updateType = self.queue.get(True,2)
                self.checkTime()
                self.getDeviceStates()
                self.logOnOff()
                self.saveDeviceStates()
                self.queue.task_done()
            except queue.Empty:
                pass
            except Exception as e:
                msg = f"{self.name}' thread error: {e}"
                if PLUGIN_DEBUG:
                    self.logger.exception(msg)
                else:
                    self.logger.error(msg)
                self.device.setErrorStateOnServer('error')
                self.cancelled = True
        else:
            self.logger.debug(f"Thread cancelled: {self.name}")

    #-------------------------------------------------------------------------------
    def cancel(self):
        """End this thread"""
        self.cancelled = True

    #-------------------------------------------------------------------------------
    def loopAction(self, loopTime):
        if self.onState and self.onFreq:
            if self.lastcheck + self.onFreq < loopTime:
                self.queue.put(kAutomaticUpdate)
        elif (not self.onState) and self.offFreq:
            if self.lastcheck + self.offFreq < loopTime:
                self.queue.put(kAutomaticUpdate)

    #-------------------------------------------------------------------------------
    def actionControl(self, action):
        if action.sensorAction == indigo.kUniversalAction.RequestStatus:
            self.logger.info(f"'{self.name}' status request")
            self.queue.put(kRequestedUpdate)
        # UNKNOWN
        else:
            self.logger.error(f"'{self.name}' {action.sensorAction} request ignored")

    #-------------------------------------------------------------------------------
    def saveDeviceStates(self):
        if len(self.newStates) > 0:
            if PLUGIN_DEBUG: # don't fill up plugin log unless actively debugging
                self.logger.debug(f"updating states on device '{self.name}:")
                for item in self.newStates:
                    self.logger.debug(f"{item['key']:>16}: {item['value']}")
            self.device.updateStatesOnServer(self.newStates)
            self.newStates = list()
        elif (self.updateType or ALWAYS_UPDATE):
            self.device.updateStateOnServer(key='onOffState', value=self.onState)
            self.logger.debug(f"{'onOffState':>16}: {self.device.states['onOffState']}")

    #-------------------------------------------------------------------------------
    def logOnOff(self):
        if self.onState != self.device.onState:
            self.logger.info(f"'{self.name}' {['off','on'][self.onState]}")

    #-------------------------------------------------------------------------------
    def checkTime(self, t=None):
        if not t: t = time.time()
        self.lastcheck = t
        self.timestamp = time.strftime(kStrftimeFormat,time.localtime(t))

    #-------------------------------------------------------------------------------
    def setStateValue(self, key, value):
        self.newStates.append({'key':key, 'value':value})

    #-------------------------------------------------------------------------------
    # abstract methods
    #-------------------------------------------------------------------------------
    def getDeviceStates(self):
        raise NotImplementedError


###############################################################################
class OnlineSensorDevice(SensorBase):

    #-------------------------------------------------------------------------------
    def __init__(self, device, logger):
        super(OnlineSensorDevice, self).__init__(device, logger)
        self.logic   = self.props.get('sensorLogic',"ANY")
        self.servers = [self.props.get(key) for key in serverFields]

    #-------------------------------------------------------------------------------
    def getDeviceStates(self):
        if self.logic == "ANY":
            shuffle(self.servers)
            self.onState = any(do_ping(server) for server in self.servers)
        else:
            self.onState = all(do_ping(server) for server in self.servers)
        if self.onState != self.device.onState:
            self.setStateValue(['lastDn','lastUp'][self.onState], self.timestamp)
            self.setStateValue('onOffState', self.onState)

###############################################################################
class LanPingDevice(SensorBase):

    #-------------------------------------------------------------------------------
    def __init__(self, device, logger):
        super(LanPingDevice, self).__init__(device, logger)
        self.server  = self.props.get('checkServer1','127.0.0.1')
        self.onPersist = int(self.props.get('persistCycles','1'))
        if self.props.get('dualFrequency',False):
            self.offPersist = int(self.props['persistCycles2'])
        else:
            self.offPersist = self.onPersist
        self.count   = 0

    #-------------------------------------------------------------------------------
    def getDeviceStates(self):
        pingResult = do_ping(self.server)
        if pingResult != self.device.onState:
            self.count += 1
            if self.count >= [self.offPersist, self.onPersist][self.device.onState]:
                self.onState = pingResult
                self.setStateValue(['lastDn','lastUp'][self.onState], self.timestamp)
                self.setStateValue('onOffState', self.onState)
        else:
            self.count = 0

###############################################################################
class IpBaseDevice(SensorBase):

    #-------------------------------------------------------------------------------
    def __init__(self, device, logger):
        super(IpBaseDevice, self).__init__(device, logger)

    #-------------------------------------------------------------------------------
    def ipUpdate(self, ipAddress):
        self.onState = bool(ipAddress)
        ipAddressUi  = ["not available",ipAddress][self.onState]
        if self.onState != self.device.onState:
            self.setStateValue('onOffState', self.onState)
        if self.onState and ipAddress != self.device.states['ipAddress']:
                self.logger.info(f"'{self.name}' new IP Address: {ipAddress}")
                self.setStateValue('ipAddress', ipAddress)
                self.setStateValue('lastChange', self.timestamp)
        if self.device.states['ipAddressUi'] != ipAddressUi:
            self.setStateValue('ipAddressUi', ipAddressUi)

###############################################################################
class PublicIpDevice(IpBaseDevice):

    #-------------------------------------------------------------------------------
    def __init__(self, device, logger):
        super(PublicIpDevice, self).__init__(device, logger)

    #-------------------------------------------------------------------------------
    def getDeviceStates(self):
        ipAddress = get_host_IP_address(self.props['ipEchoService'])
        self.ipUpdate(ipAddress)

###############################################################################
class LookupIpDevice(IpBaseDevice):

    #-------------------------------------------------------------------------------
    def __init__(self, device, logger):
        super(LookupIpDevice, self).__init__(device, logger)

    #-------------------------------------------------------------------------------
    def getDeviceStates(self):
        ipAddress = lookup_IP_address(self.props['domainName'])
        self.ipUpdate(ipAddress)

###############################################################################
class SpeedtestDevice(SensorBase):

    #-------------------------------------------------------------------------------
    def __init__(self, device, logger):
        super(SpeedtestDevice, self).__init__(device, logger)
        self.tests = self.props['testSelection']
        self.unit = self.props.get('distanceUnit','')
        self.threshold = self.props.get('threshold_float',0.)
        self.share = self.props.get('shareResults',False)

    #-------------------------------------------------------------------------------
    def getDeviceStates(self):
        # global lock so only one speedtest device may update at a time
        if SPEEDTEST_INSTALLED:
            if SPEEDTEST_LOCK.acquire(False):
                self.logger.debug(f"performSpeedtest: {self.name}")
                try:
                    s = speedtest.Speedtest()
                    self.logger.debug(u'  ...get best server...')
                    s.get_best_server()
                    if self.tests in ('DOWN','BOTH'):
                        self.logger.debug(u'  ...download...')
                        s.download()
                    if self.tests in ('UP','BOTH'):
                        self.logger.debug(u'  ...upload...')
                        s.upload()
                    if self.share:
                        self.logger.debug(u'  ...sharing...')
                        s.results.share()
                    self.logger.debug(u'  ...results...')
                    r = s.results

                    dnld = r.download/1024./1024.
                    upld = r.upload/1024./1024.
                    isOn = any(val > self.threshold for val in [dnld,upld])

                    ping = r.ping
                    dist = r.server.get('d',0.)
                    lat  = float(r.server.get('lat',0.))
                    lon  = float(r.server.get('lon',0.))

                    self.newStates = [
                        {'key':'onOffState',         'value':isOn  },
                        {'key':'Mbps_download',      'value':dnld,       'uiValue':f'{dnld:.2f} Mbps',        'decimalPlaces':2 },
                        {'key':'Mbps_upload',        'value':upld,       'uiValue':f'{upld:.2f} Mbps',        'decimalPlaces':2 },
                        {'key':'ping_latency',       'value':ping,       'uiValue':f'{ping:.2f} ms',          'decimalPlaces':2 },
                        {'key':'server_distance',    'value':dist,       'uiValue':f'{dist:.2f} {self.unit}', 'decimalPlaces':2 },
                        {'key':'raw_download',       'value':r.download, 'uiValue':f'{r.download} bps' },
                        {'key':'raw_upload',         'value':r.upload,   'uiValue':f'{r.upload} bps'   },
                        {'key':'server_latitude',    'value':lat,        'uiValue':f'{lat}°'           },
                        {'key':'server_longitude',   'value':lon,        'uiValue':f'{lon}°'           },
                        {'key':'bytes_received',     'value':r.bytes_received           },
                        {'key':'bytes_sent',         'value':r.bytes_sent               },
                        {'key':'timestamp',          'value':r.timestamp                },
                        {'key':'server_id',          'value':zint(r.server.get('id',0)) },
                        {'key':'server_name',        'value':r.server.get('name','')    },
                        {'key':'server_country',     'value':r.server.get('country','') },
                        {'key':'server_countrycode', 'value':r.server.get('cc','')      },
                        {'key':'server_url1',        'value':r.server.get('url','')     },
                        {'key':'server_url2',        'value':r.server.get('url2','')    },
                        {'key':'server_host',        'value':r.server.get('host','')    },
                        {'key':'server_sponsor',     'value':r.server.get('sponsor','') },
                        {'key':'share_link',         'value':r.share()                  },
                    ]
                    self.onState = isOn

                except Exception as e:
                    self.logger.error(e.message)
                    self.newStates = [ {'key':'onOffState','value':False} ]
                    self.onState = False

                finally:
                    self.logger.debug(f"performSpeedtest: {time.time()-self.lastcheck} seconds")
                    SPEEDTEST_LOCK.release()
            else:
                self.logger.error(u'Unable to acquire lock')
        else:
            self.logger.error("Speetest library not installed")

###############################################################################
# Utilities
###############################################################################

kPingCmd    = "/sbin/ping -c1 -t1 {}".format
kCurlCmd    = "curl -m 15 -s {} | egrep -o '{}'".format
kIpPattern  = "[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}"
kDigCmd     = "dig +short {}".format

def do_ping(server):
    cmd = kPingCmd(cmd_quote(server))
    return (do_shell_script(cmd)[0])

def get_host_IP_address(ipEchoService):
    cmd = kCurlCmd(cmd_quote(ipEchoService),kIpPattern)
    result, ipAddress = do_shell_script(cmd)
    return ['',ipAddress][result]

def lookup_IP_address(domain):
    cmd = kDigCmd(cmd_quote(domain))
    result, ipAddress = do_shell_script(cmd)
    return ['',ipAddress][result]

def do_shell_script (cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, err = p.communicate()
    return (not bool(p.returncode)), out.rstrip()

def zint(value):
    try: return int(value)
    except: return 0

#-------------------------------------------------------------------------------
# http://stackoverflow.com/questions/2532053/validate-a-hostname-string
def is_valid_hostname(hostname):
    if hostname[-1] == ".":
        # strip exactly one dot from the right, if present
        hostname = hostname[:-1]
    if len(hostname) > 253:
        return False
    labels = hostname.split(".")
    # the TLD must be not all-numeric
    if re.match(r"[0-9]+$", labels[-1]):
        return False
    allowed = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(label) for label in labels)

#-------------------------------------------------------------------------------
# http://stackoverflow.com/questions/319279/how-to-validate-ip-address-in-python
def is_valid_ipv4_address(address):
    try:
        socket.inet_pton(socket.AF_INET, address)
    except AttributeError:  # no inet_pton here, sorry
        try:
            socket.inet_aton(address)
        except socket.error:
            return False
        return address.count('.') == 3
    except socket.error:  # not a valid address
        return False
    return True
def is_valid_ipv6_address(address):
    try:
        socket.inet_pton(socket.AF_INET6, address)
    except socket.error:  # not a valid address
        return False
    return True

#-------------------------------------------------------------------------------
# http://stackoverflow.com/questions/7160737/python-how-to-validate-a-url-in-python-malformed-or-not#7160819
def is_valid_url(url, qualifying=None):
    min_attributes = ('scheme', 'netloc')
    qualifying = min_attributes if qualifying is None else qualifying
    token = urlparse(url)
    return all([getattr(token, qualifying_attr) for qualifying_attr in qualifying])

#-------------------------------------------------------------------------------
def ver(vstr): return tuple(map(int, (vstr.split('.'))))
