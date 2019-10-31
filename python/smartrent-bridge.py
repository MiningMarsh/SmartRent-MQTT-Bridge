import typing
import json
import asyncio
import mitmproxy.websocket
import paho.mqtt.client as mqtt
import ssl
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import device

#######################################################
#  Edit these:
devices = {
    # deviceId: ["friendly name", "device_mqtt_topic", "device type"]
    222222: ["Upstairs Thermostat", "upstairs_thermostat", "thermostat"],
}

#######################################################

MQTT_HOST = os.environ.get('MQTT_HOST')
MQTT_PORT = int(os.environ.get('MQTT_PORT'))
MQTT_USER = os.environ.get('MQTT_USER')
MQTT_PASS = os.environ.get('MQTT_PASS')
MQTT_TOPIC_PREFIX = os.environ.get('MQTT_TOPIC_PREFIX')

topics = {}
ws_message = ''
last_known_device_states = {}
availableDevices = device.Devices(devices)

attributeToCommandSuffix = {
    "cooling_setpoint": "/target/cool/temp",
    "heating_setpoint": "/target/heat/temp",
    "current_temp": "/current/temp",
    "current_humidity": "/current/humidity",
    "locked": "/status",
    "notifications": "/detail",
    "mode": "/current/mode",
}

def on_mqtt_connect(self, client, userdata, flags, rc):
        print("Connected to MQTT broker with result code "+str(rc))

def is_auto_mode(mode):
    return mode == 'auto' or mode == 'heat_cool'

mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(MQTT_USER, password=MQTT_PASS)
mqtt_client.on_connect = on_mqtt_connect

class SmartRentBridge:
    def __init__(self):
        mqtt_client.on_message = self.on_mqtt_message
        mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
        mqtt_client.loop_start()
        for key, value in devices.items():
            topics[value[1]] = [key, value[2]]
            if value[2] == "thermostat":
                mqtt_client.subscribe(MQTT_TOPIC_PREFIX+'/'+value[1]+'/target/cool/temp/set')
                mqtt_client.subscribe(MQTT_TOPIC_PREFIX+'/'+value[1]+'/target/heat/temp/set')
                mqtt_client.subscribe(MQTT_TOPIC_PREFIX+'/'+value[1]+'/mode/set')
            if value[2] == "lock":
                mqtt_client.subscribe(MQTT_TOPIC_PREFIX+'/'+value[1]+'/set')

    async def inject(self, flow: mitmproxy.websocket.WebSocketFlow):
        global ws_message
        while not flow.ended and not flow.error:
            if len(ws_message) > 0 :
               print('start publishing to websocket', ws_message)
               flow.inject_message(flow.server_conn, str(ws_message))
               print('publishing to websocket complete')
               ws_message = ''

            await asyncio.sleep(2)

    def on_mqtt_message(self, client, userdata, msg):
        global ws_message
        print('message from:', msg.topic)
        try:
        topic = msg.topic.split('/')
            device_id = topics[topic[1]][0]
        command = "/".join(topic[2:len(topic)])
        value = msg.payload.decode().lower()

            device = availableDevices.getDevice(device_id)
            message = device.serializeCommand(command, value)
            print(message)

            if not message:
                return

            last_known_device_states[device_id] = device
            ws_message = message
        except:
            print('failed publishing to web socket')

    def websocket_start(self, flow):
        asyncio.get_event_loop().create_task(self.inject(flow))

    def websocket_message(self, flow: mitmproxy.websocket.WebSocketFlow):
        message = flow.messages[-1]
        self.parse_message(message.content)

    def websocket_error(self, flow: mitmproxy.websocket.WebSocketFlow):
        print('websocket error')

    def parse_message(self, message):
        try:
        message_json = json.loads(message)
        msg_type = message_json[3]
        msg_data = message_json[4]
        if msg_type == "attribute_state":
                print('update from websocket', message)
                device_id = msg_data['device_id']
            attribute = msg_data['name']
            value = msg_data['last_read_state']
                last_known_device_state = last_known_device_states.get(device_id, None)
                if not last_known_device_state == None:
                    last_known_device_command = last_known_device_state.getLastCommand()
                    if not last_known_device_command == None and is_auto_mode(last_known_device_command.value) and type(last_known_device_command).__name__ == 'SetThermostatModeCommand':
                        print('thermostat mode is auto, so ignoring')
                        return

            commandSuffix = attributeToCommandSuffix[attribute]
                print("publishing to mqtt", MQTT_TOPIC_PREFIX+'/'+devices[device_id][1]+commandSuffix, value)
                mqtt_client.publish(MQTT_TOPIC_PREFIX+'/'+devices[device_id][1]+commandSuffix, value)
                print("publishing to mqtt complete")
            except:
            print('failed publishing to mqtt')

        return



addons = [SmartRentBridge()]
