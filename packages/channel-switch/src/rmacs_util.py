import subprocess
import re
import json
from logging_config import logger
import shutil

# Channel to frequency and frequency to channel mapping
CH_TO_FREQ = {1: 2412, 2: 2417, 3: 2422, 4: 2427, 5: 2432, 6: 2437, 7: 2442, 8: 2447, 9: 2452, 10: 2457, 11: 2462,
              36: 5180, 40: 5200, 44: 5220, 48: 5240, 52: 5260, 56: 5280, 60: 5300, 64: 5320, 100: 5500, 104: 5520,
              108: 5540, 112: 5560, 116: 5580, 120: 5600, 124: 5620, 128: 5640, 132: 5660, 136: 5680, 140: 5700,
              149: 5745, 153: 5765, 157: 5785, 161: 5805}

FREQ_TO_CH = {v: k for k, v in CH_TO_FREQ.items()}



def get_interface_operstate(interface : str) -> bool:
    """
    Check if a network interface is up through sysfs.
    Path : /sys/class/net/<interface>/operstate
    Arguments:
    interface: str -- Name of the network interface to check.
    Return:
    Bool -- True if the interface is up, False otherwise.
    """
    operstate_path = f"/sys/class/net/{interface}/operstate"
    try:
        with open(operstate_path, "r") as file:
            operstate = file.read().strip()
        if operstate.lower() == 'up':
            print(f"The operational state of {interface} is: up")
            return True
        else:
            print(f"The operational state of {interface} is: {operstate}")
            return False
    except FileNotFoundError:
        print(f"Interface {interface} not found.")
    except Exception as e:
        print(f"Error reading operstate: {e}")
        
def get_phy_interface(interface : str) -> str:
    """
    Get phy interface value associated with the driver 
    Arguments:
    driver : str -- driver name of the radio interface
    Return: 
    str: Phy interface value associated with the driver name
    """
    phy_interface_path = f"/sys/class/net/{interface}/phy80211/name"
    try:
        with open(phy_interface_path, "r") as file:
            phy_interface = file.read().strip()
            return phy_interface
    except FileNotFoundError:
        print(f"Interface {interface} not found.")
    except Exception as e:
        print(f"Error reading operstate: {e}")
 
'''       
def get_ipv6_addr(interface) -> str:
    """
    Get the IPv6 address of the Radio network interface.

    :param interface: The name of the network interface.
    :return: The IPv6 address as a string.
    """
    # Retrieve the IPv6 addresses associated with the osf_interface
    prefix = 'fdd8'
    addresses = ni.ifaddresses(interface).get(ni.AF_INET6, [])

    # Loop through the addresses to find the one that starts with the specified prefix
    for addr_info in addresses:
        ipv6_addr = addr_info['addr']
        if ipv6_addr.startswith(prefix):
            return ipv6_addr

    return None  # Return None if no address with the specified prefix is found
'''


    
def get_channel_bw(interface) -> int:
    
    run_cmd = f"iw dev {interface} info | grep 'width' | awk '{{print $6}}'"
    try:
        result = subprocess.run(run_cmd, 
                            shell=True, 
                            capture_output=True, 
                            text=True)

        if result.returncode == 0 and result.stdout.strip():
                width = int(result.stdout.strip())  
                print(f"Channel Width: {width}")
                return width
        else:
            print(f"Command failed or no output returned. Return code: {result.returncode}")
            return None
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return None
    
def channel_switch_announcement(frequency: int, interface: str, bandwidth: int, beacons_count: int ) -> None:
    if bandwidth in {5,10,80}:
        run_cmd = f"iw dev {interface} switch freq {frequency} {bandwidth}MHz beacons {beacons_count}"
    else:
        run_cmd = f"iw dev {interface} switch freq {frequency} HT{bandwidth}+ beacons {beacons_count}"
        
    try:
        result = subprocess.run(run_cmd, 
                            shell=True, 
                            capture_output=True, 
                            text=True)
        if(result.returncode != 0):
            print("Failed to execute the switch frequency command")

    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return None

