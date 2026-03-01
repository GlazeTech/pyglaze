from __future__ import annotations

import serial
import serial.tools.list_ports

APP_NAME = "Glaze"
LOGGER_NAME = "glaze-logger"


def list_serial_ports() -> list[str]:
    """Lists available serial ports for device conneciton.

    Returns:
        list[str]: Paths to available ports.
    """
    skip_ports_substrings = ["Bluetooth", "debug"]

    ports = []
    for port in serial.tools.list_ports.comports():
        if any(substring in port.device for substring in skip_ports_substrings):
            continue
        ports.append(port.device)
    return ports
