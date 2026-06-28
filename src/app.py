import threading
from control import home_servos
from mqtt import start_mqtt, mqtt_shutdown_event
from settings import setup, log_config
import logging
from api import start_api, api_shutdown_event
import time
import sys


logger = logging.getLogger(__name__)


if __name__ == "__main__":
    setup()
    log_config = log_config
    logger.debug("Debug mode enabled")

    home_servos()
    
    api_thread = threading.Thread(target=start_api, daemon=True)
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    
    api_thread.start()
    mqtt_thread.start()

    # wait for shutdown signal from threads
    shutdown = False
    while not shutdown:
        if mqtt_shutdown_event.is_set():
            logger.error("MQTT thread requested shutdown - triggering exit")
            shutdown = True
        if api_shutdown_event.is_set():
            logger.error("API thread requested shutdown - triggering exit")
            shutdown = True

        time.sleep(0.1)

    sys.exit("shutting down system")

    

    # keep main thread alive
    mqtt_thread.join()
    api_thread.join()    

