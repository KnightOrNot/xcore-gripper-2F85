#!/usr/bin/env python3
"""Unified command-line interface for the Robotiq 2F-85 gripper server.

The gripper itself hangs off a USB/RS485 port on the machine that runs
``gripper_server.py``.  This CLI only speaks the TCP JSON protocol, so it can
run on any control PC on the same network::

    uv run xcore-gripper-2f85 status
    uv run xcore-gripper-2f85 open --speed 150
    uv run xcore-gripper-2f85 move --pos 100          # 0 = fully open, 255 = fully closed
    uv run xcore-gripper-2f85 move --closure 0.4      # 0.0 = fully open, 1.0 = fully closed
    uv run xcore-gripper-2f85 watch --interval 0.2    # real-time observation (Ctrl-C stops)

Position conventions used everywhere in this file:

* ``pos``       raw Robotiq value, 0 = fully open, 255 = fully closed.
* ``closure``   normalized 0.0 = fully open, 1.0 = fully closed.  This matches
  the GELLO leader gripper axis (see ``gripper_config`` in the gello configs),
  so a leader value can be mapped straight onto ``--closure``.
* ``openness``  1.0 = fully open, 0.0 = fully closed; only for humans.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

try:  # installed package
    from xcore_gripper_2f85.configuration import Config, load_config
    from xcore_gripper_2f85.gripper_client import (
        GripperConnectionError,
    )
    from xcore_gripper_2f85.gripper_sdk import (
        MAX_POSITION,
        GripperSDKError,
        Robotiq2F85,
        closure_to_pos,
        pos_to_closure,
    )
except ImportError:  # executed as a loose script from src/xcore_gripper_2f85/
    from configuration import Config, load_config  # type: ignore[no-redef]
    from gripper_client import (  # type: ignore[no-redef]
        GripperConnectionError,
    )
    from gripper_sdk import (  # type: ignore[no-redef]
        MAX_POSITION,
        GripperSDKError,
        Robotiq2F85,
        closure_to_pos,
        pos_to_closure,
    )

EXIT_OK = 0
EXIT_FAILURE = 1

# Status byte meanings documented by the vendor demo (robtiq_gripper_mdbsrtu.py).
STATUS_LABELS: Dict[int, str] = {
    0x31: "已激活/待命",
    0x39: "运动中",
    0x79: "外撑到位(检测到物体)",
    0xB9: "夹取到位(检测到物体)",
    0xF9: "到位(无物体)",
}


def decode_status(code: Any) -> str:
    """Return a human label for a Robotiq status byte."""

    if not isinstance(code, int):
        return "未知"
    return STATUS_LABELS.get(code, "未知")


_CONFIG: Optional[Config] = None


def _active_config() -> Config:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_config()
    return _CONFIG


def _add_connection_args(parser: argparse.ArgumentParser) -> None:
    config = _active_config()
    parser.add_argument(
        "--host",
        default=None,
        help=f"control PC running gripper_server.py (default: {config.client.host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"TCP port of gripper_server.py (default: {config.client.port})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=config.client.timeout_s,
        help=f"per-command timeout in seconds (default: {config.client.timeout_s:g})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print the raw server response as JSON",
    )


def _add_motion_args(parser: argparse.ArgumentParser) -> None:
    config = _active_config()
    parser.add_argument(
        "--speed",
        type=int,
        default=config.client.speed,
        help=f"motion speed 0-255 (default: {config.client.speed})",
    )
    parser.add_argument(
        "--force",
        type=int,
        default=config.client.force,
        help="gripping force 0-255; 0 is the gentlest value "
        f"(default: {config.client.force})",
    )


def build_parser(config: Optional[Config] = None) -> argparse.ArgumentParser:
    global _CONFIG
    if config is not None:
        _CONFIG = config
    config = _active_config()
    parser = argparse.ArgumentParser(
        prog="xcore-gripper-2f85",
        description="Control a Robotiq 2F-85 gripper through gripper_server.py",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="TOML defaults file (default: <repository>/config/default.toml)",
    )
    # ``gripper 192.168.2.225 status`` stays valid for backwards compatibility.
    parser.add_argument(
        "host_pos",
        nargs="?",
        metavar="HOST",
        help="alias for --host, kept for the original client invocation",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="read one status sample")
    _add_connection_args(status)

    activate = sub.add_parser("activate", help="activate (reset + enable) the gripper")
    _add_connection_args(activate)

    open_cmd = sub.add_parser("open", help="fully open the gripper (pos=0)")
    _add_connection_args(open_cmd)
    _add_motion_args(open_cmd)

    close_cmd = sub.add_parser("close", help="fully close the gripper (pos=255)")
    _add_connection_args(close_cmd)
    _add_motion_args(close_cmd)

    move = sub.add_parser("move", help="move to a target position and wait")
    _add_connection_args(move)
    _add_motion_args(move)
    target = move.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--pos",
        type=int,
        help=f"raw target position 0-{MAX_POSITION} (0=open, {MAX_POSITION}=closed)",
    )
    target.add_argument(
        "--closure",
        type=float,
        help="normalized target 0.0=fully open, 1.0=fully closed (GELLO convention)",
    )
    target.add_argument(
        "--openness",
        type=float,
        help="normalized target 1.0=fully open, 0.0=fully closed",
    )
    move.add_argument(
        "--open-pos",
        type=int,
        default=config.motion.open_pos,
        help="raw position treated as fully open when using --closure/--openness "
        f"(default: {config.motion.open_pos}; measured mechanical open is about 2)",
    )
    move.add_argument(
        "--closed-pos",
        type=int,
        default=config.motion.closed_pos,
        help="raw position treated as fully closed when using --closure/--openness "
        f"(default: {config.motion.closed_pos}; measured mechanical closed is about 230)",
    )

    watch = sub.add_parser(
        "watch", help="stream status samples for real-time observation"
    )
    _add_connection_args(watch)
    watch.add_argument(
        "--interval",
        type=float,
        default=config.watch.interval_s,
        help=f"sampling period in seconds (default: {config.watch.interval_s:g})",
    )
    watch.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="stop after N seconds; 0 means run until Ctrl-C (default: 0)",
    )
    watch.add_argument(
        "--format",
        choices=("table", "csv", "jsonl"),
        default="table",
        help="output format for streamed samples (default: table)",
    )
    watch.add_argument(
        "--samples",
        type=int,
        default=0,
        help="stop after N samples; 0 means unbounded (default: 0)",
    )

    return parser


def _resolve_connection(args: argparse.Namespace) -> Robotiq2F85:
    config = _active_config()
    host = args.host or args.host_pos or config.client.host
    port = args.port if args.port is not None else config.client.port
    return Robotiq2F85(host, port=port, timeout=args.timeout)


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _print_result(result: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        _print_json(result)
        return
    if "activated" in result:
        print("夹爪已激活" if result["activated"] else "夹爪激活失败")
        return
    pos = result.get("position_raw")
    print(
        "status_code={code} ({label}) position_raw={pos} position_mm={mm} moving={moving}".format(
            code=result.get("status_code"),
            label=decode_status(result.get("status_code")),
            pos=pos,
            mm=result.get("position_mm"),
            moving=result.get("moving"),
        )
    )
    if isinstance(pos, int):
        closure = pos_to_closure(pos)
        print(f"closure={closure:.3f} (0=全开, 1=全闭) openness={1.0 - closure:.3f}")


def _parse_non_negative(value: float, name: str) -> float:
    if value < 0:
        raise SystemExit(f"{name} must be non-negative")
    return value


def _target_pos(args: argparse.Namespace) -> int:
    if args.pos is not None:
        if not 0 <= args.pos <= MAX_POSITION:
            raise SystemExit(f"--pos must be within 0..{MAX_POSITION}")
        return args.pos
    if args.closure is not None:
        value = args.closure
    else:
        value = 1.0 - args.openness
    return closure_to_pos(value, open_pos=args.open_pos, closed_pos=args.closed_pos)


def _run_watch(gripper: Robotiq2F85, args: argparse.Namespace) -> int:
    interval = _parse_non_negative(args.interval, "--interval")
    duration = _parse_non_negative(args.duration, "--duration")
    if interval == 0:
        raise SystemExit("--interval must be greater than 0")
    if args.samples < 0:
        raise SystemExit("--samples must be non-negative")

    writer: Optional[Any] = None
    if args.format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(
            [
                "wall_time",
                "status_code",
                "status",
                "position_raw",
                "position_mm",
                "closure",
                "moving",
            ]
        )
    elif args.format == "table" and not args.as_json:
        print(
            f"{'时间':<20} {'状态':<20} {'pos':>4} {'开度mm':>8} {'闭合度':>7} {'运动中':>6}"
        )

    deadline = None if duration == 0 else time.monotonic() + duration
    samples = 0
    try:
        while True:
            sample = gripper.status()
            samples += 1
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            pos = sample.get("position_raw")
            closure = pos_to_closure(pos) if isinstance(pos, int) else None
            if args.format == "jsonl" or args.as_json:
                print(
                    json.dumps(
                        {
                            "wall_time": now,
                            "monotonic_ns": time.monotonic_ns(),
                            **sample,
                            "closure": closure,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            elif args.format == "csv":
                assert writer is not None
                writer.writerow(
                    [
                        now,
                        sample.get("status_code"),
                        decode_status(sample.get("status_code")),
                        pos,
                        sample.get("position_mm"),
                        "" if closure is None else f"{closure:.4f}",
                        sample.get("moving"),
                    ]
                )
                sys.stdout.flush()
            else:
                closure_text = "  n/a" if closure is None else f"{closure:7.3f}"
                print(
                    f"{now:<20} "
                    f"{str(sample.get('status_code')) + ' ' + decode_status(sample.get('status_code')):<20} "
                    f"{str(pos):>4} "
                    f"{str(sample.get('position_mm')):>8} "
                    f"{closure_text} "
                    f"{str(sample.get('moving')):>6}",
                    flush=True,
                )

            if args.samples and samples >= args.samples:
                break
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n已停止采样", file=sys.stderr)
    return EXIT_OK


def _config_path(argv: Sequence[str]) -> Optional[Path]:
    for index, value in enumerate(argv):
        if value == "--config" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if value.startswith("--config="):
            return Path(value.split("=", 1)[1])
    return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        config = load_config(_config_path(arguments))
    except (OSError, ValueError) as exc:
        print(f"invalid configuration: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    args = build_parser(config).parse_args(arguments)

    try:
        gripper = _resolve_connection(args)
        if args.command == "watch":
            return _run_watch(gripper, args)
        if args.command == "status":
            result = gripper.status()
        elif args.command == "activate":
            result = gripper.activate()
        elif args.command == "open":
            result = gripper.open(speed=args.speed, force=args.force)
        elif args.command == "close":
            result = gripper.close(speed=args.speed, force=args.force)
        elif args.command == "move":
            result = gripper.move(
                pos=_target_pos(args), speed=args.speed, force=args.force
            )
        else:  # pragma: no cover - argparse enforces the choices
            raise SystemExit(f"unknown command {args.command!r}")
    except (GripperConnectionError, GripperSDKError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return EXIT_FAILURE

    _print_result(result, args.as_json)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
