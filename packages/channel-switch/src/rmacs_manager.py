import threading
import signal
import sys
import os
import asyncio
import queue
from nats.aio.client import Client as NATS
import time
import yaml
from src.rmacs_server_fsm import main as rmacs_server_main
from src.rmacs_client_fsm import main as rmacs_client_main


parent_directory = os.path.abspath(os.path.dirname(__file__))
if parent_directory not in sys.path:
   sys.path.append(parent_directory)

from config import create_default_config, load_config
from logging_config import logger
from rmacs_util import get_interface_operstate, get_channel_bw, kill_process_by_pid, run_command
config_file_path = '/etc/meshshield/rmacs_config.yaml'
CONFIG_DIR = "/etc/meshshield"

# Global variable to handle shutdown
graceful_shutdown = False

nats_msg_queue = queue.Queue()



async def connect_nats(nats_server_url):
    """
    Connect to the NATS server.

    Args:
        nats_server_url (str): URL of the NATS server.

    Returns:
        NATS: An instance of the connected NATS client.
    """
    nc = NATS()
    try:
        await nc.connect(nats_server_url)
        logger.info(f"Connected to NATS server at {nats_server_url}")
        return nc
    except Exception as e:
        logger.error(f"Failed to connect to NATS server: {e}")
        raise

async def publish_to_topic(nc, topic, message):
    """
    Publish a message to a NATS topic.

    Args:
        nc (NATS): An instance of the connected NATS client.
        topic (str): The topic to publish to.
        message (str): The message to publish.
    """
    try:
        await nc.publish(topic, message.encode())
        logger.info(f"Published message to NATS topic '{topic}': {message}")
    except Exception as e:
        logger.error(f"Error publishing to topic '{topic}': {e}")
        raise

async def subscribe_to_topic(nc, topic, message_handler):
    """
    Subscribe to a NATS topic and set up a message handler.

    Args:
        nc (NATS): An instance of the connected NATS client.
        topic (str): The topic to subscribe to.
        message_handler (callable): The handler function for processing messages.
    """
    try:
        await nc.subscribe(topic, cb=message_handler)
        logger.info(f"Subscribed to NATS topic: {topic}")
    except Exception as e:
        logger.error(f"Error subscribing to topic '{topic}': {e}")
        raise
    
async def handle_NATS_message(topic, payload):
    
    try:
        pass
        
    except Exception as e:
        logger.error(f"Error in handling the '{payload}': {e}")
        raise
        


async def nats_subscriber(config):
    """
    NATS subscription logic.
    """
    nats_server_url = config['NATS_Config']['nats_server_url']
    rmacs_sub_topic = config['NATS_Config']['rmacs_sub_topic']

    try:
        # Connect to NATS
        nc = await connect_nats(nats_server_url)

        # Define the message handler
        async def message_handler(message):
            topic = message.subject
            payload = message.data.decode()
            logger.info(f"Received a message from MS NATS server on '{topic}': {payload}")
            handle_NATS_message(topic, payload)

            if topic == rmacs_sub_topic:
                
                logger.info(f"Handling message: {payload}")

        # Subscribe to the topic
        await subscribe_to_topic(nc, rmacs_sub_topic, message_handler)

        # Publish a test message to rmacs_setting
        await publish_to_topic(nc, "rmacs_msg", "Current mesh operating frequency")

        # Keep the connection alive
        while True:
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Error in NATS subscription: {e}")

    finally:
        await nc.drain()

async def run_with_nats(config):
    """
    Runs the NATS subscriber concurrently.
    """
    try:
        # Start the RMACS scripts in a thread using run_in_executor
        loop = asyncio.get_running_loop()
        logger.info("Starting RMACS scripts...")
        rmacs_task = loop.run_in_executor(None, start_rmacs_scripts, config)

        # Wait for NATS subscriber task
        await nats_subscriber(config)
        await rmacs_task

    except Exception as e:
        logger.error(f"Error in NATS scripts: {e}")
        raise


      
def start_rmacs_server(args) -> None:
    """
    Start rmacs server script

    param args: Configuration options.
    """
    try:
        # Start or restart the service using systemctl
        run_command(["rmacs_server"],args,
            "Failed to start rmacs_server service")
    except Exception as e:
        logger.error(f"Failed to start rmacs_server service: {e}")
        raise

def start_rmacs_client(config, nats_msg_queue) -> None:
    """
    Start rmacs client script.

    param args: Configuration options.
    """
    try:
        # Start or restart the service using systemctl
        run_command(["rmacs_client"],config,nats_msg_queue)
    except Exception as e:
        logger.error(f"Failed to start rmacs_client service: {e}")
        raise

def start_rmacs_scripts(config) -> None:
    """
    Start rmacs-related scripts based on configuration.
    """
    
    try:
        if config['RMACS_Config']['orchestra_node']:
            server_thread = threading.Thread(target=rmacs_server_main, args=(nats_msg_queue,))
            client_thread = threading.Thread(target=rmacs_client_main, args=(nats_msg_queue,))
            server_thread.start()
            client_thread.start()
            server_thread.join()
            client_thread.join()
        else:
            client_thread = threading.Thread(target=rmacs_client_main, args=(nats_msg_queue,))
            client_thread.start()
            client_thread.join()
            
        
    except Exception as e:
        logger.info(f"Error starting rmacs server/client scripts: {e}")
        raise Exception(e)
 

def create_rmacs_config():
     # Load the configuration
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        logger.info(f"Created configuration directory: {CONFIG_DIR}")
    
    # Create the default configuration file if it doesn't exist
    create_default_config(config_file_path)
    
def update_rmacs_config(new_rmacs_config):
    config = load_config(config_file_path)
    # Apply updates to the in-memory configuration
    for section, updates in new_rmacs_config.items():
        if section in config:
            config[section].update(updates)
            logger.info(f"Applied updates to section '{section}': {updates}")
        else:
            logger.warning(f"Unknown configuration section: {section}")
    # Save the updated configuration to the file
    try:
        with open(config_file_path, "w") as config_file:
            yaml.dump(config, config_file, sort_keys=False)
            logger.info(f"Configuration saved to {config_file_path}")
    except Exception as e:
        logger.error(f"Failed to save configuration to {config_file_path}: {e}")

    

def check_radio_interface(config, primary_radio):
    # Load the configuration
    for interface in radio_interfaces:
        if get_interface_operstate(interface):
            logger.info(f'Radio interface:[{interface}] is up with channel BW : {get_channel_bw(interface)}MHz')
        else:
            if interface == primary_radio:
                logger.error(f'Primary radio:[{interface}] is not up')
            logger.warning(f'Radio interface:[{interface}] is not up')
            
def handle_signal(signal_number, frame):
    """
    Signal handler to set the global shutdown flag.

    Args:
        signal_number (int): The signal number.
        frame: The current stack frame.
    """
    global graceful_shutdown
    logger.info(f"Received signal {signal_number}, initiating graceful shutdown...")
    graceful_shutdown = True
    

def main(): 
    logger.info('RMACS Manager started....')
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    # Create the configuration
    create_rmacs_config()
    config = load_config(config_file_path)
    primary_radio = config['RMACS_Config']['primary_radio']
    # Check radio status 
    check_radio_interface(config,primary_radio)
    count = 1
    start_rmacs_scripts(config)
    
    # Start the RMACS scripts and NATS subscriber
    asyncio.run(run_with_nats(config))
        

if __name__ == "__main__":
    main()
