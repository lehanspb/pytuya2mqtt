# pytuya2mqtt

A bridge between [jasonacox/tinytuya](https://github.com/jasonacox/tinytuya) and MQTT.

Based on [mafrosis/tinytuya2mqtt](https://github.com/mafrosis/tinytuya2mqtt)

## Description

This project is a bridge that allows locally controlling IOT devices manufactured by Tuya Inc., and sold under many different brands, via simple MQTT topics. It effectively translate the Tuya protocol to easy to use topics.

Using this script requires obtaining the device ID and local keys for each of your devices after they are configured via the Tuya/Smart Life or other Tuya compatible app. With this information it is possible to communicate locally with Tuya devices using Tuya protocol version 3.1, 3.2, 3.3, 3.4 and 3.5 without using the Tuya Cloud service, however, getting the keys requires signing up for a Tuya IOT developer account.

## Features

* Local operations without Tuya cloud
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

## Setup and config
----------

Install the necessary modules:
```
pip3 install -r requirements.txt
```

### Config
----------

Two things are required:

 1. `devices.json`
 2. `mqtt.ini`


#### mqtt.ini
----------

Example:

```ini
[mqtt]
hostname = 127.0.0.1
username = yourLogin
password = yourPassword
base_topic = tuya
```

#### devices.json
----------

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
