#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# http://www.indigodomo.com

import indigo
import time
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
# globals

serverFields = ["checkServer1","checkServer2","checkServer3","checkServer4",
                "checkServer5","checkServer6","checkServer7","checkServe81"]

latestStateList = {
    "onlineSensor": (
        "lastUp",
        "lastDn",
        "nextUpdate",
        ),
    "publicIP": (
        "onOffState",
        "ipAddress",
        "ipAddressUi",
        "lastSuccess",
        "lastFail",
        "nextUpdate",
        )
    }

defaultOnlineSensorProps = {
    'checkServer1':     '8.8.8.8',          # google dns
    'checkServer2':     '8.8.4.4',          # google dns
    'checkServer3':     '208.67.222.222',   # opneDNS
    'checkServer4':     '208.67.220.220',   # opneDNS
    'checkServer5':     '209.244.0.3',      # level3
    'checkServer6':     '209.244.0.4',      # level3
    'checkServer7':     '37.235.1.174',     # freeDNS
    'checkServer8':     '37.235.1.177',     # freeDNS
    'updateFrequency':  '5',
    'sensorLogic':      'ANY',
    'updateFreqSeconds': 300,
    }

defaultPublicIPProps = {
    'updateFrequency':  '15',
    'updateFreqSeconds': 300,
    'ipEchoService': "http://ipecho.net/plain",
    }

