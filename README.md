# pytuya2mqtt

A bridge between [jasonacox/tinytuya](https://github.com/jasonacox/tinytuya) and MQTT.

Based on [mafrosis/tinytuya2mqtt](https://github.com/mafrosis/tinytuya2mqtt)

## Description

This project is a bridge that allows locally controlling IOT devices manufactured by Tuya Inc., and sold under many different brands, via simple MQTT topics. It effectively translate the Tuya protocol to easy to use topics.

Using this script requires obtaining the device ID and local keys for each of your devices after they are configured via the Tuya/Smart Life or other Tuya compatible app. With this information it is possible to communicate locally with Tuya devices using Tuya protocol version 3.1, 3.2, 3.3, 3.4 and 3.5 without using the Tuya Cloud service, however, getting the keys requires signing up for a Tuya IOT developer account.

## Features

* Local operations without Tuya cloud
* Tuya protocol version 3.1, 3.2, 3.3, 3.4 and 3.5 support
* Read states and send commands from/to any Tuya devices via MQTT
* Multithreading. Each device is polled independently
* Fully supports any sub-Devices behind Zigbee gateway
* Runs as systemd daemon

## Running

Run:
```
python3 main.py
```

Or, as a `daemon`:
```
python3 main.py -d
```

To enable debugging output (required when opening an issue):
```
python3 main.py -v 
```

To enable tinytuya debugging use tinytuya.set_debug() or TINYTUYA_DEBUG environment variable


## Setup and config

Install the necessary modules:
```
pip3 install -r requirements.txt
```

Config
----------

Two things are required:

 1. `devices.json`
 2. `mqtt.ini`


#### mqtt.ini

Example:

```ini
[mqtt]
hostname = 127.0.0.1
username = yourLogin
password = yourPassword
base_topic = tuya
```

#### devices.json


```json
[
	{
		"name": "gw2",
		"id": "aaaabbbbccccddddeeeeff",
		"ip": "192.168.20.21",
		"key": "????xxxxZZZZUUU",
		"version": 3.4,
		"subDevices":
		[
			{
				"name": "gw2-temp1",
				"id": "bbbbccccddddeeeeffffgg",
				"cid": "4444ccccddddeeee"
		  	},
		  	{
				"name": "temp2",
				"id": "ccccddddeeeeffffgggghh",
				"cid": "5555ccccddddeeee"
		  	}
		] 
	},
	{
		"name": "gw1",
		"id": "aaaabbbbccccddddeeeeff",
		"ip": "192.168.20.22",
		"key": "ZZZZxxxx????UUU",
		"version": 3.3,
		"subDevices":
		 [ 
			{
				"name": "trv",
				"id": "zzzzddddeeeeffffgggghh",
				"cid": "6666ccccddddeeee"
		   	}
		 ] 
	},
	{
		"name": "socket",
		"id": "aaaabbbbccccddddeeeeff",
		"ip": "192.168.20.23",
		"key": "ZZZZxxxx$$$$UUU",
		"version": 3.3
	},
	{
		"name": "socket2",
		"id": "yyyybbbbccccddddeeeeff",
		"ip": "192.168.20.24",
		"key": "ZZZZssss$$$$UUU",
		"version": 3.5
	}
]
```

#### Systemd script for Debian-like OS

Just create file /etc/systemd/system/pytuya2mqtt.service

```
[Unit]
 Description=pytuya2mqtt
 After=network.target
  
 [Service]
 ExecStart=/usr/bin/python3 /opt/pytuya2mqtt/main.py -d
 Restart=always
 User=openhab
 Group=openhab
 Environment=PATH=/usr/bin/
 WorkingDirectory=/opt/pytuya2mqtt/
 
 [Install]
 WantedBy=multi-user.target

 ```

Enable and run:
```
 systemctl enable pytuya2mqtt.service
 systemctl start pytuya2mqtt
```

### MQTT Topic Overview

The top level topics are created using the device name as the primary identifier. If the device as the name "Kitchen Table", the top level topic would be:

```tuya/kitchen_table/```

Controlling devices directly via DPS topics requires enough knowledge of the device to know which topics accept what values. Described below are two different methods for interfacing with DPS values, the JSON DPS topic, and the individual DPS key topics.

DPS Key topics
----------

DPS key topics allow you to monitor and send simple bool/number/string values directly to DPS keys without having to use the Tuya JSON format, the conversion to Tuya JSON is handled by tuya-mqtt. Using the example from above, turning on the dimmer and setting brightness to 50% you would simply issue the message "true" to DPS/1/command and the message "128" to DPS/2/command.

```
tuya/dimmer_device/dps/1/state    --> true/false for on/off state
tuya/dimmer_device/dps/2/command  <-- 1-255 for brightness state
tuya/dimmer_device/dps/1/state    --> accept true/false for turning device on/off
tuya/dimmer_device/dps/2/command  <-- accepts 1-255 for controlling brightness level
```

!!! Important Note !!! When sending commands directly to DPS values there are no limitation on what values are sent as tuya-mqtt has no way to know what are valid vs invalid for any given DPS key. Sending values that are out-of-range or of different types than the DPS key expects can cause unpredictable behavior of your device, from causing timeouts, to reboots, to hanging the device. While I've never seen a device fail to recover after a restart, please keep this in mind when sending commands to your device.

DPS Topics for devices behind Zigbee Gateway
----------
In addition to the DPS Key topics, it's possible to use the DPS for devices behind Tuya Gateway.

'cid' - is the subdevice id.

'name' - is the name of subdevice (from devices.json)


This example demostrates DPS values and commands for Tuya Smart Thermostat Radiator Valve behind Zigbee Gateway:

```
Thermostat mode:
tuya/thermostat/dsp/4/state      --> {"4":"auto"}
Possible values: auto/temp_auto/holiday/manual/comfort/eco/BOOST
tuya/thermostat/dps/4/command    <-- auto

Temperature Setpoint:
tuya/thermostat/dps/2/state      --> {"2": 220}
Where 220 - 22.0 Celsius
tuya/thermostat/dps/command      <-- 225

Current Temperature:
tuya/thermostat/dps/3/state      --> {"3": 225}
Where 225 - 22.5 Celsius

Valve percent:
tuya/thermostat/dps/109/state    --> {"109": 30}
Where 30 - 30%
```


