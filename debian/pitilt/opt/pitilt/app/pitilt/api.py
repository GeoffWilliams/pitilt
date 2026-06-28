#
# API/HTTP verb reasoning
#
# * GET must not change state
# * POST is for when a new entity/state is create (relative movement, new location, etc)
# * PUT is for when we transition to a known state (move to named location, absolute position, etc)
# * DELETE bye :)

from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn

import json
from dataclasses import asdict
from typing import Optional

import secrets
from settings import (
    Location, 
    get_state, 
    save_state, 
    log_config,
    get_config
)
import logging
from pydantic import BaseModel

from control import (
    pan, 
    tilt, 
    move_location, 
    get_current_pan_position, 
    get_current_tilt_position,
    move_down,
    move_left,
    move_right,
    move_up
)
from version import VERSION

from constants import (
    API_VERSION,
    APP_NAME,
)
from mqtt import ha_reregister_event
import threading


FIELD_STATUS = "status"
VALUE_OK     = "ok"
STATUS_GOOD = {FIELD_STATUS: VALUE_OK}


logger = logging.getLogger(__name__)
router = APIRouter(prefix=f"/api/{API_VERSION}")
app = FastAPI()
security = HTTPBasic()

api_shutdown_event = threading.Event()




class Value(BaseModel):
    value: int | float


def save_state_and_update_ha():
    save_state()
        
    # re-register in home assistant (for new locations)
    ha_reregister_event.set()
    


def require_login(credentials: HTTPBasicCredentials = Depends(security)):

    correct_username = secrets.compare_digest(credentials.username, get_config().pitilt.username)
    correct_password = secrets.compare_digest(credentials.password, get_config().pitilt.password)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username




#
# API - Info
#

@app.get("/")
def root():
    return {APP_NAME: VERSION}

@router.get("/locations")
def list_locations(_=Depends(require_login)):
    return json.dumps(asdict(get_state().locations), indent=2)

@router.get("/pan")
def get_pan(_=Depends(require_login)):
    return {pan: get_current_tilt_position()}

@router.get("/tilt")
def get_tilt(_=Depends(require_login)):
    return {tilt: get_current_tilt_position()}


#
# API - Named Locations
#

@router.put("/locations/{name}")
def api_move_location(name, _=Depends(require_login)):
    move_location(name)
    return STATUS_GOOD

@router.post("/locations/{name}")
def save_location(name, _=Depends(require_login)):
    get_state().locations[name] = Location(
        pan=get_current_pan_position(),
        tilt=get_current_tilt_position()
    )
    save_state_and_update_ha()
    return STATUS_GOOD

@router.delete("/locations/{name}")
def delete_location(name, _=Depends(require_login)):
    del get_state().locations[name]
    save_state_and_update_ha()
    return STATUS_GOOD

#
# API - Axis limits and settings
#
@router.put("/tilt/sleep")
def tilt_sleep(value: Value, _=Depends(require_login)):
    get_state().position.tilt.sleep = value.value

    save_state_and_update_ha()
    return STATUS_GOOD

@router.put("/tilt/step")
def tilt_step(value: Value, _=Depends(require_login)):
    get_state().position.tilt.step = value.value

    save_state_and_update_ha()
    return STATUS_GOOD

@router.put("/tilt/max")
def tilt_max(value: Optional[Value] = None, _=Depends(require_login)):
    if value and value.value:
        get_state().position.tilt.max = value.value
    else:
        get_state().position.tilt.max = get_current_tilt_position()

    save_state_and_update_ha()
    return STATUS_GOOD

@router.put("/tilt/min")
def tilt_min(value: Optional[Value] = None, _=Depends(require_login)):
    if value and value.value:
        get_state().position.tilt.min = value.value
    else:
        get_state().position.tilt.min = get_current_tilt_position()
    save_state_and_update_ha()
    return STATUS_GOOD

@router.put("/pan/sleep")
def pan_sleep(value: Value, _=Depends(require_login)):
    get_state().position.pan.sleep = value.value

    save_state_and_update_ha()
    return STATUS_GOOD

@router.put("/pan/step")
def pan_step(value: Value, _=Depends(require_login)):
    get_state().position.pan.step = value.value

    save_state_and_update_ha()
    return STATUS_GOOD

@router.put("/pan/max")
def pan_max(value: Optional[Value] = None, _=Depends(require_login)):
    if value and value.value:
        get_state().position.pan.max = value.value
    else:
        get_state().position.pan.max = get_current_pan_position()
    save_state_and_update_ha()
    return STATUS_GOOD

@router.put("/pan/min")
def pan_min(value: Optional[Value] = None, _=Depends(require_login)):
    if value and value.value:
        get_state().position.pan.min = value.value
    else:
        get_state().position.pan.min = get_current_pan_position()
    save_state_and_update_ha()
    return STATUS_GOOD

#
# API - Absolute move axis
#

@router.put("/pan")
def api_pan(value: Value, relative=False):
    pan(value.value, relative)
    return STATUS_GOOD

@router.put("/tilt")
def api_tilt(value: Value, relative=False):
    tilt(value.value, relative)
    return STATUS_GOOD

#
# API - Relative move axis
#

# tilt is inverted
@router.post("/down")
def api_move_down(_=Depends(require_login)):
    return {**STATUS_GOOD, "tilt": move_down()}


@router.post("/up")
def api_move_up(_=Depends(require_login)):
    return {**STATUS_GOOD, "tilt": move_up()}


@router.post("/left")
def api_move_left(_=Depends(require_login)):
    return {**STATUS_GOOD, "pan": move_left()}


@router.post("/right")
def api_move_right(_=Depends(require_login)):
    return {**STATUS_GOOD, "pan": move_right()}


app.include_router(router)

def start_api():
    uvicorn.run(
        app, 
        host=get_config().pitilt.host,
        port=get_config().pitilt.port,    
        log_config=log_config,
        log_level=get_config().pitilt.uvicorn_log_level
    )

def shutdown_thread(msg):
    logger.error(msg)
    api_shutdown_event.set()