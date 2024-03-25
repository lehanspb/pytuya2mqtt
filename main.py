#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Python daemon for reading and controlling Tuya WiFi devices and Tuya devices behind Zigbee or BLE gateways
Reporting statuses and controlling via MQTT
"""

# pylint: disable=no-member
# pylint: disable=unused-argument


import configparser
import dataclasses
from dataclasses import asdict, fields
import json
import logging
import os
from os.path import join, abspath, dirname
import sys
import threading
import time
from typing import List
from paho.mqtt import publish
import paho.mqtt.client as mqtt
import tinytuya
import platform
import argparse
import daemon

MQTT_INI = 'mqtt.ini'
DEVICES_JSON = 'devices.json'
PROJECT_NAME = 'pytuya2mqtt'

# Devices will close the connection if they do not receve data every 30 seconds
# Sending heartbeat packets every 9 seconds gives some wiggle room for lost packets or loop lag
PING_TIME = 9

# Option - also poll
POLL_TIME = 60

# Logger settings
logger = logging.getLogger(__name__)
sh = logging.StreamHandler()
logger.addHandler(sh)
logger.setLevel(logging.INFO)

if os.environ.get('DEBUG'):
	logger.setLevel(logging.DEBUG)

if os.environ.get('TINYTUYA_DEBUG'):
	tinytuya.set_debug()

# Uncomment if you want to see full debug
# tinytuya.set_debug()

MQTT_HOST = None
MQTT_USER = None
MQTT_PASSWORD = None
MQTT_TOPIC = None
mqtt_auth = None
TIME_SLEEP = 5

@dataclasses.dataclass
class Device:
	name: str
	id: str
	ip: str
	key: str
	version: float
	subDevices: dict = dataclasses.field(default=None)
	cid: str = dataclasses.field(default=None)
	parent: str = dataclasses.field(default=None)
	dps: dict = dataclasses.field(default=None)
	tuya: tinytuya.OutletDevice = dataclasses.field(default=None)
	gw: tinytuya.OutletDevice = dataclasses.field(default=None)

deviceslst = {}

def read_config() -> List[Device]:
	'''
	Read & parse mqtt.ini and devices.json
	'''
	logger.info(PROJECT_NAME + " daemon started")

	mqtt_conf_path = abspath(join(dirname(__file__), MQTT_INI))
	devices_conf_path = abspath(join(dirname(__file__), DEVICES_JSON))

	for fn in (DEVICES_JSON, devices_conf_path):
		if os.path.exists(fn):
			devices_conf_path = fn
			break

	if devices_conf_path is None:
		logger.error('Missing devices.json')
		sys.exit(2)

	for fn in (MQTT_INI, mqtt_conf_path):
		if os.path.exists(fn):
			mqtt_conf_path = fn
			break

	if mqtt_conf_path is None:
		logger.error('Missing mqtt.ini')
		sys.exit(2)

	try:
		# Read devices.json
		with open(devices_conf_path, encoding='utf8') as f:
			devlist = json.load(f)
	except json.decoder.JSONDecodeError:
		logger.error('Invalid devices.json!')
		sys.exit(3)

	# Create a dict of Device objects from devices.json
	devices = {}
	global deviceslst

	for d in devlist:
		if 'subDevices' in d.keys():
			devices.update({d['id']: Device(d['name'], d['id'], d['ip'], d['key'], d['version'], d['subDevices'])})
			for s in d['subDevices']:
				devices.update({s['id']: Device(s['name'], s['id'], d['ip'], d['key'], d['version'], None, s['cid'], d['id'])})
				deviceslst.update({s['cid']: s['name']})
		else:
			devices.update({d['id']: Device(d['name'], d['id'], d['ip'], d['key'], d['version'])})


	# Read mqtt.ini
	cfg = configparser.ConfigParser(inline_comment_prefixes='#')

	with open(mqtt_conf_path, encoding='utf8') as f:
		cfg.read_string(f.read())

	try:
		for section in cfg.sections():
			parts = section.split(' ')

			if parts[0] == 'mqtt':
				global MQTT_HOST  # pylint: disable=global-statement
				global MQTT_USER
				global MQTT_PASSWORD
				global MQTT_TOPIC
				global mqtt_auth
				MQTT_HOST = dict(cfg.items(section))['hostname']
				MQTT_USER = dict(cfg.items(section))['username']
				MQTT_PASSWORD = dict(cfg.items(section))['password']
				MQTT_TOPIC = dict(cfg.items(section))['base_topic']
				mqtt_auth = { 'username': MQTT_USER, 'password': MQTT_PASSWORD }

	except KeyError:
		logger.error('Malformed mqtt section in mqtt.ini')
		sys.exit(3)
	except IndexError:
		logger.error('Malformed section name in mqtt.ini')
		sys.exit(3)

	return devices.values()



def on_connect(client, userdata, _1, _2, _3):
	'''
	On broker connected, subscribe to the command topics
	'''
	
	command_topic = f"{MQTT_TOPIC}/{userdata['device'].name}/dps/+/command"
	client.subscribe(command_topic, 0)
	logger.info('Subscribed to %s', command_topic)


def start_daemon(args):
	"""function to start daemon in context, if requested
	"""

	context = daemon.DaemonContext(
		working_directory='/var/tmp',
		stdout=sys.stdout,
		stderr=sys.stderr,
		stdin=sys.stdin
	)

	with context:
		for device in read_config():
			# Starting polling this device on a thread
			t = threading.Thread(target=poll, args=(device, args.verbose))
			t.start()


def on_message(_, userdata: dict, msg: bytes):
	'''
	On command message received, take some action

	Params:
		client:    paho.mqtt.client
		userdata:  Arbitrary data passed on this Paho event loop
		msg:       Message received on MQTT topic sub
	'''
	logger.debug('Received %s on %s', msg.payload, msg.topic)
	if not msg.payload:
		return

	device: Device = userdata['device']

	# Set status or value
	if msg.topic.endswith('/command'):
		dps = int(msg.topic.split('/')[3].strip())
		val = msg.payload.decode("utf-8")

		cmnd_list_on = ['on', 'true']
		cmnd_list_off = ['off', 'false']
		cmnd_list = cmnd_list_on + cmnd_list_off
		if val.lower() in [x.lower() for x in cmnd_list]:
			val = True if val.lower() in [x.lower() for x in cmnd_list_on] else False
			device.tuya.set_status(val, switch=dps)
			logger.debug('Command %s to %s', dps, val)
		elif val.isalpha():
			device.tuya.set_value(dps, val)
			logger.debug('Setting %s to %s', dps, val)
		else:
			val = int(float(val))
			device.tuya.set_value(dps, val)
			logger.debug('Setting %s to %s', dps, val)

	device.tuya.updatedps(index=[dps], nowait=True)



def poll(device: Device, verbose=False):
	'''
	Start MQTT threads, and then poll a device for status updates.

	Params:
		device:  An instance of Device dataclass
		verbose: Boolean command line argument (-v or --verbose)
	'''

	if verbose: logger.setLevel(logging.DEBUG)

	if device.parent:
		logger.debug('Connecting to GW %s with protocol version %s', device.parent, device.version)
		device.gw = tinytuya.Device(device.id, address=device.ip, local_key=device.key, persist=True, version=device.version)
		logger.debug('Connecting to subdevice %s with cid %s via %s', device.name, device.cid, device.parent)
		device.tuya = tinytuya.OutletDevice(device.id, cid=device.cid, parent=device.gw)
	else:
		logger.debug('Connecting to %s with protocol version %s', device.ip, device.version)
		device.tuya = tinytuya.OutletDevice(device.id, device.ip, device.key)
		device.tuya.set_version(device.version)
		device.tuya.set_socketPersistent(True)

	# Connect to the broker and hookup the MQTT message event handler
	# client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, device.id, userdata={'device': device})
	client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, device.id, userdata={'device': device})
	client.on_connect = on_connect
	client.on_message = on_message
	client.username_pw_set(username=MQTT_USER, password=MQTT_PASSWORD)
	client.connect(MQTT_HOST)
	client.loop_start()
	
	logger.debug(" > Send Request for Status < ")
	device.tuya.status(nowait=True)

	logger.debug(" > Begin Monitor Loop <")
	pingtime = time.time() + PING_TIME
	polltime = time.time() + POLL_TIME

	read_and_publish_status(device)

	try:
		while True:
			read_and_publish_dps_data(device, pingtime, polltime)
			time.sleep(TIME_SLEEP)
	finally:
		client.loop_stop()
		logger.info('fin')


def read_and_publish_status(device: Device):
	'''
	Fetch device current status and values from all available DPS and publish on MQTT

	Params:
		device:  An instance of Device dataclass
	'''
	data = device.tuya.receive()

	if data and 'Err' in data:
		logger.debug(" > Status request returned an error < ")
		data = device.tuya.status()
		logger.debug('Status. Received Payload:  %s', data)

	elif data and 'dps' in data:
		logger.debug(" > Send Request for Status < ")
		data = device.tuya.status()

		logger.debug('Status. Received Payload:  %s', data)
		dps = data['dps']
		msgs = [
			(f'{MQTT_TOPIC}/{device.name}/online', 'online')
		]

		for k in dps:
			msgs.append(
				(f'{MQTT_TOPIC}/{device.name}/dps/{k}/state', dps[k])
			)
		logger.debug('PUBLISH: %s', msgs)
		publish.multiple(msgs, hostname=MQTT_HOST, auth=mqtt_auth)



def read_and_publish_dps_data(device: Device, pingtime, polltime):
	'''
	Fetch DPS values from the device and publish on MQTT

	Params:
		device:  An instance of Device dataclass
		pingtime: timeout of sending hearbeat
		polltime: polling timeout
	'''

	# data = device.tuya.receive()
	# if device.gw:
	# 	data = device.gw.receive()
	# 	if data and 'Err' in data:
	# 		data = device.gw.status()
	# 		logger.debug('DPS GW Data. Received Error Payload:  %s', data)
	# 	elif data and 'Err' not in data:
	# 		logger.info('DPS GW Data. Received Payload: %r' % data)
	# else:
	# 	data = device.tuya.receive()
	# 	if data and 'Err' in data:
	# 		data = device.tuya.status()
	# 		logger.debug('DPS Tuya Data. Received Error Payload:  %s', data)
	# 	elif data and 'Err' not in data:
	# 		logger.info('DPS Tuya Data. Received Payload: %r' % data)
	data = device.tuya.receive()
	if data and 'Err' in data:
		data = device.tuya.status()
	elif data and 'Err' not in data:
		logger.info('Received Payload: %r' % data)
	# if data and 'Err' in data:
	# 	data = device.tuya.status()
	# 	logger.debug('DPS Tuya Data. Received Error Payload:  %s', data)
	# elif data and 'Err' not in data:
	# 	logger.info('DPS Tuya Data. Received Payload: %r' % data)

	if( pingtime <= time.time() ):
		pingtime = time.time() + PING_TIME
		# Send keep-alive heartbeat
		if device.gw:
			logger.debug(" > Send Heartbeat Ping to GW Device < ")
			device.gw.heartbeat(nowait=True)	
		else:
			logger.debug(" > Send Heartbeat Ping < ")
			device.tuya.heartbeat(nowait=True)

	# Option - Poll for status
	if( polltime <= time.time() ):
		polltime = time.time() + POLL_TIME

		# Option - Some plugs require an UPDATEDPS command to update their power data points
		if False:
			logger.info(" > Send DPS Update Request < ")

			# # Some Tuya devices require a list of DPs to update
			# payload = d.generate_payload(tinytuya.UPDATEDPS,['18','19','20'])
			# data = d.send(payload)
			# logger.debug('Received Payload: %r' % data)

			# # Other devices will not accept the DPS index values for UPDATEDPS - try:
			# payload = d.generate_payload(tinytuya.UPDATEDPS)
			# data = d.send(payload)
			# logger.debug('Received Payload: %r' % data)

	msgs = []

	if data and 'dps' in data and 'cid' in data:
		for cid, name in deviceslst.items():
			if cid == data['cid']:
				msgs = [
					(f'{MQTT_TOPIC}/{name}/online', 'online')
				]
				dps = data['dps']
				for k in dps:
					msgs.append(
						(f'{MQTT_TOPIC}/{name}/dps/{k}/state', dps[k])
					)
	elif data and 'dps' in data and 'cid' not in data:
		dps = data['dps']
		msgs = [
			(f'{MQTT_TOPIC}/{device.name}/online', 'online')
		]
		for k in dps:
			msgs.append(
				(f'{MQTT_TOPIC}/{device.name}/dps/{k}/state', dps[k])
			)

	if msgs:
		logger.info('PUBLISH: %s', msgs)
		publish.multiple(msgs, hostname=MQTT_HOST, auth=mqtt_auth)


def send_updatedps(device: Device):
	'''
	Some plugs require an UPDATEDPS command to update their power data points

	Params:
		device:  An instance of Device dataclass
	'''

	device.tuya.updatedps(index=[1], nowait=True)


def main():
	"""Main function call
	"""

	logger.info(" ")
	logger.info(f'{PROJECT_NAME} started')
	logger.info(" ")

	parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument('-c', '--config', default=MQTT_INI, help="configuration file")
	parser.add_argument('-d', '--daemon', action='store_true', help="run as daemon")
	# parser.add_argument('-p', '--pid-file', default=PID_FILE)
	parser.add_argument('-v', '--verbose', action='store_true', help="verbose messages")

	cmdline_args = parser.parse_args()

	logger.info(cmdline_args)

	if cmdline_args.daemon:
			start_daemon(cmdline_args)
	else:
		for device in read_config():
			# Starting polling this device on a thread
			t = threading.Thread(target=poll, args=(device, cmdline_args.verbose))
			t.start()


if __name__ == '__main__':
	main()
	sys.exit(0)
