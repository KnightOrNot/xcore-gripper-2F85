#!/usr/bin/env python3
"""TCP server for a Robotiq 2F gripper connected by USB/RS485.

Run this script on the Ubuntu machine that has the gripper USB cable plugged in.
The control PC can then send JSON commands over the network.
"""

import argparse
import json
import os
import socketserver
import threading
import time
from typing import Any, Dict, Optional, Tuple

import serial.tools.list_ports

try:  # installed package
    from gripper_2f85 import robtiq_gripper_mdbsrtu as GRP
except ImportError:  # executed as a loose script from src/gripper_2f85/
    import robtiq_gripper_mdbsrtu as GRP  # type: ignore[no-redef]


MOVING_STATUS = 0x39


def find_usb_serial_port() -> Optional[str]:
    """Return the first USB serial adapter, or ``None`` when there is none.

    Deliberately does not fall back to hardware ``/dev/ttyS*`` ports: opening
    one by accident reports a confusing permission error instead of the real
    problem (the gripper USB adapter is not plugged in).
    """

    ports = list(serial.tools.list_ports.comports())
    for info in ports:
        device = getattr(info, "device", str(info))
        description = " ".join(
            str(getattr(info, field, "") or "")
            for field in ("description", "hwid", "manufacturer", "product")
        )
        if "USB" in description.upper() or "USB" in device.upper():
            return device
    return None


def list_serial_ports() -> str:
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return "none"
    return ", ".join(getattr(info, "device", str(info)) for info in ports)


def clamp_byte(value: Any, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer from 0 to 255") from exc
    if not 0 <= number <= 255:
        raise ValueError(f"{name} must be from 0 to 255")
    return number


class GripperController:
    def __init__(self, port: str, activate_on_start: bool = True) -> None:
        self._lock = threading.Lock()
        self._gripper = GRP.Gripper(port)
        if activate_on_start:
            self.activate()

    def activate(self, timeout: float = 10.0) -> Dict[str, Any]:
        with self._lock:
            self._gripper.ClearrACT()
            self._gripper.activate()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self._gripper.isavtivated():
                    return {"activated": True}
            raise TimeoutError("gripper activation timed out")

    def move(
        self,
        pos: int,
        speed: int = 255,
        force: int = 0,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        pos = clamp_byte(pos, "pos")
        speed = clamp_byte(speed, "speed")
        force = clamp_byte(force, "force")

        with self._lock:
            self._gripper.grip([pos, speed, force])
            deadline = time.monotonic() + timeout
            status = self._read_status_unlocked()
            while status["status_code"] == MOVING_STATUS:
                if time.monotonic() >= deadline:
                    raise TimeoutError("gripper move timed out")
                status = self._read_status_unlocked()
            return status

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return self._read_status_unlocked()

    def close(self) -> None:
        with self._lock:
            self._gripper.serclose()

    def _read_status_unlocked(self) -> Dict[str, Any]:
        status_code, position_raw, position_mm = self._gripper.ReadGripperStatus()
        return {
            "status_code": status_code,
            "position_raw": position_raw,
            "position_mm": position_mm,
            "moving": status_code == MOVING_STATUS,
        }


class GripperTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(
        self,
        server_address: Tuple[str, int],
        handler_class: Any,
        controller: GripperController,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.controller = controller


class GripperRequestHandler(socketserver.StreamRequestHandler):
    server: GripperTCPServer

    def handle(self) -> None:
        line = self.rfile.readline(4096)
        if not line:
            return

        try:
            request = json.loads(line.decode("utf-8"))
            response = self.dispatch(request)
        except Exception as exc:  # Keep the network API simple for the caller.
            response = {"ok": False, "error": str(exc)}

        self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))

    def dispatch(self, request: Dict[str, Any]) -> Dict[str, Any]:
        command = request.get("cmd")
        controller = self.server.controller

        if command == "activate":
            result = controller.activate(timeout=float(request.get("timeout", 10.0)))
        elif command == "status":
            result = controller.status()
        elif command == "open":
            result = controller.move(
                pos=0,
                speed=request.get("speed", 255),
                force=request.get("force", 0),
                timeout=float(request.get("timeout", 10.0)),
            )
        elif command == "close":
            result = controller.move(
                pos=255,
                speed=request.get("speed", 255),
                force=request.get("force", 0),
                timeout=float(request.get("timeout", 10.0)),
            )
        elif command == "move":
            result = controller.move(
                pos=request.get("pos"),
                speed=request.get("speed", 255),
                force=request.get("force", 0),
                timeout=float(request.get("timeout", 10.0)),
            )
        else:
            raise ValueError("cmd must be one of: activate, status, open, close, move")

        return {"ok": True, "result": result}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Robotiq 2F gripper TCP server")
    parser.add_argument("--host", default="0.0.0.0", help="IP to listen on")
    parser.add_argument("--port", type=int, default=5005, help="TCP port to listen on")
    parser.add_argument("--serial-port", help="Gripper serial port, for example /dev/ttyUSB0")
    parser.add_argument(
        "--no-activate",
        action="store_true",
        help="Do not activate the gripper when the server starts",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    serial_port = args.serial_port or find_usb_serial_port()
    if not serial_port:
        raise SystemExit(
            "No USB serial port found (detected: "
            f"{list_serial_ports()}). Plug in the gripper adapter or pass "
            "--serial-port /dev/ttyUSB0"
        )

    controller = GripperController(serial_port, activate_on_start=not args.no_activate)
    server = GripperTCPServer((args.host, args.port), GripperRequestHandler, controller)
    print(f"Gripper server listening on {args.host}:{args.port}, serial={serial_port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping gripper server")
    finally:
        server.server_close()
        controller.close()


if __name__ == "__main__":
    main()
