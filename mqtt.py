from dataclasses import dataclass, asdict
from paho.mqtt import client as mqtt_client
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes 
import logging
import ssl
from settings import get_config, get_state
from constants import (
    APP_NAME,
    API_VERSION,
    AUTH_METHOD_PASSWORD,
    AUTH_METHOD_MTLS
)
from version import VERSION
import time
from pathlib import Path
import json
from control import move_location, move_down, move_left, move_right, move_up
import threading


COMMAND_MOVE_REL = "move_rel"
COMMAND_LOCATION = "location"
MOVE_REL_LEFT = "left"
MOVE_REL_RIGHT = "right"
MOVE_REL_UP = "up"
MOVE_REL_DOWN = "down"



ha_reregister_event = threading.Event()
mqtt_shutdown_event = threading.Event()


@dataclass
class MqttMessage:
    command: str
    argument: str



logger = logging.getLogger(__name__)

def worker():
    while True:
        # wait until signaled
        ha_reregister_event.wait()
        ha_reregister_event.clear()  # reset the flag
        print("Re-registering with Home Assistant...")
        homeassistant_register()
        # call your actual re-registration function here
        # e.g., re_register_ha()
        time.sleep(0.1)  # optional: prevent busy looping

#
# MQTT callbacks
#

def on_message(client, userdata, msg):
    logger.debug("on_message")
    # print(msg.topic+" "+str(msg.payload))
    data = None
    try:
        data = json.loads(msg.payload)
    except json.JSONDecodeError as e:
        logger.error(f"invalid JSON: {e} payload={msg.payload}")
        return
    
    mqttMessage = MqttMessage(**data)
    if mqttMessage.command == COMMAND_MOVE_REL and mqttMessage.argument == MOVE_REL_UP:
        move_up()
    elif mqttMessage.command == COMMAND_MOVE_REL and mqttMessage.argument == MOVE_REL_DOWN:
        move_down()
    elif mqttMessage.command == COMMAND_MOVE_REL and mqttMessage.argument == MOVE_REL_LEFT:
        move_left()
    elif mqttMessage.command == COMMAND_MOVE_REL and mqttMessage.argument == MOVE_REL_RIGHT:
        move_right()
    elif mqttMessage.command == COMMAND_LOCATION:
        move_location(mqttMessage.argument)
    else:
        logger.error(f"invalid command={mqttMessage.command}")
        

def on_connect(client, userdata, flags, rc, properties):
    logger.info("on_connect")
    if rc == 0:
        logger.info("Connected to MQTT Broker!")
    else:
        logger.info("Failed to connect, return code %d\n", rc)

def on_publish(a, b, c):
    logger.debug("on_publish")

def on_subscribe(s, userdata, mid, reasoncodes, properties):
    logger.debug("on_subscribe")

def on_disconnect(client, userdata, flags, rc, properties=None):
    logger.debug("on_disconnect")
    logger.info("Disconnected with result code: %s", rc)
    reconnect_delay = 10
    while True:
        logging.info("Reconnecting in %d seconds...", reconnect_delay)
        time.sleep(reconnect_delay)

        try:
            client.reconnect()
            logging.info("Reconnected successfully!?")
            return
        except Exception as err:
            logging.error("%s. Reconnect failed. Retrying...", err)


def get_device_command_topic():
    config = get_config()
    return f"{config.mqtt.command_base_topic}/{config.mqtt.client_id}/command"

# best docs: https://stevessmarthomeguide.com/adding-an-mqtt-device-to-home-assistant/
# <discovery_prefix>/<component>/[<node_id>/]<object_id>/config
# eg
# homeassistant/sensor/plant_sensor_1/temperature/configs
# homeassistant/device_automation/0x90fd9ffffedf1266/action_arrow_left_click/config
def homeassistant_register(client):
    config = get_config()
    ha_base_topic = f"{config.mqtt.ha_device_base_topic}/button/{config.mqtt.client_id}"
    # register a subset of commands as MQTT commands

    #
    # move_rel
    # 
    for direction in [MOVE_REL_LEFT, MOVE_REL_RIGHT, MOVE_REL_UP, MOVE_REL_DOWN]:
        payload = MqttMessage(COMMAND_MOVE_REL, direction)
        payload_str = json.dumps(asdict(payload))
        registration = {
            "name": f"Move {direction}",
            "unique_id": f"pitilt_{config.mqtt.client_id}_move_{direction}",
            "payload_press": payload_str,
            "command_topic": get_device_command_topic(),
            "qos": 2,
            "device": {
                "identifiers": [
                    config.mqtt.client_id
                ],
                "configuration_url": f"http://{config.mqtt.client_id}:{config.pitilt.port}",
                "name": config.mqtt.client_id,
                "sw_version": f"{APP_NAME} {VERSION}",
                "model": f"{APP_NAME} Version {VERSION} API {API_VERSION}",
                "manufacturer": "Geoff Williams"
            }
        }
        ha_topic = f"{ha_base_topic}/{direction}/config"
        registration_str = json.dumps(registration)
        logger.info(f"register homeassistant device: topic={ha_topic}\n{registration_str}")
        client.publish(ha_topic, registration_str, 1, retain=True)

    #
    # location
    #
    for location_name in get_state().locations.keys():
        payload = MqttMessage(COMMAND_LOCATION, location_name)
        payload_str = json.dumps(asdict(payload))
        registration = {
            "name": f"Location: {location_name}",
            "unique_id": f"pitilt_{config.mqtt.client_id}_location_{location_name}",
            "payload_press": payload_str,
            "command_topic": get_device_command_topic(),
            "qos": 2,
            "device": {
                "identifiers": [
                    config.mqtt.client_id
                ],
                "configuration_url": f"http://{config.mqtt.client_id}:{config.pitilt.port}",
                "name": config.mqtt.client_id,
                "sw_version": f"{APP_NAME} {VERSION}",
                "model": f"{APP_NAME} Version {VERSION} API {API_VERSION}",
                "manufacturer": "Geoff Williams"
            }
        }
        ha_topic = f"{ha_base_topic}/location_{location_name}/config"
        registration_str = json.dumps(registration)
        logger.info(f"register homeassistant device: topic={ha_topic}\n{registration_str}")
        client.publish(ha_topic, registration_str, 1, retain=True)

