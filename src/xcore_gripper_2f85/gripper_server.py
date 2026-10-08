#!/usr/bin/env python3
"""TCP server for a Robotiq 2F gripper connected by USB/RS485.

Run this script on the Ubuntu machine that has the gripper USB cable plugged in.
The control PC can then send JSON commands over the network.
"""

import argparse
import json
import math
import signal
import socketserver
import threading
import time
from typing import Any, Dict, Optional, Tuple

import serial.tools.list_ports

try:  # installed package
    from xcore_gripper_2f85 import robtiq_gripper_mdbsrtu as GRP
except ImportError:  # executed as a loose script from src/xcore_gripper_2f85/
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
        self._stream_deadline = None
        self._stream_error = None
        self._last_target = None
        self._closing = threading.Event()
        self._watchdog_thread = threading.Thread(target=self._watchdog, daemon=True)
        if activate_on_start:
            try:
                self.activate()
            except BaseException:
                self._gripper.serclose()
                raise
        self._watchdog_thread.start()

    def activate(self, timeout: float = 10.0) -> Dict[str, Any]:
        with self._lock:
            self._reject_stream_unlocked()
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
            self._reject_stream_unlocked()
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
        self._closing.set()
        self._watchdog_thread.join(timeout=2)
        with self._lock:
            try:
                if self._stream_deadline is not None:
                    self._stop_unlocked()
            finally:
                self._gripper.serclose()

    def follow_status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(
                self._read_status_unlocked(),
                streaming=True,
                stream_error=self._stream_error,
            )

    def set_target(
        self,
        pos: int,
        speed: int = 150,
        force: int = 0,
        stale_timeout: float = 1.5,
    ) -> Dict[str, Any]:
        """Accept a new target without waiting for the fingers to reach it.

        Repeated targets refresh the watchdog and read feedback without issuing
        another grip command. Serial transactions are still serialized.
        """
        target = tuple(
            clamp_byte(v, name)
            for v, name in ((pos, "pos"), (speed, "speed"), (force, "force"))
        )
        if not math.isfinite(stale_timeout) or not 0.5 <= stale_timeout <= 10:
            raise ValueError("stale_timeout must be in [0.5,10] seconds")
        with self._lock:
            if self._closing.is_set() or self._stream_error:
                raise RuntimeError(self._stream_error or "Gripper is closing")
            try:
                self._stream_deadline = time.monotonic() + stale_timeout
                if target != self._last_target:
                    self._gripper.grip(list(target))
                    self._last_target = target
                state = self._read_status_unlocked()
                if state["status_code"] & 0x31 != 0x31:
                    raise RuntimeError("Gripper lost activation")
                return state
            except Exception as exc:
                self._stream_error = str(exc)
                try:
                    self._stop_unlocked()
                except Exception as stop_exc:
                    self._stream_error += f"; stop failed: {stop_exc}"
                raise

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self._stop_unlocked()
            self._stream_error = None
            return self._read_status_unlocked()

    def _stop_unlocked(self) -> None:
        self._stream_deadline = None
        self._last_target = None
        self._gripper.stop()

    def _reject_stream_unlocked(self) -> None:
        if self._stream_deadline is not None:
            raise RuntimeError(
                "Gripper following is active; stop it before manual commands"
            )

    def _watchdog(self) -> None:
        while not self._closing.wait(0.05):
            with self._lock:
                if (
                    self._stream_deadline is not None
                    and time.monotonic() > self._stream_deadline
                ):
                    self._stream_error = "Gripper target stream timed out"
                    try:
                        self._stop_unlocked()
                    except Exception as exc:
                        self._stream_error += f"; stop failed: {exc}"
                    print(self._stream_error, flush=True)

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
        elif command == "follow_status":
            result = controller.follow_status()
        elif command == "set_target":
            result = controller.set_target(
                pos=request.get("pos"),
                speed=request.get("speed", 150),
                force=request.get("force", 0),
                stale_timeout=float(request.get("stale_timeout", 1.5)),
            )
        elif command == "stop":
            result = controller.stop()
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
            raise ValueError(
                "cmd must be activate, status, open, close, move, "
                "follow_status, set_target or stop"
            )

        return {"ok": True, "result": result}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Robotiq 2F gripper TCP server")
    parser.add_argument("--host", default="0.0.0.0", help="IP to listen on")
    parser.add_argument("--port", type=int, default=5005, help="TCP port to listen on")
    parser.add_argument(
        "--serial-port", help="Gripper serial port, for example /dev/ttyUSB0"
    )
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

    try:
        controller = GripperController(serial_port, activate_on_start=not args.no_activate)
    except OSError as exc:
        raise SystemExit(f"Cannot initialize gripper on {serial_port}: {exc}") from exc
    server = GripperTCPServer((args.host, args.port), GripperRequestHandler, controller)
    print(f"Gripper server listening on {args.host}:{args.port}, serial={serial_port}")

    def interrupt(*_args: Any) -> None:
        raise KeyboardInterrupt

    old_term = signal.signal(signal.SIGTERM, interrupt)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping gripper server")
    finally:
        try:
            server.server_close()
            controller.close()
        finally:
            signal.signal(signal.SIGTERM, old_term)


if __name__ == "__main__":
    main()
