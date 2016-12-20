# Online Sensor

This is an )extremely simple plugin that pings internet servers and presents the result as an Indigo Sensor device.

There are 2 main uses:

1. Determine if the machine running Indigo Server is connected to the internet.
2. Determine if a particular online service is available.

(One could conceivable also use this to determine the status of local network resouces, but FINGscan is a much more robust tool for that.)

## Easy Setup

Select **Add Sample Device** from the plugin's menu.  A device will be created that pings 8 very large DNS servers.  Now Indigo knows if it is connected to the internet.  Customize the configuration any way you like.

## Devices

The plugin defines one new type of Device, the Online Sensor.

### Configuration

##### Servers

Define up to 8 servers for the device to ping.  Servers can be IP addresses or Domain names.  Basic validation will be performed.

##### Update Frequency (minutes)

Define how often the device will check (ping) the server(s).

##### Sensor Logic

Define whether the device goes **ON** when **ANY** of the servers reply to pings or when **ALL** of them do.

### States

The plugin provide the following device states:

##### IP Address

The apparent public IP address of the machine running Indigo Server.  Useful as a trigger for updating DDNS.

##### Last Up

Timestamp of the last time the device switched to the **ON** state.

##### Last Down

Timestamp of the last time the device switched to the **OFF** state.

##### Next Update

Seconds after epoch to perform the next update.  Used internally.

## Notes

* The list of servers will be shuffled before each update. For **ANY** sensor logic and frequent updating, this speeds up updates in the the case where the first server is not reachable.
* The ping command sends a single ping packet with a timeout of 1 second.  So maximum time to update is on the order of 8 seconds. Typically *much* lower.