#
# MQTT client config
#

def start_mqtt():
    config = get_config()
    if not config.mqtt.mqtt_enabled:
        logger.info("mqtt disabled in config file")

    logger.info("configuring MQTT...")

    client = mqtt_client.Client(
        client_id=config.mqtt.client_id,
        transport=config.mqtt.transport,
        protocol=mqtt_client.MQTTv5
    )

    if config.mqtt.tls_enabled and config.mqtt.auth_method == AUTH_METHOD_MTLS:
        missing_files = False
        if not config.mqtt.cacert_path or not Path(config.mqtt.cacert_path).exists():
            logger.error(f"missing file for cacart_path: {config.mqtt.cacert_path}")
            missing_files = True

        if not config.mqtt.client_cert_path or not Path(config.mqtt.client_cert_path).exists():
            logger.error(f"missing file for client_cert_path: {config.mqtt.client_cert_path}")
            missing_files = True      

        if not config.mqtt.client_key_path or not Path(config.mqtt.client_key_path).exists():
            logger.error(f"missing file for client_key_path: {config.mqtt.client_key_path}")
            missing_files = True   

        if missing_files:
            shutdown_thread("MQTT MTLS setup failed - incorrect/missing files")

        logger.info(f"MTLS config: "
            f"cacert_path={config.mqtt.cacert_path}, "
            f"client_cert_path={config.mqtt.client_cert_path}, "
            f"client_key_path={config.mqtt.client_key_path}, "
            f"keyfile_password={bool(config.mqtt.keyfile_password)}"
        )

        client.tls_set(
            ca_certs=config.mqtt.cacert_path,
            cert_reqs=ssl.CERT_REQUIRED,
            certfile=config.mqtt.client_cert_path,
            keyfile=config.mqtt.client_key_path,
            keyfile_password=config.mqtt.keyfile_password
        )

    elif config.mqtt.tls_enabled:
        if config.mqtt.cacert_path and not Path(config.mqtt.cacert_path).exists():
            shutdown_thread(f"MQTT MTLS cacart_path must exist if specified: {config.mqtt.cacert_path}")
        logger.info(f"TLS config: cacert_path={config.mqtt.cacert_path}, ")
        client.tls_set(
            ca_certs=config.mqtt.cacert_path,
            cert_reqs=ssl.CERT_REQUIRED,
        )
    elif config.mqtt.auth_method == AUTH_METHOD_PASSWORD:
        logger.info("MQTT password authentication - "
            f"username={config.mqtt.username},"
            f"password={config.mqtt.username}"
        )
        client.username_pw_set(
            config.mqtt.username, 
            config.mqtt.password
        )
    else:
        shutdown_thread("MQTT authentication is mandatory")
    
    
    #
    # plug-in callbacks
    #

    client.on_message = on_message
    client.on_connect = on_connect
    client.on_publish = on_publish
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect

    properties=Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval=30*60 # in seconds

    #
    # Connect...
    #
    logger.info(f"connecting to {config.mqtt.host}")
    client.connect(
        config.mqtt.host, 
        port=config.mqtt.port,
        #clean_start=MQTT_CLEAN_START_FIRST_ONLY,
        #properties=properties,
        keepalive=60
    )
    # client.loop_start()
    logger.info("connected???")
    # client.loop_start()

    # QOS - for your reference
    # At most once (QoS 0): QoS 0 offers "fire and forget" messaging with no acknowledgment from the receiver.
    # At least once (QoS 1): QoS 1 ensures that messages are delivered at least once by requiring a PUBACK acknowledgment.
    # Exactly once (QoS 2): QoS 2 guarantees that each message is delivered exactly once by using a four-step handshake (PUBLISH, PUBREC, PUBREL, PUBCOMP). 

    homeassistant_register(client)
    client.subscribe(get_device_command_topic())

    # #,0,properties=properties)
    # #result = client.publish("test",'qos=0 Cedalo Mosquitto is awesome',0,properties=properties)
    # #result = client.publish("test",'qos=1 Cedalo Mosquitto is awesome',1,properties=properties)
    # #result = client.publish("test",'qos=2 Cedalo Mosquitto is awesome',2,properties=properties)
    # status = result[0]
    # if status == 0:
    #     print(f"Send OK")
    # else:
    #     print(f"Failed to send message to topic")
    # client.loop_stop()
    
    # client.loop_forever()
    # client.loop_forever()
    client.loop_start()
    while True:
        # wait until signaled
        ha_reregister_event.wait()
        ha_reregister_event.clear()  # reset the flag
        print("Re-registering with Home Assistant...")
        homeassistant_register(client)
        # call your actual re-registration function here
        # e.g., re_register_ha()
        time.sleep(0.1)  # optional: prevent busy looping




def shutdown_thread(msg):
    logger.error(msg)
    mqtt_shutdown_event.set()
