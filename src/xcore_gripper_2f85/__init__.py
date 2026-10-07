"""Robotiq 2F-85 gripper control over the TCP JSON server.

Public API::

    from xcore_gripper_2f85 import Robotiq2F85, closure_to_pos, pos_to_closure

    gripper = Robotiq2F85("192.168.2.225")   # defaults to GRIPPER_HOST/GRIPPER_PORT
    gripper.activate()
    gripper.open()
    gripper.move_closure(0.5)                # 0.0 = fully open, 1.0 = fully closed
"""

from __future__ import annotations

from typing import Optional, Sequence

from xcore_gripper_2f85.gripper_client import (
    COMMANDS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    GripperConnectionError,
    send_command,
)
from xcore_gripper_2f85.gripper_sdk import (
    MAX_POSITION,
    MAX_WIDTH_MM,
    GripperSDKError,
    Robotiq2F85,
    close_gripper,
    closure_to_pos,
    open_gripper,
    pos_to_closure,
    pos_to_width_mm,
)

__version__ = "0.2.0"

__all__ = [
    "COMMANDS",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_TIMEOUT",
    "MAX_POSITION",
    "MAX_WIDTH_MM",
    "GripperConnectionError",
    "GripperSDKError",
    "Robotiq2F85",
    "close_gripper",
    "closure_to_pos",
    "main",
    "open_gripper",
    "pos_to_closure",
    "pos_to_width_mm",
    "send_command",
]


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Console entry point (``gripper``)."""

    from xcore_gripper_2f85.cli import main as cli_main

    return cli_main(argv)
