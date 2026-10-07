#!/usr/bin/env python3
"""TCP client transport for ``gripper_server.py``.

Wire protocol: one JSON object per line.

Request::

    {"cmd": "move", "pos": 100, "speed": 255, "force": 0, "timeout": 10.0}\\n

Response::

    {"ok": true, "result": {"status_code": 249, "position_raw": 100, ...}}\\n
    {"ok": false, "error": "..."}\\n

The richer command line interface lives in :mod:`xcore_gripper_2f85.cli`; this module
keeps the original ``gripper_client.py HOST cmd`` invocation working.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from typing import Any, Dict, Optional, Sequence

DEFAULT_HOST = os.environ.get("GRIPPER_HOST", "192.168.2.225")
try:
    DEFAULT_PORT = int(os.environ.get("GRIPPER_PORT", "5005"))
except ValueError:  # pragma: no cover - misconfigured environment
    DEFAULT_PORT = 5005
DEFAULT_TIMEOUT = 10.0
COMMANDS = ("activate", "status", "open", "close", "move")


class GripperConnectionError(RuntimeError):
    """Raised when the gripper server cannot be reached or answers garbage."""


def send_command(
    host: str,
    port: int,
    payload: Dict[str, Any],
    timeout: float,
) -> Dict[str, Any]:
    """Send one JSON request and return the decoded JSON response."""

    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
    except OSError as exc:
        raise GripperConnectionError(
            f"cannot reach gripper server {host}:{port} ({exc})"
        ) from exc

    if not data:
        raise GripperConnectionError(
            f"empty response from gripper server {host}:{port}"
        )

    text = data.decode("utf-8", errors="replace").strip()
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GripperConnectionError(
            f"invalid JSON from gripper server {host}:{port}: {text!r}"
        ) from exc
    if not isinstance(decoded, dict):
        raise GripperConnectionError("gripper server returned a non-object response")
    return decoded


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Robotiq 2F gripper TCP client")
    parser.add_argument(
        "host",
        nargs="?",
        default=DEFAULT_HOST,
        help=f"IP of the machine connected to the gripper USB (default: {DEFAULT_HOST})",
    )
    parser.add_argument("cmd", choices=COMMANDS)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--pos", type=int, help=f"raw target position for move: 0=open, 255=close"
    )
    parser.add_argument("--speed", type=int, default=255)
    parser.add_argument("--force", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    payload: Dict[str, Any] = {
        "cmd": args.cmd,
        "speed": args.speed,
        "force": args.force,
        "timeout": args.timeout,
    }
    if args.cmd == "move":
        if args.pos is None:
            raise SystemExit("move requires --pos, for example --pos 100")
        payload["pos"] = args.pos

    try:
        response = send_command(
            args.host, args.port, payload, timeout=args.timeout + 1.0
        )
    except GripperConnectionError as exc:
        print(f"错误：{exc}")
        return 1
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
