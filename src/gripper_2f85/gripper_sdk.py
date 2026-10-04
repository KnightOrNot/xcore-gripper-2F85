#!/usr/bin/env python3
"""Small Python SDK for ``gripper_server.py``.

Typical usage::

    from gripper_2f85 import Robotiq2F85

    gripper = Robotiq2F85("192.168.2.225")
    gripper.open()
    gripper.close(force=80)
    gripper.move(pos=100)              # raw Robotiq position
    gripper.move_closure(0.4)          # 0.0 = fully open, 1.0 = fully closed

Position conventions:

* raw ``pos``        0 = fully open, 255 = fully closed.
* ``closure``        0.0 = fully open, 1.0 = fully closed.  This is the same
  direction as the GELLO leader gripper axis computed by
  ``gello.robots.dynamixel.DynamixelRobot`` from ``gripper_config``, so a leader
  value maps onto :meth:`Robotiq2F85.move_closure` without extra inversion.
* ``openness``       1.0 = fully open, 0.0 = fully closed.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:  # installed package
    from gripper_2f85.gripper_client import (
        DEFAULT_HOST,
        DEFAULT_PORT,
        DEFAULT_TIMEOUT,
        GripperConnectionError,
        send_command,
    )
except ImportError:  # executed as a loose script from src/gripper_2f85/
    from gripper_client import (  # type: ignore[no-redef]
        DEFAULT_HOST,
        DEFAULT_PORT,
        DEFAULT_TIMEOUT,
        GripperConnectionError,
        send_command,
    )

MAX_POSITION = 255
MAX_WIDTH_MM = 50.0


class GripperSDKError(RuntimeError):
    """Raised when the gripper server reports an error or returns bad data."""


def closure_to_pos(
    closure: float,
    open_pos: int = 0,
    closed_pos: int = MAX_POSITION,
) -> int:
    """Map a normalized closure value onto the raw 0..255 Robotiq position.

    ``0.0`` (fully open) maps to ``open_pos``; ``1.0`` (fully closed) maps to
    ``closed_pos``.  Values outside ``[0, 1]`` are clamped.

    The default ``open_pos=0`` / ``closed_pos=255`` are the protocol endpoints.
    A real 2F-85 has a small mechanical deadband at each end (measured on this
    unit: fully open lands at raw ≈2 and fully closed at raw ≈230 even with
    ``force=255``), so pass the measured endpoints to use the whole leader
    travel when teleoperating.
    """

    if closure != closure:  # NaN
        raise ValueError("closure must be a finite number")
    if not 0 <= open_pos <= MAX_POSITION or not 0 <= closed_pos <= MAX_POSITION:
        raise ValueError("open_pos and closed_pos must be within 0..255")
    clamped = min(1.0, max(0.0, float(closure)))
    return int(round(open_pos + clamped * (closed_pos - open_pos)))


def pos_to_closure(pos: Any) -> float:
    """Map a raw 0..255 Robotiq position onto the normalized closure value."""

    if not isinstance(pos, (int, float)) or pos != pos:
        raise ValueError(f"position must be a number, got {pos!r}")
    return min(1.0, max(0.0, float(pos) / MAX_POSITION))


def pos_to_width_mm(pos: Any) -> float:
    """Convert a raw position to the millimetre opening reported by the server."""

    if not isinstance(pos, (int, float)) or pos != pos:
        raise ValueError(f"position must be a number, got {pos!r}")
    return round(MAX_WIDTH_MM - (MAX_WIDTH_MM / MAX_POSITION) * float(pos), 2)


class Robotiq2F85:
    """Thin client for the TCP gripper server.

    Every method performs one request/response round trip; there is no
    persistent connection, so an instance is cheap and thread-safe enough for
    occasional polling.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
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

    def move_closure(
        self,
        closure: float,
        speed: int = 255,
        force: int = 0,
        timeout: Optional[float] = None,
        open_pos: int = 0,
        closed_pos: int = MAX_POSITION,
    ) -> Dict[str, Any]:
        """Move using the normalized GELLO convention (0=open, 1=closed).

        ``open_pos`` / ``closed_pos`` let a calibrated mechanical range (for
        example ``open_pos=2, closed_pos=230``) replace the protocol endpoints.
        """

        return self.move(
            pos=closure_to_pos(closure, open_pos=open_pos, closed_pos=closed_pos),
            speed=speed,
            force=force,
            timeout=timeout,
        )

    def move_openness(
        self,
        openness: float,
        speed: int = 255,
        force: int = 0,
        timeout: Optional[float] = None,
        open_pos: int = 0,
        closed_pos: int = MAX_POSITION,
    ) -> Dict[str, Any]:
        """Move using the human convention (1=open, 0=closed)."""

        return self.move_closure(
            closure=1.0 - openness,
            speed=speed,
            force=force,
            timeout=timeout,
            open_pos=open_pos,
            closed_pos=closed_pos,
        )

    def closure(self, timeout: Optional[float] = None) -> float:
        """Read one status sample and return the normalized closure value."""

        return pos_to_closure(self.status(timeout=timeout).get("position_raw"))

    def _command(
        self, cmd: str, timeout: Optional[float] = None, **kwargs: Any
    ) -> Dict[str, Any]:
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
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    speed: int = 255,
    force: int = 0,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    return Robotiq2F85(host, port=port, timeout=timeout).open(speed=speed, force=force)


def close_gripper(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    speed: int = 255,
    force: int = 80,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    return Robotiq2F85(host, port=port, timeout=timeout).close(speed=speed, force=force)