################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
    
    def __del__(self):
        indigo.PluginBase.__del__(self)

    ########################################
    # Plugin Methods
    ########################################
    def startup(self):
        self.debug = self.pluginPrefs.get("showDebugInfo",False)
        self.logger.debug(u"startup")
        if self.debug:
            self.logger.debug("Debug logging enabled")
        self.deviceList = []

    def shutdown(self):
        self.logger.debug(u"shutdown")

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.logger.debug(u"closedPrefsConfigUi")
        if not userCancelled:
            self.debug = valuesDict.get("showDebugInfo",False)
            if self.debug:
                self.logger.debug("Debug logging enabled")
    
    def runConcurrentThread(self):
        try:
            while True:
                loopTime = time.time()
                for devId in self.deviceList:
                    dev = indigo.devices[devId]
                    if dev.deviceTypeId == "onlineSensor":
                        if dev.states["nextUpdate"] < loopTime:
                            self.updateOnlineSensor(dev)
                    elif dev.deviceTypeId == "publicIP":
                        if dev.states["nextUpdate"] < loopTime:
                            self.updatePublicIP(dev)
                self.sleep(int(loopTime+10-time.time()))
        except self.StopThread:
            pass    # Optionally catch the StopThread exception and do any needed cleanup.
        

    
    ########################################
    # Device Methods
    ########################################
    
    def validateDeviceConfigUi(self, valuesDict, typeId, devId, runtime=False):
        self.logger.debug(u"validateDeviceConfigUi: " + typeId)
        errorsDict = indigo.Dict()
        
        if typeId == "onlineSensor":
            if valuesDict.get("updateFrequency","") == "":
                errorsDict["updateFrequency"] = "Update Frequency is required"
            elif not valuesDict.get("updateFrequency","").isdigit():
                errorsDict["updateFrequency"] = "Update Frequency must be a positive integer"
            elif int(valuesDict.get("updateFrequency","")) == 0:
                errorsDict["updateFrequency"] = "Update Frequency may not be zero"
            for key, value in valuesDict.items():
                if (key in serverFields) and value:
                    if not any([is_valid_hostname(value),is_valid_ipv4_address(value),is_valid_ipv6_address(value)]):
                        errorsDict[key] = "Not valid IP or host name"
            
        elif typeId == "publicIP":
            if valuesDict.get("updateFrequency","") == "":
                errorsDict["updateFrequency"] = "Update Frequency is required"
            elif not valuesDict.get("updateFrequency","").isdigit():
                errorsDict["updateFrequency"] = "Update Frequency must be a positive integer"
            elif int(valuesDict.get("updateFrequency","")) < 5:
                errorsDict["updateFrequency"] = "Update Frequency must be at least 5 minutes"
            if not is_valid(valuesDict.get("ipEchoService",defaultPublicIPProps["ipEchoService"])):
                errorsDict["ipEchoService"] = "Not a valid URL"
            
        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)
    
    def deviceStartComm(self, dev):
        self.logger.debug(u"deviceStartComm: "+dev.name)
        if any(item not in dev.states for item in latestStateList[dev.deviceTypeId]):
            dev.stateListOrDisplayStateIdChanged()
        theProps = dev.pluginProps
        if dev.deviceTypeId in ("onlineSensor","publicIP"):
            theProps["updateFrequency"] = theProps.get("updateFrequency","5")
            theProps["updateFreqSeconds"] = int(theProps["updateFrequency"])*60
        if dev.deviceTypeId == "onlineSensor":
            servers = []
            for key, value in theProps.items():
                if (key in serverFields) and value:
                    servers.append(value)
            theProps["servers"] = servers
        if theProps != dev.pluginProps:
            dev.updateStateOnServer(key='nextUpdate', value=int(time.time()+theProps["updateFreqSeconds"]))
            dev.replacePluginPropsOnServer(theProps)
        if dev.id not in self.deviceList:
            self.deviceList.append(dev.id)
    
    def deviceStopComm(self, dev):
        self.logger.debug(u"deviceStopComm: "+dev.name)
        if dev.id in self.deviceList:
            self.deviceList.remove(dev.id)
            
    def updateOnlineSensor(self,dev):
        self.logger.debug(u"updateOnlineSensor: " + dev.name)
        startTime = time.time()
        theProps = dev.pluginProps
        newStates = [{'key':'nextUpdate','value':int(startTime+theProps["updateFreqSeconds"])}]
        servers = theProps.get("servers",[])
        # check servers
        if theProps.get("sensorLogic","ANY") == "ANY":
            shuffle(servers)
            online = any(do_ping(server) for server in servers)
        else:
            online = all(do_ping(server) for server in servers)
        # update if changed
        if online != dev.onState:
            newStates.append({'key':'onOffState','value':online})
            if online:
                newStates.append({'key':'lastUp','value':unicode(indigo.server.getTime())})
            else:
                newStates.append({'key':'lastDn','value':unicode(indigo.server.getTime())})
        # update device
        dev.updateStatesOnServer(newStates)
        self.logger.debug("updateOnlineSensor: "+unicode(time.time()-startTime)+" seconds")
    
    def updatePublicIP(self,dev):
        self.logger.debug(u"updatePublicIP: " + dev.name)
        startTime = time.time()
        theProps = dev.pluginProps
        newStates = [{'key':'nextUpdate','value':int(startTime+theProps["updateFreqSeconds"])}]
        # get IP address
        ipAddress = get_host_IP_address(theProps.get("ipEchoService",defaultPublicIPProps["ipEchoService"]))
        if ipAddress:
            if not dev.states["onOffState"]:
                newStates.append({'key':'onOffState','value':True})
            if dev.states["ipAddress"] != ipAddress:
                newStates.append({'key':'ipAddress','value':ipAddress})
            if dev.states["ipAddressUi"] != ipAddress:
                newStates.append({'key':'ipAddressUi','value':ipAddress})
            newStates.append({'key':'lastSuccess','value':unicode(indigo.server.getTime())})
        else:
            if dev.states["onOffState"]:
                newStates.append({'key':'onOffState','value':False})
            if dev.states["ipAddressUi"] != "N/A":
                newStates.append({'key':'ipAddressUi','value':"N/A"})
            newStates.append({'key':'lastFail','value':unicode(indigo.server.getTime())})
        # update device
        dev.updateStatesOnServer(newStates)
        self.logger.debug("updatePublicIP: "+unicode(time.time()-startTime)+" seconds")
    
    ########################################
    # Menu Methods
    ########################################
    
    def createSampleOnlineSensor(self, valuesDict="", typeId=""):
        self.logger.debug(u"createSampleOnlineSensor: " + valuesDict.get("sampleName"))
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
                props        = defaultOnlineSensorProps,
                )
            return (True, valuesDict)
    
    def createSamplePublicIP(self, valuesDict="", typeId=""):
        self.logger.debug(u"createSamplePublicIP: " + valuesDict.get("sampleName"))
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
                props        = defaultPublicIPProps,
                )
            return (True, valuesDict)
    
    ########################################
    # Action Methods
    ########################################
    
    def actionControlSensor(self, action, dev):
        self.logger.debug(u"actionControlSensor: "+dev.name)
        if action.sensorAction == indigo.kUniversalAction.RequestStatus:
            if dev.deviceTypeId == "onlineSensor":
                self.updateOnlineSensor(dev)
            elif dev.deviceTypeId == "publicIP":
                self.updatePublicIP(dev)
        else:
            self.logger.error("Unknown action: "+unicode(action.sensorAction))
    
########################################
# Utilities
########################################

def do_ping(server):
    cmd = "/sbin/ping -c1 -t1 %s" % cmd_quote(server)
    return (do_shell_script(cmd)[0])

def get_host_IP_address(ipEchoService):
    cmd = "curl -m 15 -s %s | grep -o '[0-9][0-9]*.[0-9][0-9]*.[0-9][0-9]*.[0-9][0-9]*'" % cmd_quote(ipEchoService)
    result = do_shell_script(cmd)
    if result[0]:
        return result[1]
    else:
        return ''

def do_shell_script (cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, err = p.communicate()
    return (not bool(p.returncode)), out.rstrip()

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
def is_valid(url, qualifying=None):
    min_attributes = ('scheme', 'netloc')
    qualifying = min_attributes if qualifying is None else qualifying
    token = urlparse.urlparse(url)
    return all([getattr(token, qualifying_attr)
                for qualifying_attr in qualifying])