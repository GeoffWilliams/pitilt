import logging
import time
import board
import busio
from adafruit_pca9685 import PCA9685
from adafruit_motor import servo
from settings import get_state

logger = logging.getLogger(__name__)

# Create the I2C bus interface
i2c = busio.I2C(board.SCL, board.SDA)

# Create the PCA9685 instance
pca = PCA9685(i2c)
pca.frequency = 50  # Standard servo frequency

# Servo on channel 0
servo_pan = servo.Servo(pca.channels[0])

# Servo on channel 1
servo_tilt = servo.Servo(pca.channels[1])

def get_angle_as_int(servo):
    return int(round(servo.angle))

def clamp(val, min_val, max_val):
    return max(min_val, min(val, max_val))

def pan(i: int, relative):
    current = get_angle_as_int(servo_pan)
    want = clamp(
        i + (current if relative else 0), 
        get_state().position.pan.min,
        get_state().position.pan.max
    )
    logger.debug(f"pan {i} degrees - {current} -> {want} degrees")
    move_servo(servo_pan, get_state().position.pan.step, get_state().position.pan.sleep, want)
    return want

def tilt(i: int, relative):
    current = get_angle_as_int(servo_tilt)
    want = clamp(
        i + (current if relative else 0), 
        get_state().position.tilt.min,
        get_state().position.tilt.max
    )
    logger.debug(f"tilt {i} degrees - {current} -> {want} degrees")
    move_servo(servo_tilt, get_state().position.tilt.step, get_state().position.tilt.sleep, want)
    return want


def move_servo(servo, step: int, sleep: float, want: int):
    current = get_angle_as_int(servo)
    if want > servo.angle:
        direction = +1
    else:
        direction = -1
    logger.info(f"move servo: {current} -> {want} in {step} degree steps")


    # +1/-1 to fix off-by-one
    # when we compare current position to want position, its important to note current
    # position comes from a float which we have rounded, eg 10.45993 to 10. This rounding
    # will prevent very small changes in want from working as in this example we might be
    # moving to 10 which the servo is basically already at - so we get a twitch or nothing
    # for this reason, move the servo by 2 degrees+ each time 
    for i in range(max(0, current), want + direction, step * direction):
        logger.debug(f"servo.angle set: {i}")
        servo.angle = i
        time.sleep(sleep)

def move_location(name):
    if not name in get_state().locations:
        logger.debug(f"requested invalid location: {name}")
        return {"status": "not found"}
    
    want_pan = clamp(
        get_state().locations[name].pan, 
        get_state().position.pan.min, 
        get_state().position.pan.max
    ) 
    
    want_tilt = clamp(
        get_state().locations[name].tilt, 
        get_state().position.tilt.min, 
        get_state().position.tilt.max
    ) 

    logger.info(f"move to location={name} | pan={want_pan} tilt={want_tilt}")

    move_servo(servo_pan, get_state().position.pan.step, get_state().position.pan.sleep, want_pan)
    move_servo(servo_tilt, get_state().position.tilt.step, get_state().position.tilt.sleep, want_tilt)


def get_current_tilt_position():
    return get_angle_as_int(servo_tilt)

def get_current_pan_position():
    return get_angle_as_int(servo_pan)

def home_servos():
    servo_pan.actuation_range = get_state().position.pan.max
    servo_tilt.actuation_range = get_state().position.tilt.max
    if servo_pan.angle == None:
        # after power off, angle state is lost
        logger.info("init servo_pan angle")
        servo_pan.angle = get_state().locations["home"].pan

    if servo_tilt.angle == None:
        logger.info("init servo_tilt angle")
        servo_tilt.angle = get_state().locations["home"].tilt

    move_location("home")    

def move_down():
    want = tilt(+2, True)
    return want

def move_up():
    want = tilt(-2, True)
    return want

def move_left():
    want = pan(+2, True)
    return want

def move_right():
    want = pan(-2, True)
    return want
