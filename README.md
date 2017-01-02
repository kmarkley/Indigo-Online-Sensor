# Online Sensor

This is an extremely simple plugin that checks for internet connectivity and presents the result as an Indigo sensor device.

There are a few main uses:

1. Determine if the machine running Indigo Server is connected to the internet.
2. Determine if a particular online service is available.
3. Check if the external IP address changes to trigger a DDNS script
4. Determine the status of local network resouces. FINGscan is a much more robust tool for this, but if you only have a couple devices you're interested in this might do.

## Easy Setup

Select the **Add Sample Device** items from the plugin's menu.  

For **Online Sensor**, device will be created that pings 8 very large DNS servers.  Now Indigo knows if it is connected to the internet.  

For **Public IP**, a device will be created that uses ipecho.net to get your public IP.

Most people will only need one device of each type, and default setting should work fine.  But you can customize the configurations any way you like.

## Devices

The plugin defines two new types of Device, Online Sensors, and Public IPs.

### 'Online Sensor' devices

#### Configuration

* **Servers**  
Define up to 8 servers for the device to ping.  Servers can be IP addresses or Domain names.  Basic validation will be performed.

* **Update Frequency (minutes)**  
Define how often the device will check (ping) the server(s).

* **Sensor Logic**  
Define whether the device goes **ON** when **ANY** of the servers reply to pings or when **ALL** of them do.

#### States

* **Last Up**  
Timestamp of the last time the device switched to the **ON** state.

* **Last Down**  
Timestamp of the last time the device switched to the **OFF** state.

* **Last Checked**  
Timestamp of the last status update.

* **onOffState**  
Whether Indigo is connected to the internet.

### 'Public IP' devices

#### Configuration

* **IP Echo Service**  
Define the service you want to use.  Defaults to http://ipecho.net/plain

* **Update Frequency (minutes)**  
Define how often the device will check (ping) the server(s).  5 minute minimum.

#### States

* **IP Address**  
The apparent public IP address of the machine running Indigo Server.  **Note that the state does not change until a new positive result is obtained.**  If the device fails to optain an IP, the old state will persist. This makes it useful as a trigger for updating DDNS.

* **IP Address UI**  
Same as above, except that when the device fails to connect the UI displays "N/A".

* **Last Change**  
Timestamp of the last time the device optained a new IP address.

* **Last Fail**  
Timestamp of the last time the device failed to optained an IP address.

* **Last Checked**  
Timestamp of the last status update.

* **onOffState**  
If the last attempt was successful.

### 'Lookup IP' devices

#### Configuration

* **Domain Name**  
Define the domain name to lookup.

* **Update Frequency (minutes)**  
Define how often the device will check (ping) the server(s).  5 minute minimum.

#### States

* **IP Address**  
The IP address of the specified domain.  **Note that the state does not change until a new positive result is obtained.**  If the device fails to optain an IP, the old state will persist. This makes it useful as a trigger for updating DDNS.

* **IP Address UI**  
Same as above, except that when the device fails to connect the UI displays "N/A".

* **Last Change**  
Timestamp of the last time the device optained a new IP address.

* **Last Fail**  
Timestamp of the last time the device failed to optained an IP address.

* **Last Checked**  
Timestamp of the last status update.

* **onOffState**  
If the last attempt was successful.

## Notes

* When sensor logic is **ANY**, the list of servers will be shuffled before each update.
* The ping command sends a single ping packet with a timeout of 1 second.
* The IP Echo request has a timeout of 15 seconds.