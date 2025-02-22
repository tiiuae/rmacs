import threading
import time
import uuid
import subprocess
import os
import sys
import json
import signal
import atexit

from enum import auto, Enum
from typing import List, Tuple, Dict


parent_directory = os.path.abspath(os.path.dirname(__file__))
if parent_directory not in sys.path:
   sys.path.append(parent_directory)

from config import load_config

config_file_path = '/etc/meshshield/rmacs_config.yaml'
from rmacs_util import get_mesh_freq, get_mac_address, get_interface_operstate, get_channel_bw, path_lookup
from logging_config import logger
from rmacs_comms import rmacs_comms, send_data


action_to_id = {
    "bad_channel_quality_index": 0,
    "channel_quality_report": 1,
    "operating_frequency": 2,
    "switch_frequency": 3
}
id_to_action = {v: k for k, v in action_to_id.items()}


class ServerState(Enum):
    IDLE = auto()
    PREPARE_PARTIAL_FREQUENCY_HOPPING = auto()
    PARTIAL_FREQUENCY_HOPPING = auto()
    SEND_CHANNEL_SWITCH_REQUEST = auto()
    UPDATE_FREQ_HOPPING_SEQUENCE = auto()
    BROADCAST_OPERATING_FREQ = auto()
    RESET_CLIENT_MESSAGES = auto()
    RESET_COMPLETE = auto()


class ServerEvent(Enum):
    BAD_CHANNEL_QUALITY_INDEX = auto()
    CHANNEL_QUALITY_REPORT = auto()
    NEW_TARGET_FREQUENCY = auto()
    CHANNEL_SWITCH_REQUEST = auto()
    CHANNEL_SWITCH_REQUEST_SENT = auto()
    TARGET_FREQ_EQ_CURRENT = auto()
    PERIODIC_OPERATING_FREQ_BROADCAST = auto()
    BROADCAST_COMPLETE = auto()
    CHANNEL_QUALITY_UPDATE_COMPLETE = auto()
    FREQUENCY_HOPPING_COMPLETE = auto()
    RESET_COMPLETE = auto()
    PREPARATION_DONE = auto()


class RMACSServerFSM:
    def __init__(self, server):
        self.state = ServerState.IDLE
        self.server = server

        # Transition table
        self.transitions = {
            (ServerState.IDLE, ServerEvent.BAD_CHANNEL_QUALITY_INDEX): (ServerState.PARTIAL_FREQUENCY_HOPPING, self.server.partial_frequency_hopping),
            (ServerState.IDLE, ServerEvent.CHANNEL_QUALITY_REPORT): (ServerState.UPDATE_FREQ_HOPPING_SEQUENCE, self.server.check_and_update_channel_quality_report),
            (ServerState.IDLE, ServerEvent.PERIODIC_OPERATING_FREQ_BROADCAST): (ServerState.BROADCAST_OPERATING_FREQ, self.server.broadcast_operating_freq),
            (ServerState.UPDATE_FREQ_HOPPING_SEQUENCE, ServerEvent.CHANNEL_QUALITY_UPDATE_COMPLETE): (ServerState.IDLE, None),
            (ServerState.BROADCAST_OPERATING_FREQ, ServerEvent.BROADCAST_COMPLETE): (ServerState.IDLE, None),
            (ServerState.PARTIAL_FREQUENCY_HOPPING, ServerEvent.CHANNEL_SWITCH_REQUEST): (ServerState.SEND_CHANNEL_SWITCH_REQUEST, self.server.send_switch_frequency_message),
            (ServerState.SEND_CHANNEL_SWITCH_REQUEST, ServerEvent.CHANNEL_SWITCH_REQUEST_SENT): (ServerState.PARTIAL_FREQUENCY_HOPPING, self.server.partial_frequency_hopping),
            (ServerState.PARTIAL_FREQUENCY_HOPPING, ServerEvent.FREQUENCY_HOPPING_COMPLETE): (ServerState.IDLE, None),
            (ServerState.RESET_CLIENT_MESSAGES, ServerEvent.RESET_COMPLETE): (ServerState.IDLE, None),
        }

    def trigger(self, event) -> None:
        """Function to handle state transitions"""
        logger.debug(f" Trigger event arrived {event}")
        self._process_event(event)

    def _process_event(self, event) -> None:
        """Internal function to process the given event"""
        key = (self.state, event)
        if key in self.transitions:
            next_state, action = self.transitions[key]
            logger.info(f'{self.state} -> {next_state}')
            self.state = next_state
            if action:
                action(event)
                logger.debug(f'process event : {action}')
        else:
            logger.info(f"No transition found for event '{event}' in state '{self.state}'")


