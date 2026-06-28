from dataclasses import dataclass, field, asdict
from typing import Dict
import socket
import yaml
import json
import logging
from logging.config import dictConfig
import sys
from constants import (
    LOG_CONFIG,
    DEFAULT_CONFIG_FILE,
    DEFAULT_STATE_FILE,
    DEFAULT_SERVO_SLEEP,
    DEFAULT_SERVO_STEP,
    AUTH_METHOD_PASSWORD
)
from pathlib import Path
from dacite import from_dict
import os

# from mqtt import homeassistant_register

#
# YAML - config file
#


@dataclass
class MqttConfig:
    mqtt_enabled: bool = False
    tls_enabled: bool = False
    auth_method: str = AUTH_METHOD_PASSWORD
    host: str = None
    port: int = None
    username: str = None
    password: str = None
    cacert_path: str = None
    client_cert_path: str = None
    client_key_path: str = None
    keyfile_password: str = ""
    # using wrong transport will give strange errors when using a valid MTLS certificate:
    # ssl.SSLError: [SSL: SSLV3_ALERT_UNSUPPORTED_CERTIFICATE] ssl/tls alert unsupported certificate (_ssl.c:2649)
    transport: str = "tcp"
    client_id: str = socket.getfqdn()
    ha_device_base_topic: str = "homeassistant"
    command_base_topic: str = "pitilt"


@dataclass
class PitiltConfig:
    username: str = "pitilt"
    password: str = None
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    uvicorn_log_level = "info"


@dataclass
class Config:
    pitilt: PitiltConfig
    mqtt: MqttConfig


#
# JSON - managed state (locations, servo limits)
#
@dataclass
class ServoPosition:
    # servo min allowed position
    min: int

    # servo max allowed position
    max: int

    # how much to move servo at a time (degrees)
    step: int

    # how long to sleep between moves (seconds)
    sleep: float

@dataclass
class Position:
    pan: ServoPosition
    tilt: ServoPosition

@dataclass
class Location:
    pan: int
    tilt: int

@dataclass
class State:
    position: Position
    locations: Dict[str, Location] = field(default_factory=dict)

logger = logging.getLogger(__name__)
log_config = None
config: Config = None
state: State = State(
    position=Position(
        pan=ServoPosition(
            min=0, 
            max=270, 
            step=DEFAULT_SERVO_STEP, 
            sleep=DEFAULT_SERVO_SLEEP
        ),
        tilt=ServoPosition(
            min=0, 
            max=135, 
            step=DEFAULT_SERVO_STEP, 
            sleep=DEFAULT_SERVO_SLEEP
        )
    ),
    locations={ 
        "home": Location(pan=60, tilt=45)
    } 
)

def setup_logging():
    global log_config
    logging_config_path = Path(LOG_CONFIG)
    if not logging_config_path.is_file():
        raise FileNotFoundError(f"Logging config file not found (missing file?): {LOG_CONFIG}")

    with open(logging_config_path, "r", encoding="utf-8") as f:
        log_config = json.load(f)
        dictConfig(log_config)



def load_state():
    global state

    state_file = get_state_file_path()
    if state_file.exists():

        with open(state_file, "r") as f:
            data = json.load(f)

        try:
            state = State(
                position=Position(
                    pan=ServoPosition(**data["position"]["pan"]),
                    tilt=ServoPosition(**data["position"]["tilt"])
                ),
                locations={name: Location(**loc) for name, loc in data["locations"].items()}
            )
            logger.debug(f"loaded: {state_file}")
        except TypeError as e:
            sys.exit(f"{state_file} bad. Delete/fix it, then try again: {e}")
    else:
        # file no exist, create the defaults
        save_state()

def save_state():
    logger.debug(f"locations in state: {','.join(state.locations.keys())}")
    state_file = get_state_file_path()
    if not state_file.exists():
        logger.info(f"state file does not exist, creating: {state_file}")

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(asdict(state), f, indent=2)
        logger.debug(f"saved {state_file}")

def load_config():
    global config
    config_file = get_config_file_path()

    if not config_file.exists():
        sys.exit(f"no such config file: {config_file}")

    with open(config_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        config = from_dict(data_class=Config, data=data)


def setup():
    """load config and state"""
    load_config()
    setup_logging()
    
    load_state()

# state and config object definitive version is in this module - prevent split
# brain/working on wrong reference with accessors...
def get_config():
    return config

def get_state():
    return state

config_file=None
state_file=None

def get_config_file_path():
    global config_file
    if not config_file:
        config_file = Path(os.environ.get("PITILT_CONFIG_FILE", DEFAULT_CONFIG_FILE))
        logger.info(f"Using config_file={config_file}")

    return config_file

def get_state_file_path():
    global state_file
    if not state_file:
        state_file = Path(os.environ.get("PITILT_STATE_FILE", DEFAULT_STATE_FILE))
        logger.info(f"Using state_file={state_file}")

    return state_file
    