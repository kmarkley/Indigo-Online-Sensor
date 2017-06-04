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
from datetime import datetime, timedelta
import subprocess
import re
import socket
import urlparse
from random import shuffle
import speedtest
try:
    from shlex import quote as cmd_quote
except ImportError:
    from pipes import quote as cmd_quote
from ghpu import GitHubPluginUpdater

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
        },
    'lanPing': {
        'checkServer1':     "127.0.0.1",        # localhost
        'updateFrequency':  "60",
        },
    'publicIP': {
        'ipEchoService':    "http://ipecho.net/plain",
        'updateFrequency':  "900",
        },
    'lookupIP': {
        'domainName':       "localhost",
        'updateFrequency':  "900",
        },
    'speedtest': {
        'testSelection':    "BOTH",
        'threshold_str':    "10.0",
        'threshold_float':  10.0,
        'distanceUnit':     "mi",
        'updateFrequency':  "21600",
        },
    }

serverFields = ['checkServer1','checkServer2','checkServer3','checkServer4',
                'checkServer5','checkServer6','checkServer7','checkServer8']

################################################################################
class Plugin(indigo.PluginBase):
    #-------------------------------------------------------------------------------
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.updater = GitHubPluginUpdater(self)

    def __del__(self):
        indigo.PluginBase.__del__(self)

    #-------------------------------------------------------------------------------
    # Start, Stop and Config changes
    #-------------------------------------------------------------------------------
    def startup(self):
        self.debug = self.pluginPrefs.get('showDebugInfo',False)
        self.logger.debug("startup")
        if self.debug:
            self.logger.debug("Debug logging enabled")
        self.speedtest_lock = threading.Lock()
        self.deviceDict = dict()

    #-------------------------------------------------------------------------------
    def shutdown(self):
        self.logger.debug("shutdown")
        self.pluginPrefs['showDebugInfo'] = self.debug

    #-------------------------------------------------------------------------------
    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.logger.debug("closedPrefsConfigUi")
        if not userCancelled:
            self.debug = valuesDict.get('showDebugInfo',False)
            if self.debug:
                self.logger.debug("Debug logging enabled")

    #-------------------------------------------------------------------------------
    def runConcurrentThread(self):
        try:
            while True:
                loopTime = datetime.now()
                for devId, device in self.deviceDict.items():
                    device.loopAction()
                self.sleep((loopTime+timedelta(seconds=1)-datetime.now()).total_seconds())
        except self.StopThread:
            pass    # Optionally catch the StopThread exception and do any needed cleanup.

    #-------------------------------------------------------------------------------
    # Device Methods
    #-------------------------------------------------------------------------------
    def deviceStartComm(self, device):
        self.logger.debug("deviceStartComm: "+device.name)
        if device.version != self.pluginVersion:
            self.updateDeviceVersion(device)

        if device.configured:
            if device.deviceTypeId == 'onlineSensor':
                self.deviceDict[device.id] = self.OnlineSensorDevice(device, self)
            elif device.deviceTypeId == 'lanPing':
                self.deviceDict[device.id] = self.LanPingDevice(device, self)
            elif device.deviceTypeId == 'publicIP':
                self.deviceDict[device.id] = self.PublicIpDevice(device, self)
            elif device.deviceTypeId == 'lookupIP':
                self.deviceDict[device.id] = self.LookupIpDevice(device, self)
            elif device.deviceTypeId == 'speedtest':
                self.deviceDict[device.id] = self.SpeedtestDevice(device, self)

    #-------------------------------------------------------------------------------
    def deviceStopComm(self, device):
        self.logger.debug("deviceStopComm: "+device.name)
        if device.id in self.deviceDict:
            del self.deviceDict[device.id]

    #-------------------------------------------------------------------------------
    def validateDeviceConfigUi(self, valuesDict, typeId, devId, runtime=False):
        self.logger.debug("validateDeviceConfigUi: " + typeId)
        errorsDict = indigo.Dict()

        # ONLINE SENSOR
        if typeId == 'onlineSensor':
            for key, value in valuesDict.items():
                if (key in serverFields) and value:
                    if not any([is_valid_hostname(value),is_valid_ipv4_address(value),is_valid_ipv6_address(value)]):
                        errorsDict[key] = "Not valid IP or host name"

        # LAN PING
        if typeId == 'lanPing':
            value = valuesDict['checkServer1']
            if not any([is_valid_ipv4_address(value),is_valid_ipv6_address(value)]):
                errorsDict['checkServer1'] = "Not valid IP addess"

        # PUBLIC IP
        elif typeId == 'publicIP':
            if not is_valid_url(valuesDict.get("ipEchoService")):
                errorsDict['ipEchoService'] = "Not a valid URL"

        # LOOKUP IP
        elif typeId == 'lookupIP':
            if not is_valid_hostname(valuesDict.get('domainName')):
                errorsDict['domainName'] = "Not a valid domain"

        # SPEEDTEST
        elif typeId == 'speedtest':
            try:
                valuesDict['threshold_float'] = float(valuesDict.get('threshold_str',0.))
                if valuesDict['threshold_float'] < 0:
                    raise ValueError("negative value")
            except:
                errorsDict['threshold_str'] = "Must be a positive real number (or zero)."

        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        else:
            return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def updateDeviceVersion(self, device):
        self.logger.debug("updateDeviceVersion: " + device.name)
        theProps = device.pluginProps
        # update states
        device.stateListOrDisplayStateIdChanged()
        # add new props
        for key, value in defaultProps[device.deviceTypeId].items():
            if (key not in serverFields) and ((key not in theProps) or not theProps[key]):
                theProps[key] = value

        # update frequency from minutes to seconds
        if str(theProps.get('version',"Z.Z.Z")) < "0.0.9":
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
        self.logger.debug("createSampleDevice: " + valuesDict.get('deviceName'))
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
    # Action Methods
    #-------------------------------------------------------------------------------
    def actionControlSensor(self, action, device):
        self.logger.debug("actionControlSensor: "+device.name)
        # STATUS REQUEST
        if action.sensorAction == indigo.kUniversalAction.RequestStatus:
            self.logger.info('"{}" status request'.format(device.name))
            self.deviceDict[device.id].updateState()
        # UNKNOWN
        else:
            self.logger.error('"{}" {} request ignored'.format(device.name, unicode(action.sensorAction)))

    #-------------------------------------------------------------------------------
    # Menu Methods
    #-------------------------------------------------------------------------------
    def checkForUpdates(self):
        self.updater.checkForUpdate()

    #-------------------------------------------------------------------------------
    def updatePlugin(self):
        self.updater.update()

    #-------------------------------------------------------------------------------
    def forceUpdate(self):
        self.updater.update(currentVersion='0.0.0')

    #-------------------------------------------------------------------------------
    def toggleDebug(self):
        if self.debug:
            self.logger.debug("Debug logging disabled")
            self.debug = False
        else:
            self.debug = True
            self.logger.debug("Debug logging enabled")

    ###############################################################################
    # Classes
    ###############################################################################
    class SensorBase(object):

        #-------------------------------------------------------------------------------
        def __init__(self, device, plugin):
            self.plugin     = plugin
            self.logger     = plugin.logger
            self.logger.debug("__init__: {}".format(device.name))

            self.device     = device
            self.id         = device.id
            self.name       = device.name
            self.props      = device.pluginProps
            self.freq       = zint(self.props['updateFrequency'])
            self.lastCheck  = device.lastChanged

        #-------------------------------------------------------------------------------
        def loopAction(self):
            if self.freq:
                if self.lastCheck + timedelta(seconds=self.freq) < datetime.now():
                    self.updateState()

        #-------------------------------------------------------------------------------
        # abstract methods
        #-------------------------------------------------------------------------------
        def updateState(self):
            raise NotImplementedError


    ###############################################################################
    class OnlineSensorDevice(SensorBase):

        #-------------------------------------------------------------------------------
        def __init__(self, device, plugin):
            plugin.SensorBase.__init__(self, device, plugin)
            self.logic  = self.props.get('sensorLogic',"ANY")

        #-------------------------------------------------------------------------------
        def updateState(self):
            newStates = []
            servers = filter(None, (self.props.get(key) for key in serverFields))
            if self.logic == "ANY":
                shuffle(servers)
                online = any(do_ping(server) for server in servers)
            else:
                online = all(do_ping(server) for server in servers)
            if online != self.device.onState:
                self.logger.info('"{}" {}'.format(self.name, ['off','on'][online]))
                newStates.append({'key':['lastDn','lastUp'][online],'value':unicode(datetime.now())})
            newStates.append({'key':'onOffState','value':online})
            self.device.updateStatesOnServer(newStates)
            self.lastCheck  = datetime.now()

    ###############################################################################
    class LanPingDevice(SensorBase):

        #-------------------------------------------------------------------------------
        def __init__(self, device, plugin):
            plugin.SensorBase.__init__(self, device, plugin)
            self.server = self.props.get('checkServer1','127.0.0.1')

        #-------------------------------------------------------------------------------
        def updateState(self):
            newStates = []
            servers = filter(None, (self.props.get(key) for key in serverFields))
            online = do_ping(self.server)
            if online != self.device.onState:
                self.logger.info('"{}" {}'.format(self.name, ['off','on'][online]))
                newStates.append({'key':['lastDn','lastUp'][online],'value':unicode(datetime.now())})
            newStates.append({'key':'onOffState','value':online})
            self.device.updateStatesOnServer(newStates)
            self.lastCheck  = datetime.now()

    ###############################################################################
    class IpBaseDevice(SensorBase):

        #-------------------------------------------------------------------------------
        def __init__(self, device, plugin):
            plugin.SensorBase.__init__(self, device, plugin)

        #-------------------------------------------------------------------------------
        def ipUpdate(self, ipAddress):
            newStates = []
            online = bool(ipAddress)
            if online != self.device.onState:
                self.logger.info('"{}" {}'.format(self.name, ['off','on'][online]))
            if online and (ipAddress != self.device.states['ipAddress']):
                self.logger.info('"{}" new IP Address: {}'.format(self.name, ipAddress))
                newStates.append({'key':'ipAddress','value':ipAddress})
                newStates.append({'key':'lastChange','value':unicode(datetime.now())})
            newStates.append({'key':'onOffState','value':online})
            newStates.append({'key':'ipAddressUi','value':["not available",ipAddress][online]})
            self.device.updateStatesOnServer(newStates)
            self.lastCheck  = datetime.now()

    ###############################################################################
    class PublicIpDevice(IpBaseDevice):

        #-------------------------------------------------------------------------------
        def __init__(self, device, plugin):
            plugin.IpBaseDevice.__init__(self, device, plugin)

        #-------------------------------------------------------------------------------
        def updateState(self):
            ipAddress = get_host_IP_address(self.props['ipEchoService'])
            self.ipUpdate(ipAddress)

    ###############################################################################
    class LookupIpDevice(IpBaseDevice):

        #-------------------------------------------------------------------------------
        def __init__(self, device, plugin):
            plugin.IpBaseDevice.__init__(self, device, plugin)

        #-------------------------------------------------------------------------------
        def updateState(self):
            ipAddress = lookup_IP_address(self.props['domainName'])
            self.ipUpdate(ipAddress)

    ###############################################################################
    class SpeedtestDevice(SensorBase):

        #-------------------------------------------------------------------------------
        def __init__(self, device, plugin):
            plugin.SensorBase.__init__(self, device, plugin)


        #-------------------------------------------------------------------------------
        def updateState(self):
            try:
                speedtest_thread = threading.Thread(target=self.performSpeedtest)
                speedtest_thread.setDaemon(True)
                speedtest_thread.start()
            except:
                self.logger.error("unable to start speedtest thread")

        #-------------------------------------------------------------------------------
        def performSpeedtest(self):
            if self.plugin.speedtest_lock.acquire(False):
                self.logger.debug("performSpeedtest: {}".format(self.name))
                speedtestStartTime = datetime.now()

                try:
                    s = speedtest.Speedtest()
                    self.logger.debug("  ...get best server...")
                    s.get_best_server()
                    if self.props['testSelection'] in ('DOWN','BOTH'):
                        self.logger.debug("  ...download...")
                        s.download()
                    if self.props['testSelection'] in ('UP','BOTH'):
                        self.logger.debug("  ...upload...")
                        s.upload()
                    self.logger.debug("  ...results...")
                    r = s.results

                    dnld = r.download/1024./1024.
                    upld = r.upload/1024./1024.
                    isOn = any(val > self.props.get('threshold_float',0.) for val in [dnld,upld])

                    ping = r.ping
                    dist = r.server.get('d',0.)
                    unit = self.props.get('distanceUnit','')
                    lat  = float(r.server.get('lat',0.))
                    lon  = float(r.server.get('lon',0.))

                    newStates = [
                        {'key':'onOffState',         'value':isOn  },
                        {'key':'Mbps_download',      'value':dnld,       'uiValue':'{:.2f} Mbps'.format(dnld),    'decimalPlaces':2 },
                        {'key':'Mbps_upload',        'value':upld,       'uiValue':'{:.2f} Mbps'.format(upld),    'decimalPlaces':2 },
                        {'key':'ping_latency',       'value':ping,       'uiValue':'{:.2f} ms'.format(ping),      'decimalPlaces':2 },
                        {'key':'server_distance',    'value':dist,       'uiValue':'{:.2f} {}'.format(dist,unit), 'decimalPlaces':2 },
                        {'key':'raw_download',       'value':r.download, 'uiValue':'{} bps'.format(r.download) },
                        {'key':'raw_upload',         'value':r.upload,   'uiValue':'{} bps'.format(r.upload)   },
                        {'key':'server_latitude',    'value':lat,        'uiValue':'{}°'.format(lat)           },
                        {'key':'server_longitude',   'value':lon,        'uiValue':'{}°'.format(lon)           },
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

                except Exception as e:
                    self.logger.error(e.message)
                    newStates = [ {'key':'onOffState','value':False} ]

                finally:
                    self.logger.debug("performSpeedtest: {} seconds".format( (datetime.now()-speedtestStartTime).total_seconds() ) )
                    self.device.updateStatesOnServer(newStates)
                    self.plugin.speedtest_lock.release()
            else:
                self.logger.error("Unable to acquire lock")

            self.lastCheck  = datetime.now()

###############################################################################
# Utilities
###############################################################################
def do_ping(server):
    cmd = "/sbin/ping -c1 -t1 {}".format(cmd_quote(server))
    return (do_shell_script(cmd)[0])

def get_host_IP_address(ipEchoService):
    ipPattern = '[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}'
    cmd = "curl -m 15 -s {} | egrep -o '{}'".format(cmd_quote(ipEchoService),ipPattern)
    result, ipAddress = do_shell_script(cmd)
    return ['',ipAddress][result]

def lookup_IP_address(domain):
    cmd = "dig +short {}".format(cmd_quote(domain))
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
    token = urlparse.urlparse(url)
    return all([getattr(token, qualifying_attr) for qualifying_attr in qualifying])
