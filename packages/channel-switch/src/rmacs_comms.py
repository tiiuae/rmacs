import socket
import struct
#from netstring import encode, decode
import msgpack


#from config_old import Config, MULTICAST_CONFIG
from config import create_default_config, load_config

from logging_config import logger
from rmacs_util import create_json_message

config_file_path = '/etc/meshshield/rmacs_config.yaml'

def get_multicast_config(interface):
    """
    Retrieve multicast group and port based on the interface.
    """
    config = load_config(config_file_path)
    multicast_config = config.get("MULTICAST_CONFIG",{})
    _config = multicast_config.get(interface)
    if config:
        return _config['group'], _config['port']
    else:
        raise ValueError(f"Unknown interface: {interface}")

def rmacs_comms(interface):
    """
    Create a RMACS Multicast socket for Server and Client communication
    """
    try:
        # Create a socket for IPv6 UDP communication
        # Retrieve the multicast group and port based on the interface
        MULTICAST_GROUP, MULTICAST_PORT = get_multicast_config(interface)
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)

        # Allow multiple sockets to use the same port
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)    
        sock.bind(('', MULTICAST_PORT))  # '' means bind to all interfaces

        # Join the multicast group
        # Set the outgoing interface for multicast
        interface_index = socket.if_nametoindex(interface)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, interface_index)

        # Join the multicast group
        rmacs = struct.pack("16sI", socket.inet_pton(socket.AF_INET6, MULTICAST_GROUP), interface_index)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP, rmacs)
        logger.info(f"Server listening on {MULTICAST_GROUP}:{MULTICAST_PORT}")
        return sock
    except socket.error as sock_err:
            logger.error(f"Socket error occurred: {sock_err}")
            return None
    except ValueError as val_err:
        logger.error(f"Value error occurred: {val_err}")
        return None
    except Exception as ex:
        logger.error(f"An unexpected error occurred: {ex}")
        return None
    
def send_data(socket, data, interface) -> None:

    try:
        MULTICAST_GROUP, MULTICAST_PORT = get_multicast_config(interface)
        # Create the JSON message
        payload = data
        message = create_json_message(msg_type="COMMAND", payload=payload)
        logger.info(f"Debug*** : socket = {socket} ")
        if socket:
            socket.sendto(message.encode('utf-8'), (MULTICAST_GROUP, MULTICAST_PORT))  
            logger.info(f"*Sent report to Mutlicast")
        else:
            logger.info(f"Debug : No socket connection for interface :{interface}")
            
        return None
    except BrokenPipeError:
        logger.info(f"Broken pipe error")
    except Exception as e:
        logger.info(f"*Error in sending data : {e}")
        logger.info(f"Error sending data : {e}")

        