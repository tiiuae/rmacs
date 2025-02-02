import threading
import signal
import sys
import os

parent_directory = os.path.abspath(os.path.dirname(__file__))
if parent_directory not in sys.path:
   sys.path.append(parent_directory)

from config import create_default_config, load_config
from logging_config import logger
from rmacs_util import get_interface_operstate, get_channel_bw, kill_process_by_pid, run_command
config_file_path = '/etc/meshshield/rmacs_config.yaml'
CONFIG_DIR = "/etc/meshshield"

def get_script_path(script_name):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, script_name)

def start_server(args) -> None:
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



def start_client(args) -> None:
    """
    Start rmacs client script.

    param args: Configuration options.
    """
    try:
        # Start or restart the service using systemctl
        run_command(["rmacs_client"],args,
            "Failed to start rmacs_client service")
    except Exception as e:
        logger.error(f"Failed to start rmacs_client service: {e}")
        raise


def start_rmacs_scripts(config) -> None:
    """
    Start rmacs-related scripts based on configuration.
    """
    
    try:
        if config['RMACS_Config']['orchestra_node']:
            server_thread = threading.Thread(target=start_server, args=(config,))
            client_thread = threading.Thread(target=start_client, args=(config,))
            server_thread.start()
            client_thread.start()
            server_thread.join()
            client_thread.join()
        else:
            client_thread = threading.Thread(target=start_client, args=(config,))
            client_thread.start()
            client_thread.join()
        
    except Exception as e:
        logger.info(f"Error starting rmacs server/client scripts: {e}")
        raise Exception(e)
 


# Function to handle the SIGTERM signal
def sigterm_handler(signum, frame):
    """
    Handles a signal interrupt (SIGINT).

    :param signum: The signal number received by the handler.
    :param frame: The current execution frame.
    """
    try:
        logger.info(f"Received SIGTERM signal. Attempting to stop rmacs scripts.")
        kill_process_by_pid("rmacs_client_fsm.py")
        kill_process_by_pid("rmacs_server_fsm.py")
        logger.info("rmacs scripts stopped.")
        # Exit after cleanup
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error killing rmacs client and server FSM scripts. {str(e)}")
        # Exit with an error code
        sys.exit(1)


# Set up the signal handler for SIGTERM
signal.signal(signal.SIGTERM, sigterm_handler)


def create_rmacs_config():
     # Load the configuration
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        logger.info(f"Created configuration directory: {CONFIG_DIR}")
    
    # Create the default configuration file if it doesn't exist
    create_default_config(config_file_path)

def check_radio_interface(config, primary_radio):
    # Load the configuration
    #config = load_config(config_file_path)
    radio_interfaces = config['RMACS_Config']['radio_interfaces'] 
    for interface in radio_interfaces:
        if get_interface_operstate(interface):
            logger.info(f'Radio interface:[{interface}] is up with channel BW : {get_channel_bw(interface)}MHz')
        else:
            if interface == primary_radio:
                logger.error(f'Primary radio:[{interface}] is not up')
            logger.warning(f'Radio interface:[{interface}] is not up')

def main(): 
    logger.info('RMACS Manager started....')
    # Create the configuration
    create_rmacs_config()
    config = load_config(config_file_path)
    primary_radio = config['RMACS_Config']['primary_radio']
    # Check radio status 
    check_radio_interface(config,primary_radio)
    start_rmacs_scripts(config)

if __name__ == "__main__":
    main()
