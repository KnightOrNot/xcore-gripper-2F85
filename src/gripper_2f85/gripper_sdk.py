#!/usr/bin/env python3
"""Small Python SDK for gripper_server.py.

Typical usage:

    from gripper_sdk import Robotiq2F85

    gripper = Robotiq2F85("192.168.2.225")
    gripper.open()
    gripper.close(force=80)
"""

from typing import Any, Dict, Optional

from gripper_client import send_command


DEFAULT_PORT = 5005
DEFAULT_TIMEOUT = 10.0


class GripperSDKError(RuntimeError):
    """Raised when the gripper server reports an error or returns bad data."""


class Robotiq2F85:
    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def activate(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        return self._command("activate", timeout=timeout)

    def status(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        return self._command("status", timeout=timeout)

    def open(
        self,
        speed: int = 255,
        force: int = 0,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        return self._command("open", speed=speed, force=force, timeout=timeout)

    def close(
        self,
        speed: int = 255,
        force: int = 80,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        return self._command("close", speed=speed, force=force, timeout=timeout)

    def move(
        self,
        pos: int,
        speed: int = 255,
        force: int = 0,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        return self._command("move", pos=pos, speed=speed, force=force, timeout=timeout)

    def _command(self, cmd: str, timeout: Optional[float] = None, **kwargs: Any) -> Dict[str, Any]:
        command_timeout = self.timeout if timeout is None else timeout
        payload: Dict[str, Any] = {"cmd": cmd, "timeout": command_timeout}
        payload.update(kwargs)

        response = send_command(
            self.host,
            self.port,
            payload,
            timeout=command_timeout + 1.0,
        )
        if not response.get("ok"):
            raise GripperSDKError(response.get("error", "unknown gripper server error"))
        result = response.get("result")
        if not isinstance(result, dict):
            raise GripperSDKError("gripper server returned an invalid result")
        return result


def open_gripper(
    host: str,
    port: int = DEFAULT_PORT,
    speed: int = 255,
    force: int = 0,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    return Robotiq2F85(host, port=port, timeout=timeout).open(speed=speed, force=force)


def close_gripper(
    host: str,
    port: int = DEFAULT_PORT,
    speed: int = 255,
    force: int = 80,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    return Robotiq2F85(host, port=port, timeout=timeout).close(speed=speed, force=force)
