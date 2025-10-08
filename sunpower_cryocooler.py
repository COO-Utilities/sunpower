"""
A Python class to control a Sunpower cryocooler via serial or TCP connection.
"""
import sys
import socket
import time
import logging
from typing import Union
import serial


def parse_single_value(reply: list) -> Union[float, int, bool, str]:
    """Attempt to parse a single value from the reply list."""
    if not isinstance(reply, list):
        raise TypeError("reply must be a list")

    try:
        val = reply[1]
    except IndexError:
        return "No reply"

    # Parse Booleans
    if val.lower() in ("true", "yes", "on", "1"):
        return True
    if val.lower() in ("false", "no", "off", "0"):
        return False

    # Parse integers
    try:
        return int(val)
    except ValueError:
        pass

    # Parse floats
    try:
        return float(val)
    except ValueError:
        pass

    # Fallback: return string
    return val.strip()

class SunpowerCryocooler:
    """A class to control a Sunpower cryocooler via serial or TCP connection."""
    # pylint: disable=too-many-instance-attributes
    def __init__(self, logfile=None, quiet=True, connection_type='tcp',
                 read_timeout=1.0):
        """ Initialize the SunpowerCryocooler."""
        if not logfile:
            logfile = __name__.rsplit('.', 1)[-1] + '.log'
        self.logger = logging.getLogger(logfile)
        self.logger.setLevel(logging.INFO)

        # console logging
        console_formatter = logging.Formatter(
            '%(asctime)s--%(message)s')
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # file logging
        if not quiet:
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler = logging.FileHandler(logfile)
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

        self.connection_type = connection_type
        self.read_timeout = read_timeout
        self.connected = False
        self.ser = None
        self.sock = None
        self.verbose = False
        self.last_error = ""

    def connect(self, tcp_host=None, tcp_port=None, port="/dev/ttyUSB0", baudrate=9600):
        """Connect to the Sunpower controller."""
        try:
            if self.connection_type == "serial":
                self.ser = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    timeout=self.read_timeout,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                )
                self._log(f"Serial connection opened: {self.ser.is_open}", logging.INFO)
                self.connected = True
            elif self.connection_type == "tcp":
                if tcp_host is None or tcp_port is None:
                    raise ValueError(
                        "tcp_host and tcp_port must be specified for TCP connection"
                    )
                self.sock = socket.create_connection((tcp_host, tcp_port), timeout=2)
                self.sock.settimeout(self.read_timeout)
                self._log(f"TCP connection opened: {tcp_host}:{tcp_port}", logging.INFO)
                self.connected = True
            else:
                raise ValueError("connection_type must be 'serial' or 'tcp'")
        except Exception as ex:
            self._log(f"Failed to establish connection: {ex}", logging.ERROR)
            raise

    def disconnect(self):
        """Close the connection."""
        if self.connection_type == "serial":
            self.ser.close()
            self._log("Serial connection closed.", logging.INFO)
        elif self.connection_type == "tcp":
            self.sock.close()
            self._log("TCP connection closed.", logging.INFO)
        self.connected = False

    def _send_command(self, command: str):
        """Send a command to the Sunpower controller."""
        full_cmd = f"{command}\r"
        try:
            if self.connection_type == "serial":
                self.ser.write(full_cmd.encode())
            elif self.connection_type == "tcp":
                self.sock.sendall(full_cmd.encode())
            self._log(f"Sent command: {repr(full_cmd)}")
        except Exception as ex:
            self._log(f"Failed to send command '{command}': {ex}")
            raise

    def _read_reply(self):
        """Read and return lines from the device."""
        lines_out = []
        try:
            raw_data = None
            if self.connection_type == "serial":
                raw_data = self.ser.read(1024)
            elif self.connection_type == "tcp":
                try:
                    raw_data = self.sock.recv(1024)
                except socket.timeout:
                    self._log("TCP read timeout.", logging.WARNING)
                    return []

            if not raw_data:
                self._log("No data received.", logging.WARNING)
                return []

            self._log(f"Raw received: {repr(raw_data)}")
            lines = raw_data.decode(errors="replace").splitlines()
            for line in lines:
                stripped = line.strip()
                if stripped:
                    lines_out.append(stripped)
            return lines_out
        except (serial.SerialException, socket.error, ValueError) as ex:
            self._log(f"Failed to read reply: {ex}", logging.ERROR)
            return []

    def _send_and_read(self, command: str):
        """Send a command and read the reply."""
        if self.connected:
            self._send_command(command)
            time.sleep(0.2)  # wait a bit for device to reply
            return self._read_reply()
        self._log(f"Failed to send command '{command}': Not connected", logging.ERROR)
        return []

    def _log(self, message, level=logging.DEBUG):
        """ output log message

        :param message: String message
        :param level: Log level
        """
        # logging set up
        if self.logger:
            self.logger.log(level, message)
        # logging not set up
        else:
            log_type = logging.getLevelName(level)
            # print everything
            if self.verbose:
                print(log_type + ": " + message)
            # only print warnings or worse
            else:
                if level >= logging.WARNING:
                    print(log_type + ":", message)
        if level >= logging.WARNING:
            self.last_error = message

    # --- User-Facing Methods (synchronous) ---
    def set_verbose(self, verbose: bool =True):
        """ Set verbose mode.

        :param verbose: Boolean, set to True to enable DEBUG level messages,
                        False to disable DEBUG level messages
        """
        self.verbose = verbose
        if self.logger:
            if self.verbose:
                self.logger.setLevel(logging.DEBUG)
            else:
                self.logger.setLevel(logging.INFO)

    def get_status(self):
        """Get the status of the Sunpower cryocooler."""
        return self._send_and_read("STATUS")

    def get_error(self):
        """Get the last error message from the Sunpower cryocooler."""
        return parse_single_value(self._send_and_read("ERROR"))

    def get_version(self):
        """Get the firmware version of the Sunpower cryocooler."""
        return parse_single_value(self._send_and_read("VERSION"))

    def get_cold_head_temp(self):
        """Get the temperature of the cold head."""
        return parse_single_value(self._send_and_read("TC"))

    def get_reject_temp(self):
        """Get the temperature of the reject heat."""
        return parse_single_value(self._send_and_read("TEMP RJ"))

    def get_target_temp(self):
        """Get the target temperature set for the cryocooler."""
        return parse_single_value(self._send_and_read("TTARGET"))

    def set_target_temp(self, temp_kelvin: float):
        """Set the target temperature for the cryocooler in Kelvin."""
        return parse_single_value(self._send_and_read(f"TTARGET={temp_kelvin}"))

    def get_measured_power(self):
        """Get the measured power of the cryocooler."""
        return parse_single_value(self._send_and_read("P"))

    def get_commanded_power(self):
        """Get the commanded power of the cryocooler."""
        return parse_single_value(self._send_and_read("PWOUT"))

    def set_commanded_power(self, watts: float):
        """Set the commanded power for the cryocooler in watts."""
        return parse_single_value(self._send_and_read(f"PWOUT={watts}"))

    def turn_on_cooler(self):
        """Turn on the cryocooler."""
        return parse_single_value(self._send_and_read("COOLER=ON"))

    def turn_off_cooler(self):
        """Turn off the cryocooler."""
        return parse_single_value(self._send_and_read("COOLER=OFF"))
