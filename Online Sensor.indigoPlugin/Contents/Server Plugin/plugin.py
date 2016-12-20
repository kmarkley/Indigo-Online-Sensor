#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# http://www.indigodomo.com

import indigo
import time
import subprocess
import re
import socket
from random import shuffle

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.

###############################################################################
# globals

serverFields = ["checkServer1","checkServer2","checkServer3","checkServer4",
                "checkServer5","checkServer6","checkServer7","checkServe81"]

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
                for dev in indigo.devices.iter(u'self'):
                    if dev.deviceTypeId == "onlineSensor":
                        if dev.pluginProps.get("nextUpdate",0) < time.time():
                            self.updateOnlineSensor(dev)
                self.sleep(10)
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
            
        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)
    
    def deviceStartComm(self, dev):
        self.logger.debug(u"deviceStartComm: " + dev.name)
        theProps = dev.pluginProps
        if dev.deviceTypeId == "onlineSensor":
            theProps["updateFrequency"] = theProps.get("updateFrequency","5")
            theProps["updateFreqSeconds"] = int(theProps["updateFrequency"])*60
            servers = []
            for key, value in theProps.items():
                if (key in serverFields) and value:
                    servers.append(value)
            theProps["servers"] = servers
        if theProps != dev.pluginProps:
            dev.replacePluginPropsOnServer(theProps)
    
    def updateOnlineSensor(self,dev):
        self.logger.debug(u"updateOnlineSensor: " + dev.name)
        theProps = dev.pluginProps
        servers = theProps.get("servers",[])
        shuffle(servers)
        if theProps.get("sensorLogic","ANY") == "ANY":
            online = any(_doPing(server) for server in servers)
        else:
            online = all(_doPing(server) for server in servers)
        dev.updateStateOnServer(key='onOffState', value=online)        
        theProps["nextUpdate"] = int(time.time()+theProps["updateFreqSeconds"])
        dev.replacePluginPropsOnServer(theProps)

    
    ########################################
    # Action Methods
    ########################################
    
    def actionControlSensor(self, action, dev):
        self.logger.debug(u"actionControlSensor: "+dev.name)
        if dev.deviceTypeId == "onlineSensor":
            if action.sensorAction == indigo.kDeviceGeneralAction.RequestStatus:
                self.updateOnlineSensor(dev)
            else:
                self.logger.error("Unknown action: "+unicode(action.sensorAction))
    
    ########################################
    # Utilities
    ########################################
    
def _doPing(server):
  p = subprocess.Popen("/sbin/ping -c1 -t1 "+server,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  p.communicate()
  return (p.returncode == 0)

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