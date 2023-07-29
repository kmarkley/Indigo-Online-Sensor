# Online Sensor

This is a simple plugin that checks for internet connectivity and presents the result as an Indigo sensor device.

There are a few main uses:

1. Determine if the machine running Indigo Server is connected to the internet.
2. Determine if a particular online service is available.
3. Check if your external IP address changes to trigger a DDNS script
4. Check the speed of your internet connection with speedtest.net.

### The speedtest library must now be manually installed from terminal:

   `pip3 install speedtest-cli`

(You can ignore this if you don't have any speedtest devices configured)