"""
A Python class to control a Sunpower cryocooler via serial or TCP connection.
"""
import socket
import time
from typing import Union
import serial

from hardware_device_base.hardware_sensor_base import HardwareSensorBase


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

class SunpowerCryocooler(HardwareSensorBase):
    """A class to control a Sunpower cryocooler via serial or TCP connection."""
    # pylint: disable=too-many-instance-attributes
    def __init__(self, log: bool = True, logfile: str = __name__.rsplit(".", 1)[-1],
                 read_timeout: float = 1.0):
        """ Initialize the SunpowerCryocooler."""

        super().__init__(log, logfile)
        self.con_type = None
        self.read_timeout = read_timeout
        self.ser = None
        self.sock = None

    def connect(self, host, port, con_type: str ="tcp"):  # pylint: disable=W0221
        """Connect to the Sunpower controller."""
        if self.validate_connection_params((host, port)):
            try:
                if con_type == "serial":
                    self.ser = serial.Serial(
                        port=host,
                        baudrate=port,
                        timeout=self.read_timeout,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                    )
                    self.report_info(f"Serial connection opened: {self.ser.is_open}")
                    self._set_connected(True)
                    self.con_type = con_type
                elif con_type == "tcp":
                    self.sock = socket.create_connection((host, port), timeout=2)
                    self.sock.settimeout(self.read_timeout)
                    self.report_info(f"TCP connection opened: {host}:{port}")
                    self._set_connected(True)
                    self.con_type = con_type
                else:
                    self._set_connected(False)
                    self.report_error("connection_type must be 'serial' or 'tcp'")
            except Exception as ex:
                self._set_connected(False)
                self.report_error(f"Failed to establish connection: {ex}")
                raise IOError(f"Failed to establish connection: {ex}") from ex
        else:
            self.report_error(f"Invalid connection parameters: {host}:{port}")
            self._set_connected(False)

    def disconnect(self):
        """Close the connection."""
        if not self.is_connected():
            self.report_warning("Already disconnected from device.")
            return
        try:
            if self.con_type == "serial":
                self.ser.close()
                self.report_info("Serial connection closed.")
            elif self.con_type == "tcp":
                self.sock.close()
                self.report_info("TCP connection closed.")
            self._set_connected(False)
        except Exception as ex:
            raise IOError(f"Failed to close connection: {ex}") from ex
        self.report_info("Disconnected from device")

    def _send_command(self, command: str) -> bool:  # pylint: disable=W0221
        """Send a command to the Sunpower controller."""
        if not self.is_connected():
            self.report_error("Device is not connected.")
            return False

        full_cmd = f"{command}\r"
        try:
            self.logger.debug("Sending command: %s", full_cmd)
            if self.con_type == "serial":
                self.ser.write(full_cmd.encode())
            elif self.con_type == "tcp":
                self.sock.sendall(full_cmd.encode())
        except Exception as ex:
            self.report_error(f"Failed to send command: {ex}")
            raise IOError(f"Failed to send command: {ex}") from ex
        self.logger.debug("Command sent")
        return True

    def _read_reply(self) -> list:
        """Read and return lines from the device."""
        if not self.is_connected():
            self.report_error("Device is not connected.")
            return []

        lines_out = []
        try:
            raw_data = None
            if self.con_type == "serial":
                raw_data = self.ser.read(1024)
            elif self.con_type == "tcp":
                try:
                    raw_data = self.sock.recv(1024)
                except socket.timeout:
                    self.report_warning("TCP read timeout.", errno=-1)
                    return []

            if not raw_data:
                self.report_warning("No data received.", errno=-1)
                return []

            self.logger.debug("Raw received: %s", repr(raw_data))
            lines = raw_data.decode(errors="replace").splitlines()
            for line in lines:
                stripped = line.strip()
                if stripped:
                    lines_out.append(stripped)
            return lines_out
        except (serial.SerialException, socket.error, ValueError) as ex:
            self.report_error(f"Failed to read reply: {ex}")
            return []

    def _send_and_read(self, command: str):
        """Send a command and read the reply."""
        if self.is_connected():
            self._send_command(command)
            time.sleep(0.2)  # wait a bit for device to reply
            return self._read_reply()
        self.report_error(f"Failed to send command '{command}': Not connected")
        return []

    # --- User-Facing Methods (synchronous) ---
    def get_atomic_value(self, item: str ="") -> Union[float, int, str, None]:
        """Get the atomic value from the Sunpower cryocooler."""
        retval = None
        if item == "cold_head_temp":
            retval = self.get_cold_head_temp()
        elif item == "reject_temp":
            retval = self.get_reject_temp()
        elif item == "target_temp":
            retval = self.get_target_temp()
        elif item == "measured_power":
            retval = self.get_measured_power()
        elif item == "commanded_power":
            retval = self.get_commanded_power()
        elif item == "current_commanded_power":
            retval = self.get_current_commanded_power()
        else:
            self.report_error(f"Unknown item: {item}")
        return retval

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

    def get_current_commanded_power(self):
        """Get the current commanded power of the cryocooler."""
        retval = self._send_and_read("E")
        return float(retval[3])

    def set_commanded_power(self, watts: float):
        """Set the commanded power for the cryocooler in watts."""
        return parse_single_value(self._send_and_read(f"PWOUT={watts}"))

    def turn_on_cooler(self):
        """Turn on the cryocooler."""
        return parse_single_value(self._send_and_read("COOLER=ON"))

    def turn_off_cooler(self):
        """Turn off the cryocooler."""
        return parse_single_value(self._send_and_read("COOLER=OFF"))
