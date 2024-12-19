import threading
import yaml
#import netifaces
import signal
import sys
import os
parent_directory = os.path.abspath(os.path.dirname(__file__))
if parent_directory not in sys.path:
   sys.path.append(parent_directory)
from config import create_default_config, load_config
from logging_config import logger
from rmacs_util import get_interface_operstate, get_channel_bw, is_process_running, kill_process_by_pid, run_command

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
    # Define server file name
    server_file = "rmacs_server_fsm.py"
    # Kill any running instance of server file before starting it
    server_script_path = get_script_path(server_file)
    if is_process_running(server_file):
        kill_process_by_pid(server_file)
    # Start rmacs server script
    logger.info(f"Started {server_file}")
    #run_command(["python", f"{server_file}"],args,'Failed to run rmacs_server_fsm file')
    run_command(["python", server_script_path], args, 'Failed to run rmacs_server_fsm.py')


def start_client(args) -> None:
    """
    Start rmacs client script.

    param args: Configuration options.
    """
    # Define client file name
    client_file = "rmacs_client_fsm.py"
    client_script_path = get_script_path(client_file)
    # Kill any running instance of server file before starting it
    if is_process_running(client_file):
        kill_process_by_pid(client_file)
    # Start rmacs client script
    #logger.info(f"Started {client_file}")
    #run_command(["python", f"{client_file}"], args,'Failed to run rmacs_client_fsm file')
    logger.info(f"Starting {client_file} from {client_script_path}")
    run_command(["python", client_script_path], args, 'Failed to run rmacs_client_fsm.py')


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
    # Start rmacs-related scripts  
    logger.info('RMACS Manager thread is started....')
    # Create the configuration
    create_rmacs_config()
    config = load_config(config_file_path)
    primary_radio = config['RMACS_Config']['primary_radio']
    # Check radio status 
    check_radio_interface(config,primary_radio)
    start_rmacs_scripts(config)

if __name__ == "__main__":
    main()
