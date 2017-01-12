#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# http://www.indigodomo.com

import indigo
from datetime import datetime, timedelta
import subprocess
import re
import socket
import urlparse
from random import shuffle
try:
    from shlex import quote as cmd_quote
except ImportError:
    from pipes import quote as cmd_quote

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.

###############################################################################
# these are used to create sample devices, 
# and also to update existing devices when plugin changes.

defaultProps = {
    "onlineSensor": {
        "checkServer1":     "8.8.8.8",          # google dns
        "checkServer2":     "8.8.4.4",          # google dns
        "checkServer3":     "208.67.222.222",   # opneDNS
        "checkServer4":     "208.67.220.220",   # opneDNS
        "checkServer5":     "209.244.0.3",      # level3
        "checkServer6":     "209.244.0.4",      # level3
        "checkServer7":     "37.235.1.174",     # freeDNS
        "checkServer8":     "37.235.1.177",     # freeDNS
        "updateFrequency":  "5",
        "sensorLogic":      "ANY",
        },
    "publicIP": {
        "ipEchoService": "http://ipecho.net/plain",
        "updateFrequency":  "15",
        },
    "lookupIP": {
        "domainName": "localhost",
        "updateFrequency":  "15",
        },
    }

serverFields = ["checkServer1","checkServer2","checkServer3","checkServer4",
                "checkServer5","checkServer6","checkServer7","checkServer8"]

