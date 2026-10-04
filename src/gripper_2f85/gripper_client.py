#!/usr/bin/env python3
"""Command-line client for gripper_server.py."""

import argparse
import json
import socket
from typing import Any, Dict


def send_command(host: str, port: int, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    if not data:
        raise RuntimeError("empty response from gripper server")
    return json.loads(data.decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Robotiq 2F gripper TCP client")
    parser.add_argument("host", help="IP of the Ubuntu machine connected to the gripper USB")
    parser.add_argument("cmd", choices=["activate", "status", "open", "close", "move"])
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--pos", type=int, help="Target position for move: 0=open, 255=close")
    parser.add_argument("--speed", type=int, default=255)
    parser.add_argument("--force", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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

    response = send_command(args.host, args.port, payload, timeout=args.timeout + 1.0)
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