def get_mesh_freq(interface) -> int:
    """
    Get the mesh frequency of the device.

    :return: An integer representing the mesh frequency.
    """
    mesh_freq: int = None

    try:
        iw_output = subprocess.check_output(['iw', 'dev'], encoding='utf-8')
        iw_output = re.sub(r'\s+', ' ', iw_output).split(' ')

        # Extract interface sections from iw_output
        idx_list = [idx - 1 for idx, val in enumerate(iw_output) if val == "Interface"]
        if len(idx_list) > 1:
            idx_list.pop(0)

        # Calculate the start and end indices for interface sections
        start_indices = [0] + idx_list
        end_indices = idx_list + ([len(iw_output)] if idx_list[-1] != len(iw_output) else [])

        # Use zip to create pairs of start and end indices, and extract interface sections
        iw_interfaces = [iw_output[start:end] for start, end in zip(start_indices, end_indices)]

        # Check if mesh interface is up and get freq
        for interface_list in iw_interfaces:
            try:
                if interface in interface_list and "mesh" in interface_list and "channel" in interface_list:
                    channel_index = interface_list.index("channel") + 2
                    mesh_freq = int(re.sub("[^0-9]", "", interface_list[channel_index]).split()[0])
                    break
            except Exception as e:
                logger.error(f"Get mesh freq exception: {e}")
    except Exception as e:
        logger.error(f"Get mesh freq exception: {e}")

    return mesh_freq

def get_mac_address(interface):
    mac_address_path = f"/sys/class/net/{interface}/address"
    try:
        with open(mac_address_path, "r") as file:
            mac_address = file.read().strip()
        if mac_address:
            logger.info(f"MAC address is : {mac_address}")
            return mac_address
        else:
            logger.info("Failed to get MAC address")
            return None
    except FileNotFoundError:
        print(f"Interface {interface} not found.")
    except Exception as e:
        print(f"Error reading operstate: {e}")
       
def is_process_running(process_name: str) -> bool:
    """
    Check if a process with a given name is currently running.

    param process_name: The name of the process to check.

    return: True if the process is running, False otherwise.
    """
    try:
        ps_output = subprocess.check_output(['ps', 'aux']).decode('utf-8')
        if process_name in ps_output:
            return True
        else:
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Error occurred while checking process: {e}")
        return False


def get_pid_by_process_name(process_name: str) -> int:
    """
    Get the Process ID (PID) of a process by its name.

    param: The name of the process to search for.

    return: The PID of the process if found, or 0 if the process is not found.
    """
    try:
        # List processes and filter by name
        ps_output = subprocess.check_output(['ps', 'aux'], text=True)
        for line in ps_output.split('\n'):
            if process_name in line:
                pid = int(line.split()[0])
                return pid
        return 0  # Process not found
    except subprocess.CalledProcessError:
        return 0


def kill_process_by_pid(process_name: str) -> None:
    """
    Attempt to kill a process by its name.

    param: The name of the process to be killed.
    """
    if is_process_running(process_name):
        # Retrieve the Process ID (PID) of the specified process
        pid = get_pid_by_process_name(process_name)
        try:
            subprocess.check_output(['kill', str(pid)])
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to kill process: {e}")  # Failed to kill the process
    else:
        logger.info(f"{process_name} not running, nothing to kill.") 
        

def run_command(command, config, error_message) -> None:
    """
    Execute a shell command and check for success.

    param command: The shell command to execute in the form of list of strings.
    param error_message: Error message to display if the command fails.
    """
    try:
        # Run the command, redirecting both stdout and stderr to the log file
        with open(config['RMACS_Config']['log_file'], 'a') as subprocess_output:
            # Redirect the output to the log file
            return_code = subprocess.call(command, shell=False, stdout=subprocess_output, stderr=subprocess_output)

        if return_code != 0:
            logger.error(f"Command {command} failed with return code {return_code}")
    except Exception as e:
        logger.error(f"{error_message}. Error: {e}")
        raise Exception(error_message) from e
    
def create_json_message(msg_type, payload=None, status_code=0):
    """
    Create a JSON message based on input parameters without source address.
    
    Parameters:
    msg_type (str): The type of the message (e.g., "COMMAND", "STATUS", "DATA").
    target (str): The target device or entity (default is "All").
    payload (dict): The payload of the message (e.g., command details or data) (optional).

    Returns:
    str: A JSON-formatted message as a string.
    """
    # Create the base message structure
    message = {
        "msg_type": msg_type
    }

    # Add optional payload if provided
    if payload:
        message["payload"] = payload

    # Convert the message dictionary to a JSON string
    return json.dumps(message, indent=4)

def path_lookup(binary) -> str:
    
    return shutil.which(binary)  