################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
    
    def __del__(self):
        indigo.PluginBase.__del__(self)

    ########################################
    # Start, Stop and Config changes
    ########################################
    def startup(self):
        self.debug = self.pluginPrefs.get("showDebugInfo",False)
        self.logger.debug("startup")
        if self.debug:
            self.logger.debug("Debug logging enabled")
        self.deviceDict = dict()

    ########################################
    def shutdown(self):
        self.logger.debug("shutdown")
        self.pluginPrefs['showDebugInfo'] = self.debug

    ########################################
    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.logger.debug("closedPrefsConfigUi")
        if not userCancelled:
            self.debug = valuesDict.get("showDebugInfo",False)
            if self.debug:
                self.logger.debug("Debug logging enabled")
    
    ########################################
    def runConcurrentThread(self):
        try:
            while True:
                loopTime = datetime.now()
                for devId in self.deviceDict:
                    dev = self.deviceDict[devId]['dev']
                    if self.deviceDict[devId]['lastCheck'] + timedelta(minutes=int(dev.pluginProps['updateFrequency'])) < loopTime:
                        self.updateDeviceStatus(dev)
                        self.deviceDict[devId]['lastCheck'] = loopTime
                self.sleep((loopTime+timedelta(seconds=10)-datetime.now()).total_seconds())
        except self.StopThread:
            pass    # Optionally catch the StopThread exception and do any needed cleanup.
    
    ########################################
    # Device Methods
    ########################################
    def deviceStartComm(self, dev):
        self.logger.debug("deviceStartComm: "+dev.name)
        if dev.version != self.pluginVersion:
            self.updateDeviceVersion(dev)
        if dev.id not in self.deviceDict:
            self.deviceDict[dev.id] = {'dev':dev, 'lastCheck':datetime(1,1,1)}
    
    ########################################
    def deviceStopComm(self, dev):
        self.logger.debug("deviceStopComm: "+dev.name)
        if dev.id in self.deviceDict:
            del self.deviceDict[dev.id]
            
    ########################################
    def validateDeviceConfigUi(self, valuesDict, typeId, devId, runtime=False):
        self.logger.debug("validateDeviceConfigUi: " + typeId)
        errorsDict = indigo.Dict()
        
        # ONLINE SENSOR
        if typeId == "onlineSensor":
            for key, value in valuesDict.items():
                if (key in serverFields) and value:
                    if not any([is_valid_hostname(value),is_valid_ipv4_address(value),is_valid_ipv6_address(value)]):
                        errorsDict[key] = "Not valid IP or host name"
            
        # PUBLIC IP
        elif typeId == "publicIP":
            if not is_valid_url(valuesDict.get("ipEchoService")):
                errorsDict["ipEchoService"] = "Not a valid URL"
            
        # LOOKUP IP
        elif typeId == "lookupIP":
            if not is_valid_hostname(valuesDict.get("domainName")):
                errorsDict["domainName"] = "Not a valid domain"
            
        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        else:
            return (True, valuesDict)
    
    ########################################
    def updateDeviceVersion(self, dev):
        self.logger.debug("updateDeviceVersion: " + dev.name)
        theProps = dev.pluginProps
        # update states
        dev.stateListOrDisplayStateIdChanged()
        # add new props
        for key, value in defaultProps[dev.deviceTypeId].items():
            if (key not in serverFields) and ((key not in theProps) or not theProps[key]):
                theProps[key] = value
        # delete obsolete props
        for key in theProps:
            if (key not in defaultProps[dev.deviceTypeId]):
                del theProps[key]
        # push to server
        theProps["version"] = self.pluginVersion
        dev.replacePluginPropsOnServer(theProps)
    
    ########################################
    def updateDeviceStatus(self,dev):
        self.logger.debug("updateDeviceStatus: " + dev.name)
        statusUpdateTime = datetime.now()
        theProps = dev.pluginProps
        newStates = []
        
        # ONLINE SENSOR
        if dev.deviceTypeId == "onlineSensor":
            servers = filter(None, (theProps.get(key) for key in serverFields))
            # check servers
            if theProps.get("sensorLogic","ANY") == "ANY":
                shuffle(servers)
                online = any(do_ping(server) for server in servers)
            else:
                online = all(do_ping(server) for server in servers)
            # update if changed
            if online != dev.onState:
                self.logger.info('"%s" %s' % (dev.name, ['off','on'][online]))
                if online:
                    newStates.append({'key':'lastUp','value':unicode(statusUpdateTime)})
                else:
                    newStates.append({'key':'lastDn','value':unicode(statusUpdateTime)})
        
        # PUBLIC IP, LOOKUP IP
        elif dev.deviceTypeId in ("publicIP","lookupIP"):
            # get IP address
            if dev.deviceTypeId == "publicIP":
                ipAddress = get_host_IP_address(theProps.get("ipEchoService"))
            elif dev.deviceTypeId == "lookupIP":
                ipAddress = lookup_IP_address(theProps.get("domainName"))
            else:
                ipAddress = False
            # update if changed
            online = bool(ipAddress)
            if online != dev.onState:
                self.logger.info('"%s" %s' % (dev.name, ['off','on'][online]))
                if online:
                    newStates.append({'key':'ipAddressUi','value':ipAddress})
                else:
                    newStates.append({'key':'ipAddressUi','value':"not available"})
            if online and (ipAddress != dev.states["ipAddress"]):
                self.logger.info('"%s" new IP Address: %s' % (dev.name, ipAddress))
                newStates.append({'key':'ipAddress','value':ipAddress})
                newStates.append({'key':'lastChange','value':unicode(statusUpdateTime)})
        
        # update device
        newStates.append({'key':'onOffState','value':online})
        dev.updateStatesOnServer(newStates)
        self.logger.debug("updateDeviceStatus: %s seconds" % (datetime.now()-statusUpdateTime).total_seconds() )
    
    ########################################
    # Menu Methods
    ########################################
    def createSampleOnlineSensor(self, valuesDict="", typeId=""):
        self.logger.debug("createSampleOnlineSensor: " + valuesDict.get("sampleName"))
        errorsDict = indigo.Dict()
        
        theName = valuesDict.get("sampleName","Online Sensor Sample Device")
        if theName in indigo.devices:
            errorsDict["sampleName"] = "A device with that name already exists"
        
        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        else:
            indigo.device.create(
                protocol     = indigo.kProtocol.Plugin,
                name         = theName,
                description  = "",
                deviceTypeId = "onlineSensor",
                props        = defaultProps["onlineSensor"],
                )
            return (True, valuesDict)
    
    ########################################
    def createSamplePublicIP(self, valuesDict="", typeId=""):
        self.logger.debug("createSamplePublicIP: " + valuesDict.get("sampleName"))
        errorsDict = indigo.Dict()
        
        theName = valuesDict.get("sampleName","Public IP Sample Device")
        if theName in indigo.devices:
            errorsDict["sampleName"] = "A device with that name already exists"
        
        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        else:
            indigo.device.create(
                protocol     = indigo.kProtocol.Plugin,
                name         = theName,
                description  = "",
                deviceTypeId = "publicIP",
                props        = defaultProps["publicIP"],
                )
            return (True, valuesDict)
    
    ########################################
    # Action Methods
    ########################################
    def actionControlSensor(self, action, dev):
        self.logger.debug("actionControlSensor: "+dev.name)
        # STATUS REQUEST
        if action.sensorAction == indigo.kUniversalAction.RequestStatus:
            self.logger.info('"%s" status request' % dev.name)
            self.updateDeviceStatus(dev)
        # UNKNOWN
        else:
            self.logger.debug('"%s" %s request ignored' % (dev.name, unicode(action.sensorAction)))
    
    ########################################
    # Menu Methods
    ########################################
    def toggleDebug(self):
        if self.debug:
            self.logger.debug("Debug logging disabled")
            self.debug = False
        else:
            self.debug = True
            self.logger.debug("Debug logging enabled")
        
########################################
# Utilities
########################################
def do_ping(server):
    cmd = "/sbin/ping -c1 -t1 %s" % cmd_quote(server)
    return (do_shell_script(cmd)[0])

def get_host_IP_address(ipEchoService):
    cmd = "curl -m 15 -s %s | grep -o '[0-9][0-9]*.[0-9][0-9]*.[0-9][0-9]*.[0-9][0-9]*'" % cmd_quote(ipEchoService)
    result, ipAddress = do_shell_script(cmd)
    return ['',ipAddress][result]

def lookup_IP_address(domain):
    cmd = "dig +short %s" % cmd_quote(domain)
    result, ipAddress = do_shell_script(cmd)
    return ['',ipAddress][result]

def do_shell_script (cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, err = p.communicate()
    return (not bool(p.returncode)), out.rstrip()

########################################
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

# http://stackoverflow.com/questions/7160737/python-how-to-validate-a-url-in-python-malformed-or-not#7160819
def is_valid_url(url, qualifying=None):
    min_attributes = ('scheme', 'netloc')
    qualifying = min_attributes if qualifying is None else qualifying
    token = urlparse.urlparse(url)
    return all([getattr(token, qualifying_attr)
                for qualifying_attr in qualifying])