#!/usr/bin/python
import subprocess
from typing import BinaryIO
import json
import re
import shutil
import os



from config import load_config
config_file_path = '/etc/meshshield/rmacs_config.yaml'
from rmacs_util import get_mesh_freq, get_channel_bw, get_interface_operstate, get_phy_interface
from logging_config import logger

class Spectral_Scan:
    def __init__(self):
        self.VALUES = dict()
        config = load_config(config_file_path)
        self.interface = config['RMACS_Config']['primary_radio']
        self.is_interface_up = get_interface_operstate(self.interface)
        self.phy_interface = get_phy_interface(self.interface)
        self.channel_bw = get_channel_bw(self.interface)
        self.driver = config['RMACS_Config']['driver']
        self.bin_file = config['RMACS_Config']['bin_file']

    def initialize_scan(self) -> None:
        """
        Initialize spectral scan.
        """
        if self.driver in ("ath9k", "ath10K"):
            output_file = f"/sys/kernel/debug/ieee80211/{self.phy_interface}/{self.driver}/spectral_scan_ctl"

            cmd_background = ["echo", "background"]
            with open(output_file, "w") as file:
                subprocess.call(cmd_background, stdout=file, stderr=subprocess.PIPE, shell=False)

            cmd_trigger = ["echo", "trigger"]
            with open(output_file, "w") as file:
                subprocess.call(cmd_trigger, stdout=file, stderr=subprocess.PIPE, shell=False)
        else:
            raise Exception(f"Invalid driver: {self.driver}")

    def execute_scan(self, freq: str) -> None:
        """
        Execute spectral scan.

        param interface: A string of the interface to use to perform the spectral scan.
        param frequencies: A string of the frequencies to scan.
        /* enum spectral_mode:
        *
        * @SPECTRAL_DISABLED: spectral mode is disabled
        * @SPECTRAL_BACKGROUND: hardware sends samples when it is not busy with
        *	something else.
        * @SPECTRAL_MANUAL: spectral scan is enabled, triggering for samples
        *	is performed manually.
        * @SPECTRAL_CHANSCAN: Like manual, but also triggered when changing channels
        *	during a channel scan.
        */
        """
        
         # Check for interface up
        if self.is_interface_up:
            # Command to execute spectral scan
            cur_freq = get_mesh_freq(self.interface) 
            if self.channel_bw == 40 and (cur_freq != freq):
                scan_cmd = ["iw", "dev", f"{self.interface}", "scan", "freq", f"{freq}", f"{cur_freq}", "flush"]
            else:
                scan_cmd = ["iw", "dev", f"{self.interface}", "scan", "freq", f"{freq}", "flush"]
            logger.info(f"scan cmd : {scan_cmd}")
            try: 
                subprocess.call(scan_cmd, shell=False, stderr=subprocess.STDOUT, stdout=subprocess.DEVNULL)
            except subprocess.CalledProcessError as e:
                logger.info(f"Error: {e}")         
        else:
            logger.info(f"The interface :{self.driver} is not up")
            return
        # Command to stop spectral scan
        cmd_disable = ["echo", "disable"]
        spectral_scan_ctl_file = f"/sys/kernel/debug/ieee80211/{self.phy_interface}/{self.driver}/spectral_scan_ctl"
        try:
            with open(spectral_scan_ctl_file, "w") as file:
                subprocess.call(cmd_disable, stdout=file, stderr=subprocess.PIPE, shell=False)
        except subprocess.CalledProcessError as e:
            logger.info(f"Error: {e}")

        # Command to dump scan output from spectral_scan0 to binary file
        cmd_dump = ["cat", f"/sys/kernel/debug/ieee80211/{self.phy_interface}/{self.driver}/spectral_scan0"]
        try:
            with open(self.bin_file, "wb") as output_file:
                subprocess.call(cmd_dump, stdout=output_file, stderr=subprocess.PIPE, shell=False)
        except subprocess.CalledProcessError as e:
            logger.info(f"Error: {e}")
            
    def run_fft_eval(self, freq:str) -> list[dict]:

        try:
            # Run the subprocess command
            #result = subprocess.run(['ss-analyser', self.bin_file, f"{freq}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if shutil.which('ss-analyser') is None:
                print("Executable 'ss-analyser' not found in PATH")
                return [{"error": "Executable 'ss-analyser' not found in PATH"}]
            else:
                print("Executable 'ss-analyser' is found in PATH")
                

            # Check if 'bin_file' exists
            if not os.path.exists(self.bin_file):
                print(f"Binary file not found: {self.bin_file}")
                return [{"error": f"Binary file not found: {self.bin_file}"}]
            else:
                print(f"Binary file is found: {self.bin_file}")
            
            result = subprocess.Popen(
                ['ss-analyser', self.bin_file, f"{freq}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True)
            stdout, stderr = result.communicate()
            logger.info(f"+stdrr : {stderr.strip()}")
            logger.info(f"+stdout : {stdout.strip()}")

        # Check return code and handle output
            if result.returncode == 0:
                output = stdout
                output = re.sub(r'([{,])\s*(\w+)\s*:', r'\1"\2":', output)
                logger.info(f"+Channel Quality Report : {output}")
                return output
            else:
                error_message = stderr.strip() if stderr.strip() else "Unknown error occurred."
                logger.info(f"++Command failed with return code: {result.returncode}. Error: {error_message}")
                return [{"error": f"Return code: {result.returncode}, Message: {error_message}"}]
     

        except FileNotFoundError as e:
            return [{"error": f"Command not found: {e}"}]
        except subprocess.SubprocessError as e:
            return [{"error": f"Subprocess failed: {e}"}]
        except json.JSONDecodeError as e:
            return [{"error": f"Failed to parse JSON: {e}"}]
       
       