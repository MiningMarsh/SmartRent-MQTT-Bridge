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

#######################################################

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

attributeToCommandSuffix = {
    "heating_setpoint": "/target/temp",
    "cooling_setpoint": "/target/temp",
    "current_temp": "/current/temp",
    "current_humidity": "/current/humidity",
    "locked": "/status",
    "notifications": "/detail",
    "mode": "/current/mode",
}

def on_mqtt_connect(self, client, userdata, flags, rc):
        print("Connected to MQTT broker with result code "+str(rc))

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
                mqtt_client.subscribe(MQTT_TOPIC_PREFIX+'/'+value[1]+'/target/cool')
                mqtt_client.subscribe(MQTT_TOPIC_PREFIX+'/'+value[1]+'/target/heat')
            if value[2] == "lock":
                mqtt_client.subscribe(MQTT_TOPIC_PREFIX+'/'+value[1]+'/set')

    async def inject(self, flow: mitmproxy.websocket.WebSocketFlow):
        global ws_message
        while not flow.ended and not flow.error:
            if len(ws_message) > 0 :
               flow.inject_message(flow.server_conn, str(ws_message))
               print(ws_message)
               ws_message = ''

            await asyncio.sleep(2)

    def on_mqtt_message(self, client, userdata, msg):
        global ws_message
        topic = msg.topic.split('/')
        device_id = str(topics[topic[1]][0])
        device_type = topics[topic[1]][1]
        command = topic[2]
        value = msg.payload.decode().lower()
        # Handle Thermostat Commands
        if device_type == "thermostat":
            if command == "/target/heat/set":
                ws_message = '["6","69","devices:'+device_id+'","update_attributes",{"device_id":"'+device_id+'","attributes":[{"name":"mode","value":"heat"},{"name":"heating_setpoint","value":"'+value+'"}]}]'
            if command == "/target/cool/set":
                ws_message = '["6","69","devices:'+device_id+'","update_attributes",{"device_id":"'+device_id+'","attributes":[{"name":"mode","value":"cool"},{"name":"cooling_setpoint","value":"'+value+'"}]}]'
        # Handle Lock Commands
        if device_type == "lock":
           ws_message = '["null","null","devices:'+device_id+'","update_attributes",{"device_id":"'+device_id+'","attributes":[{"name":"locked","value":"'+value+'"}]}]'

    #####
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
            print(msg_data)
            attribute = msg_data['name']
            device_id = msg_data['device_id']
            value = msg_data['last_read_state']
            commandSuffix = attributeToCommandSuffix[attribute]
                print("trying to publish", MQTT_TOPIC_PREFIX+'/'+devices[device_id][1]+commandSuffix)
                mqtt_client.publish(MQTT_TOPIC_PREFIX+'/'+devices[device_id][1]+commandSuffix, value)
            except:
                print('failed publishing')

        return



addons = [SmartRentBridge()]
