import os 
import time
import subprocess
import sys
import re

from logging_config import logger
from rmacs_util import get_mesh_freq
parent_directory = os.path.abspath(os.path.dirname(__file__))
if parent_directory not in sys.path:
   sys.path.append(parent_directory)
   
from config import load_config
config_file_path = '/etc/meshshield/rmacs_config.yaml'

class TrafficMonitor:
    '''
    A class designed to monitor network traffic and transmission errors by capturing network interface statistics from sysfs.
    
    Methods:
    traffic_monitor: Monitor the Network traffic at specific Network Interface.
    error_monitor: Monitor the Transmission error at specific Network Interface.
    get_traffic_status: Calculate the Network traffic based on previous and current tx_bytes 
    read_sysfs_file: Read the network interface statistics from sysfs.

    '''
    def __init__(self):
        self.prev_tx_bytes = None
        self.cur_tx_bytes = None
        self.tx_rate_wait_time = 2
        self.phy_error_wait_time = 2
        self.tx_timeout_wait_time = 2
        # Set the Network interface  
        config = load_config(config_file_path)
        self.interface = config['RMACS_Config']['primary_radio']
        self.traffic_threshold =  config['RMACS_Config']['traffic_threshold']
        #Network statistics file 
        self.tx_bytes_path = f"/sys/class/net/{self.interface}/statistics/tx_bytes"
        self.tx_error_path = f"/sys/class/net/{self.interface}/statistics/tx_errors"
        self.fw_stats_path = f"/sys/kernel/debug/ieee80211/phy1/{self.interface}/fw_stats"
        
        
        '''
        To get the phy_error : 
        /usr/sbin/ethtool -S wlp1s0|grep -i 'd_rx_phy_err:'|cut -f 2 -d :
        To get the tx_timeout :
        
        /usr/sbin/ethtool -S wlp1s0|grep -i 'd_tx_timeout:'|cut -f 2 -d : 
        
        '''
    def traffic_monitor(self) -> int:
        '''
        Monitor the Network traffic at specific Network Interface.
        
        Returns: 
        int : Return the network traffic in bytes
        '''  
        self.prev_tx_bytes = self.read_sysfs_file(self.tx_bytes_path)
        time.sleep(self.tx_timeout_wait_time)
        self.cur_tx_bytes = self.read_sysfs_file(self.tx_bytes_path)
        if self.prev_tx_bytes is not None and self.cur_tx_bytes is not None: 
            self.traffic = ((self.cur_tx_bytes - self.prev_tx_bytes) * 8)/ (self.tx_rate_wait_time * 1000) #kbps 
            logger.info(f"Traffic : {self.traffic}")
            if self.traffic > self.traffic_threshold:
                logger.info(f"Current Traffic: {self.traffic} in Kbps above threshold traffic : {self.traffic_threshold} in Kbps")
                return self.traffic
            else:
                logger.info(f"There is no traffic, let's go for channel scan......")
                return 0
        else:
            return 0

               
    def error_monitor(self) -> int:
        '''
        Monitor the Transmission error at specific Network Interface.
        
        Returns: 
        int : Return the network traffic error in bytes
        '''
        self.tx_error = self.read_sysfs_file(self.tx_error_path)
        logger.info(f"The traffic error is : {self.tx_error}")
        return self.tx_error
    
    def get_traffic_status(self) -> int:
        '''
        Calculate the Network traffic based on previous and current tx_bytes 
        
        Returns: 
        int : Return the network traffic in bytes
        '''
        if self.prev_tx_bytes is None:
            self.prev_tx_bytes = self.cur_tx_bytes
            time.sleep(self.tx_rate_wait_time) 
            self.cur_tx_bytes = self.read_sysfs_file(self.tx_bytes_path) 
            # Convert tx_bytes value in bytes to Kilobits [Kilobits = Bytes * 8 / 1000]
        self.traffic_in_kbps = ((self.cur_tx_bytes - self.prev_tx_bytes) * 8)/ (self.tx_rate_wait_time * 1000) #kbps 
        logger.info(f"Traffic : {self.traffic_in_kbps}")
        return self.traffic_in_kbps
    
    def get_phy_error(self) ->int:
        
        self.command = f"/usr/sbin/ethtool -S {self.interface} | grep -i 'd_rx_phy_err:' | cut -f 2 -d :"
        self.prev_phy_error = self.run_command(self.command)
        time.sleep(self.phy_error_wait_time)
        self.cur_phy_error = self.run_command(self.command)
        if self.prev_phy_error is not None and self.cur_phy_error is not None:
            logger.info(f"phy_error: {self.cur_phy_error - self.prev_phy_error}")
            return self.cur_phy_error - self.prev_phy_error
                
    def get_tx_timeout(self) ->int:
        
        self.command = f"/usr/sbin/ethtool -S {self.interface} | grep -i 'd_tx_timeout:' | cut -f 2 -d :"
        self.prev_tx_timeout = self.run_command(self.command)
        time.sleep(self.tx_timeout_wait_time)
        self.cur_tx_timeout = self.run_command(self.command)
        if self.prev_tx_timeout is not None and self.cur_tx_timeout is not None:
            logger.info(f"tx_timeout: {self.cur_tx_timeout - self.prev_tx_timeout}")
            return self.cur_tx_timeout - self.prev_tx_timeout
        
    def get_air_time(self) -> int:
        self.mesh_freq = get_mesh_freq(self.interface)
        self.command = f"iw {self.interface} survey dump | grep -A 2 {self.mesh_freq}| grep -E 'channel active time|channel busy time'"
        #iw dev wlp3s0 survey dump | grep -A 2 '2412' | grep -E 'channel active time|channel busy time'

        self.prev_value = self.run_command(self.command)
        time.sleep(self.tx_timeout_wait_time)
        self.cur_value = self.run_command(self.command)
        act_time_1, bsy_time_1 = self.parse_air_time(self.prev_value)
        act_time_2, bsy_time_2 = self.parse_air_time(self.cur_value)
        
        # Check for missing values
        if None in (act_time_1, bsy_time_1, act_time_2, bsy_time_2):
            logger.info("Error: One or more RF parameters are missing.")
            return

        # Calculate the differences
        act_time_delta = act_time_2 - act_time_1
        bsy_time_delta = bsy_time_2 - bsy_time_1

        # Check for zero active time delta to avoid division by zero
        if act_time_delta == 0:
            logger.info("Error: Active time delta is zero. Cannot calculate air time.")
            return

        # Calculate air time percentage
        air_time = (bsy_time_delta / act_time_delta) * 100

        # Display the results
        logger.info("--------------------------------------------")
        logger.info(f"Active Time Delta: {act_time_delta} ms")
        logger.info(f"Busy Time Delta: {bsy_time_delta} ms")
        logger.info(f"Air Time: {air_time}")
        #logger.info(f"Air Time: {air_time:.3f}%")
        logger.info("--------------------------------------------")
        return air_time        

    def parse_air_time(rf_params):
 
        active_time = None
        busy_time = None

        for line in rf_params.splitlines():
            if 'channel active time' in line:
                active_time = int(re.search(r"\d+", line).group())
            elif 'channel busy time' in line:
                busy_time = int(re.search(r"\d+", line).group())

        return active_time, busy_time
    
    def run_command(self, command: str) -> int:
        try:
            result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                output  = result.stdout.strip()
                return int(output)
            else:
                logger.info(f"Command failed with return code {result.returncode}. Error:", result.stderr)
                return None
    
        except FileNotFoundError as e:
            logger.info(f"Command not found: {e}")
            return None
        except subprocess.SubprocessError as e:
            logger.info(f"Subprocess error: {e}")
            return None
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}")
            return None
            
    
    def read_sysfs_file(self, syspath: str) -> int:
        '''
        Read the network interface statistics from sysfs.
        
        Returns: 
        int : Return the sysfs value 
        '''
        
        if os.path.exists(syspath):
            with open(syspath, 'r') as file:
                return int(file.read().strip())
        else:
            raise FileNotFoundError(f"{syspath} does not exist.")
        
        
def main():
    logger.info('Main called ..........')
    obj = TrafficMonitor()
    phy_error = obj.get_phy_error()
    tx_timeout = obj.get_tx_timeout()
    logger.info(f"phy error : {phy_error}, tx_timeout = {tx_timeout}")
    pass

if __name__ == "__main__":
    main()
        
    
    

    


    