class RMACSServer:
    def __init__(self):
        """
        Initializes the RMACS Server object.

        """
        # Initialize server objects and attributes
        self.running = False
        self.fsm = RMACSServerFSM(self)
        config = load_config(config_file_path)
        self.interface = config['RMACS_Config']['primary_radio']
        self.freq_quality_report = config['RMACS_Config']['freq_quality_report']
        self.seq_limit = config['RMACS_Config']['seq_limit']
        self.hop_interval = config['RMACS_Config']['hop_interval']
        self.stability_threshold = config['RMACS_Config']['stability_threshold']
        # Control channel interfaces
        self.ch_interfaces = config['RMACS_Config']['radio_interfaces']
        self.sockets: Dict = {}
        self.listen_threads: list = []
        
        # Receive msg 
        self.bad_channel_message: Dict = {}
        self.channel_report_message: Dict = {}
        
        # Variables for Partial Frequency Hopping
        self.top_freq_stability_counter = 0
        self.pfh_index = 0
        self.seq_limit = config['RMACS_Config']['seq_limit']
        self.sorted_frequencies: list = [] 
        self.top_freq = 0
        self.report_expiry_threshold = config['RMACS_Config']['report_expiry_threshold']
        
        # Variables for Channel Switch 
        self.channel_bandwidth: int = config['RMACS_Config']['channel_bandwidth']
        self.beacon_count: int = config['RMACS_Config']['beacon_count']
        self.buffer_period: int = config['RMACS_Config']['buffer_period']
        
        # BCQI 
        self.bcqi_threshold_time = config['RMACS_Config']['bcqi_threshold_time']

        # Initialize the lock for thread-safe access
        self.lock = threading.Lock()

        # Create threads for server operations
        self.run_server_fsm_thread = threading.Thread(target=self.run_server_fsm)
        
        # Time for periodic events' variables (in seconds)
        self.last_operating_freq_broadcast: float = time.time()
        self.periodic_operating_freq_broadcast = config['RMACS_Config']['periodic_operating_freq_broadcast']

        # Internal Attributes
        self.operating_frequency: int = get_mesh_freq(self.interface)
        self.mac_address: str = get_mac_address(self.interface)
        self.switch_freq: int = self.operating_frequency
        
        # A set to store the unique IDs of processed messages
        self.processed_ids = set()
        self.msg_id_lock = threading.Lock()

    def start(self) -> None:
        """
        Starts the server and listens for incoming client connections.
        """
        try:     
            self.running = True
            # Establish socket connections for all interfaces
            for interface in self.ch_interfaces:
                if get_interface_operstate(interface):
                    logger.info(f'Radio interface:[{interface}] is up with channel BW : {get_channel_bw(interface)}MHz')
                    try:
                        socket = rmacs_comms(interface)
                        self.sockets[interface] = socket
                        listen_thread = threading.Thread(target=self.receive_messages, args=(socket, interface))
                        self.listen_threads.append(listen_thread)
                        listen_thread.start()
                        logger.info(f"Listening on interface: {interface}")
                    except ConnectionError as e:
                        logger.error(f"Connection error on {interface}: {e}")
                else:
                    logger.info(f'Radio interface:[{interface}] is not up, cannot create a multicast socket connection to it.')
            # Start the server FSM thread
            logger.info("Server started and listening...")
            self.run_server_fsm_thread = threading.Thread(target=self.run_server_fsm)
            self.run_server_fsm_thread.start()

        except Exception as e:
            logger.error(f"Unexpected error while starting server: {e}")
            self.stop()
            
    def run_server_fsm(self) -> None:
        """
        Run the Server Finite State Machine (FSM) continuously to manage its state transitions and periodic tasks.
        """
        
        logger.info("Run RMACS Server FSM thread ........")
        count = 0
    
        while self.running:
            try:
                if self.fsm.state == ServerState.IDLE:
                    current_time = time.time()
                    count +=1
                    
                    if self.bad_channel_message:
                        self.update_channel_quality_report(self.bad_channel_message)
                        self.bad_channel_message = None
                        self.fsm.trigger(ServerEvent.BAD_CHANNEL_QUALITY_INDEX)
                    
                    # Check if it's time to perform a periodic operating frequency broadcast
                    if current_time - self.last_operating_freq_broadcast >= self.periodic_operating_freq_broadcast:
                        logger.info("Broadcast Operating Frequency.....")
                        self.last_operating_freq_broadcast = time.time()
                        self.fsm.trigger(ServerEvent.PERIODIC_OPERATING_FREQ_BROADCAST)
                              
                if self.channel_report_message:
                    logger.info("Received channel report and update it:")
                    self.fsm.trigger(ServerEvent.CHANNEL_QUALITY_REPORT)
                    
                time.sleep(2)
            except Exception as e:
                logger.info(f"Exception in run_server_fsm: {e}")
    
    
    def check_and_update_channel_quality_report(self,trigger_event) -> None:
        """
        Check for a channel quality report message from any connected client.
        """
        self.msg = self.channel_report_message
        self.update_channel_quality_report(self.msg)
        self.channel_report_message = None
        self.fsm.trigger(ServerEvent.CHANNEL_QUALITY_UPDATE_COMPLETE)
                     
    def update_channel_quality_report(self, message) -> None:
        try:
            self.freq = message.get("payload", {}).get("freq")
            self.quality_index = message.get("payload", {}).get("qual")
            self.device_id = message.get("payload", {}).get("device")
            self.phy_error = message.get("payload", {}).get("phy_error")
            self.tx_rate = message.get("payload", {}).get("tx_rate")
            self.tx_timeout = message.get("payload", {}).get("tx_timeout")
        except Exception as e:
                logger.info(f"Exception in update channel quality report: {e}")
        current_time = time.time()
        # Check if the frequency exists; if not, add it
        if self.freq not in self.freq_quality_report:
            self.freq_quality_report[self.freq] = {'nodes': {}, 'Average_quality': 1}
        # Update the node's quality data
        self.freq_quality_report[self.freq]['nodes'][self.device_id] = {'quality': self.quality_index, 'timestamp':current_time}
        self.update_average_quality(self.freq)
        logger.info(f"Updated Channel Quality Report: {self.freq_quality_report}")
        
    def update_average_quality(self, freq):
        """
        Recalculate the average quality for a specific frequency, considering only recent reports.
        :param freq: Frequency to recalculate average quality for
        """
        node_reports = self.freq_quality_report[freq]['nodes']

        # Find the latest timestamp among all reports for the given frequency
        if node_reports:
            latest_timestamp = max(report['timestamp'] for report in node_reports.values())
            expiry_threshold = latest_timestamp - self.report_expiry_threshold

            # Filter reports within 30 seconds of the latest timestamp
            valid_qualities = [
                report['quality']
                for report in node_reports.values()
                if report['timestamp'] >= expiry_threshold
            ]

            # Calculate the average quality based on valid reports
            if valid_qualities:
                average_quality = sum(valid_qualities) / len(valid_qualities)
            else:
                average_quality = None  # No valid reports within 30 seconds
        else:
            average_quality = None  # No reports at all

        # Update the average quality in the main dictionary
        self.freq_quality_report[freq]['Average_quality'] = average_quality
        logger.info(f"Channel Quality Avg index for freq {freq} : {average_quality}")
        logger.info(f'Channel quality report is {self.freq_quality_report}')
    

    def broadcast_operating_freq(self, trigger_event) -> None:
        """
        Broadcast Operating frequency to all clients.

        :param trigger_event: ServerEvent that triggered the execution of this function.
        """
        try:
            action_id: int = action_to_id["operating_frequency"]
            freq = get_mesh_freq(self.interface)
            message_id: str = str(uuid.uuid4())  
            operating_freq_data = {'a_id': action_id, 'freq': freq, 'message_id': message_id, 'device': self.mac_address }
            logger.info(f"Brodcasting operating freq : {operating_freq_data}")
             # Loop through the sockets dictionary and send data
            for interface, socket in self.sockets.items():
                self.send_to_socket(socket, operating_freq_data, interface)
            self.fsm.trigger(ServerEvent.BROADCAST_COMPLETE)
        except Exception as e:
            logger.info(f"Broadcast operating frequency error: {e}")
    
    def send_to_socket(self, socket, data, interface):
        try:
            send_data(socket, data, interface)
            logger.info(f"Successfully sent data to {interface}")
        except Exception as e:
            logger.error(f"Error sending data to {interface}: {e}")
        
        
    # Adaptive frequency hopping with dynamic intervals and exit condition based on top frequency stability
    
    def partial_frequency_hopping(self, trigger_event) -> None:
        
        try:
            self.sorted_frequencies = sorted(self.freq_quality_report.items(),key=lambda item: item[1]['Average_quality'])
            logger.info(f'Sorted freq : {self.sorted_frequencies}  ')
            self.top_freq = self.sorted_frequencies[0][0]
            self.seq_limit = min(self.seq_limit, len(self.sorted_frequencies))
            if self.top_freq_stability_counter:
                time.sleep(self.hop_interval)
            if (self.fsm.state == ServerState.PARTIAL_FREQUENCY_HOPPING):
              
                if self.top_freq_stability_counter < self.stability_threshold:
                    # Continue hopping between the best frequencies
                    self.switch_freq = self.sorted_frequencies[self.pfh_index][0]
                    logger.info(f"Executing partial frequency hopping, stability count: {self.top_freq_stability_counter}")

                    # Move to the next frequency in the list
                    self.pfh_index = (self.pfh_index + 1) % self.seq_limit
                    with self.lock:
                        # Sort by the second item in the tuple (quality) in ascending order (best quality first)
                        
                        self.sorted_frequencies = sorted(self.freq_quality_report.items(),key=lambda item: item[1]['Average_quality'])
                        current_top_freq = self.sorted_frequencies[0][0]
                    #logger.info(f" the current top freq : {current_top_freq}")
                    if current_top_freq == self.top_freq:
                        self.top_freq_stability_counter += 1
                        logger.info(f"Top frequency {self.top_freq} remained the same for {self.top_freq_stability_counter} consecutive checks.")
                    else:
                        self.top_freq_stability_counter = 0  # Reset counter if top frequency changes
                        self.top_freq = current_top_freq  # Update the top frequency
                        logger.info(f"Top frequency changed to {self.top_freq}.")

                    # Exit if the top frequency stays the same for the stability threshold period
                    if self.top_freq_stability_counter == self.stability_threshold:
                        logger.info(f"Top frequency {self.top_freq} has been stable for {self.stability_threshold} consecutive checks. Exiting.")
                        self.operating_frequency = self.top_freq
                        self.switch_freq = self.top_freq
                    
                    logger.info(f"The next switch frequency: {self.switch_freq}")
                    result = self.switch_frequency(self.switch_freq, self.interface, self.channel_bandwidth, self.beacon_count)
                    if result:
                        logger.info("Waiting for CSA to be established")
                        time.sleep(self.beacon_count + self.buffer_period)
                    if get_mesh_freq(self.interface) == self.switch_freq:
                       logger.info(f" CSA is successfull, Node switched to new operating freq : {get_mesh_freq(self.interface)}")
                    else:
                       logger.info(f" CSA is not successfull, current operating freq : {get_mesh_freq(self.interface)}")
                    self.fsm.trigger(ServerEvent.CHANNEL_SWITCH_REQUEST)

                if self.top_freq_stability_counter >= self.stability_threshold:
                    logger.info(f"Completed partial frequency hopping: count: {self.top_freq_stability_counter}")
                    self.top_freq_stability_counter = 0
                    self.fsm.trigger(ServerEvent.FREQUENCY_HOPPING_COMPLETE)
                
        except Exception as e:
            logger.info(f" PFH error {e}")

    def switch_frequency(self, frequency: int, interface: str, bandwidth: int, beacon_count: int ) -> bool:
        cur_freq = get_mesh_freq(interface)
        logger.info(f"The operating freq is {cur_freq}, Requested switch freq : {frequency}")
        if cur_freq == frequency:
            logger.info(f"Mesh node is currently operating at requested freq:{cur_freq} switch")
            return False 
        iw_path = path_lookup('iw')
        if iw_path is not None:
            run_cmd = f"{iw_path} dev {interface} switch freq {frequency} HT{bandwidth} beacons {beacon_count}"
            logger.info(f"+run_cmd: {run_cmd}")
            try:
                result = subprocess.run(run_cmd, 
                                    shell=True, 
                                    capture_output=True, 
                                    text=True)
                if(result.returncode != 0):
                    logger.info("Failed to execute the switch frequency command")
                    return False
                else:
                    logger.info("Channel Switch cmd run successfully!")
                    return True

            except subprocess.CalledProcessError as e:
                logger.info(f"Error: {e}")
                return False
            
        else:
            logger.warning(f"iw utility is not found")


    def send_switch_frequency_message(self, trigger_event) -> None:
        """
        Sends a message to all connected clients to switch to operating frequency.

        :param trigger_event: ServerEvent that triggered the execution of this function.
        """
        logger.info('Sending channel switch request...')
        action_id = action_to_id["switch_frequency"]
        message_id = str(uuid.uuid4())  # Generate a new ID at the end of the healing process
        switch_frequency_data = {'a_id': action_id, 'freq': self.switch_freq, 'message_id': message_id, 'device': self.mac_address}
        logger.info(f"The switch info is : {switch_frequency_data}")     
        # Loop through the sockets dictionary and send data
        for interface, socket in self.sockets.items():
            self.send_to_socket(socket, switch_frequency_data, interface)
        self.fsm.trigger(ServerEvent.CHANNEL_SWITCH_REQUEST_SENT)
        

    def receive_messages(self, socket, interface) -> None:
        """
        Handles incoming messages from the client.
        """
        logger.info("RMACS server receive msg is started.........")
        current_received_bcqi_alert = 0
        last_received_bcqi_alert = 0
        while self.running:
            try:
                # Receive incoming messages and decode the netstring encoded data
                try:
                    data, address = socket.recvfrom(1024)
                    data = data.decode('utf-8')
                    logger.debug(f"Received message from {address[0]}")
                    # Parse the JSON message
                    parsed_message = json.loads(data)
                except Exception as e:
                    # Handle netstring decoding errors
                    logger.info(f"Failed to decode netstring from interface: {interface}")
                    break

                # Deserialize the MessagePack message
                try:
                    message_id = parsed_message.get("payload", {}).get("message_id")
                    with self.msg_id_lock:
                        if message_id in self.processed_ids:
                            logger.debug(f"Duplicate Msg: Message with ID {message_id} has already been processed and was received via interface : {interface}. Ignoring.")
                        else:
                            logger.debug(f"New Msg: Processing Message with ID : {message_id} via interface : {interface}")
                            device_id: str = parsed_message.get("payload", {}).get("device")
                            # Add the unique ID to the processed set
                            self.processed_ids.add(message_id)
                            action_id: int = parsed_message.get("payload", {}).get("a_id")
                            action_str: str = id_to_action.get(action_id)
    
                            # Bad channel quality index received from client
                            if action_str == "bad_channel_quality_index":
                                current_received_bcqi_alert = time.time()
                                device_id = parsed_message.get("payload", {}).get("device")
                                bcqi_reported_freq = parsed_message.get("payload", {}).get("freq")
                                channel_quality_index = parsed_message.get("payload", {}).get("qual")
                                current_operating_freq = get_mesh_freq(self.interface)
                                logger.info(f"Received BCQI report for freq :{bcqi_reported_freq} of channel quality index : {channel_quality_index} from device : {device_id} via interface : {interface}")
                                if current_operating_freq == bcqi_reported_freq:
                                    if (current_received_bcqi_alert - last_received_bcqi_alert) > self.bcqi_threshold_time:
                                        logger.info(f"The current rec bcqi alert : {current_received_bcqi_alert}")
                                        logger.info(f"The last rec bcqi alert : {last_received_bcqi_alert}")
                                        logger.info(f"The bcqi threshold time : {self.bcqi_threshold_time}")
                                        logger.info(f" the time diff : {current_received_bcqi_alert - last_received_bcqi_alert}")
                                        last_received_bcqi_alert = current_received_bcqi_alert
                                        logger.info(f"Received BCQI report for freq:{bcqi_reported_freq} from device :{device_id} is for the current operating freq : {current_operating_freq} via interface : {interface}")
                                        self.bad_channel_message = data
                                    else:
                                        logger.info(f"Received BCQI report for freq : {bcqi_reported_freq} from device : {device_id} at time : {current_received_bcqi_alert} via interface : {interface} is considered as duplicate message, since similar msg from other client prior to this msg is already addressed")
                                else:
                                    logger.info(f"Received BCQI report for freq:{bcqi_reported_freq} not for current operating freq : {current_operating_freq} via interface : {interface}")
                                    logger.info("Not required to trigger partial frequency hopping")
                                    parsed_message = {}
                                #self.bad_channel_message = data

                            # Channel report received from client
                            elif action_str == "channel_quality_report":
                                #self.channel_report_message = data
                                self.channel_report_message = parsed_message
                                if not self.channel_report_message:
                                    logger.info("Channel quality is empty.")
                                else:
                                    logger.info(f"The report is {self.channel_report_message}")
                                parsed_message = {}
                except Exception as e:
                    logger.error(f"Error in received message: {e}")
                    continue

            except ConnectionResetError:
                logger.error("Connection forcibly closed by the remote host")
                break

    def reset(self):
        """
        Reset message related client attributes to their default values.
        """
        self.bad_channel_message = {}
        self.channel_report_message = {}
            
    def stop(self) -> None:
        """
        Stops all threads, closes all sockets, and cleans up server resources.
        """
        logger.info("Stopping the RMACS server...")
        try:
            self.running = False

            if self.run_server_fsm_thread.is_alive():
                self.run_server_fsm_thread.join()
                logger.info("RMACS Server FSM thread stopped.")

            for interface, socket in self.sockets.items():
                try:
                    socket.close()
                    logger.info(f"Socket on interface {interface} closed.")
                except Exception as e:
                    logger.error(f"Error closing socket on interface {interface}: {e}")

            for thread in self.listen_threads:
                if thread.is_alive():
                    thread.join()
                    logger.info(f"Listener thread {thread.name} stopped.")

            self.reset()
            logger.info("Server attributes reset.")

        except Exception as e:
            logger.error(f"Error while stopping the server: {e}")

        finally:
            logger.info("RMACS server stopped.")
            
