# Online Sensor

This is an extremely simple plugin that checks for internet connectivity and presents the result as an Indigo sensor device.

There are a few main uses:

1. Determine if the machine running Indigo Server is connected to the internet.
2. Determine if a particular online service is available.
3. Check if your external IP address changes to trigger a DDNS script
4. Check the speed of your internet connection with speedtest.net.

## Easy Setup

Select the **Create Sample Device** items from the plugin's menu.  

Most people will only need one device of each type, and default setting should work fine.  But you can customize the configurations any way you like.

## Devices

The plugin defines four Device types: Online Sensor, Public IP, Lookup IP, and Speedtest.

### 'Online Sensor' devices

#### Configuration

* **Servers**  
Define up to 8 servers for the device to ping.  Servers can be IP addresses or Domain names.  Basic validation will be performed.

* **Update Frequency**  
Define how often the device will check (ping) the server(s).

* **Sensor Logic**  
Define whether the device goes **ON** when **ANY** of the servers reply to pings or when **ALL** of them do.

#### States

* **Last Up**  
Timestamp of the last time the device switched to the **ON** state.

* **Last Down**  
Timestamp of the last time the device switched to the **OFF** state.

* **onOffState**  
Whether Indigo is connected to the internet.

### 'Public IP' devices

#### Configuration

* **IP Echo Service**  
Define the service you want to use.  Defaults to http://ipecho.net/plain

* **Update Frequency**  
Define how often the device will check for a new IP address.

#### States

* **IP Address**  
The apparent public IP address of the machine running Indigo Server.  **Note that the state does not change until a new positive result is obtained.**  If the device fails to optain an IP, the old state will persist. This makes it useful as a trigger for updating DDNS.

* **IP Address UI**  
Same as above, except that when the device fails to connect the UI displays "N/A".

* **Last Change**  
Timestamp of the last time the device optained a new IP address.

* **onOffState**  
If the last attempt was successful.

### 'Lookup IP' devices

#### Configuration

* **Domain Name**  
Define the domain name to lookup.

* **Update Frequency**  
Define how often the device will check for a new IP address.

#### States

* **IP Address**  
The IP address of the specified domain.  **Note that the state does not change until a new positive result is obtained.**  If the device fails to optain an IP, the old state will persist. This makes it useful as a trigger for updating DDNS.

* **IP Address UI**  
Same as above, except that when the device fails to connect the UI displays "N/A".

* **Last Change**  
Timestamp of the last time the device optained a new IP address.

* **onOffState**  
If the last attempt was successful.

### 'Speedtest' devices

#### Configuration

* **Select Test(s)**  
Perform download test, upload test, or both.

* **On Threshold**  
The minimum tested speed (upload or download) at which the sensor will report ON.

* **Distance Unit**  
Speedtest.net reports the distance to the server.  This only affects the unit label on control pages (i.e. no conversion takes place).

* **Update Frequency**  
Define how often the device perform a speedtest.

#### States

* **Download Speed (Mbps)**  
The download speed in Mbps, rounded to 2 decimal places.

* **Upload Speed (Mbps)**  
The upload speed in Mbps, rounded to 2 decimal places.

* **Raw Download Speed**  
The raw download speed as reported by speedtest.net (in bps).

* **Raw Upload Speed**  
The raw upload speed as reported by speedtest.net (in bps).

* **Ping Latency**  
Round trip ping time in milliseconds, rounded to 2 decimal places.

* **Server ID**  
ID of the speedtest server.

* **Server Latitude**  
Latitude of the speedtest server.

* **Server Longitude**  
Longitude of the speedtest server.

* **Server Distance**  
Distance to the speedtest server.

* **Server Name**  
Name of the speedtest server.

* **Server Country**  
Country where the speedtest server is located.

* **Server Country Code**  
Country code of the speedtest server.

* **Server URL 1**  
Primary URL of the speedtest server.

* **Server URL 2**  
Secondary URL of the speedtest server.

* **Server Host**  
Hostname of the speedtest server.

* **Server Sponsor**  
Sponsor of the speedtest server.

* **Share Link**  
URL to a sharable image of the last test results on speedtest.net.

* **Timestamp**  
Timestamp of the last test, exactly as provide by speedtest.net.

* **Bytes Received**  
Bytes received in last download test.

* **Bytes Sent**  
Bytes sent in last upload test.

* **onOffState**  
If the last attempt was successful.

## Notes

* When sensor logic is **ANY**, the list of servers will be shuffled before each update.
* The ping command sends a single ping packet with a timeout of 1 second.
* The IP Echo request has a timeout of 15 seconds.
* Speed tests are performed on a new thread.  Only one speed test may occur at a time.