def handle_exit_signal(server: RMACSServer, signum, frame) -> None:
    """
    Handles termination signals (SIGTERM, SIGINT) and gracefully stops the server.
    :param server: The RMACSServer instance.
    :param signum: The signal number received.
    :param frame: The current stack frame (ignored here).
    """
    logger.info(f"Received signal {signum}. Gracefully stopping the RMACS server...")
    if server:
        server.stop()
    sys.exit(0)  # Exit the application
def register_exit_handlers(server: RMACSServer) -> None:
    """
    Registers signal handlers and atexit cleanup for the RMACS server.
    :param server: The RMACSServer instance.
    """
    # Register signal handlers
    signal.signal(signal.SIGTERM, lambda s, f: handle_exit_signal(server, s, f))
    signal.signal(signal.SIGINT, lambda s, f: handle_exit_signal(server, s, f))
    # Register atexit cleanup
    atexit.register(lambda: server.stop() if server else None)

def main():
    """
    Main entry point for the RMACS server.
    """
    server: RMACSServer = None

    try:
        server = RMACSServer()
        register_exit_handlers(server)
        server.start()
        logger.info("RMACS server is running...")

    except Exception as e:
        logger.error(f"Unexpected error in the server: {e}")
        if server:
            server.stop()

if __name__ == "__main__":
    main()
