"""Validated defaults for the 2F-85 server and client from ``config/default.toml``."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10 are supported by this package.
    import tomli as tomllib


def _default_config_path() -> Path | None:
    package = Path(__file__).resolve().parent
    checkout = package.parents[1] / "config/default.toml"
    if checkout.exists():
        return checkout
    bundled = package / "default.toml"
    if bundled.exists():
        return bundled
    return None


DEFAULT_CONFIG = _default_config_path()


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 5005
    serial_port: str = ""
    activate: bool = True


@dataclass(frozen=True)
class ClientConfig:
    host: str = "192.168.2.225"
    port: int = 5005
    timeout_s: float = 10.0
    speed: int = 255
    force: int = 0


@dataclass(frozen=True)
class MotionConfig:
    open_pos: int = 0
    closed_pos: int = 255


@dataclass(frozen=True)
class WatchConfig:
    interval_s: float = 0.2


SECTIONS = {
    "server": ServerConfig,
    "client": ClientConfig,
    "motion": MotionConfig,
    "watch": WatchConfig,
}


@dataclass(frozen=True)
class Config:
    path: Path | None
    server: ServerConfig = ServerConfig()
    client: ClientConfig = ClientConfig()
    motion: MotionConfig = MotionConfig()
    watch: WatchConfig = WatchConfig()

    def validate(self) -> None:
        sections = {
            name: getattr(self, "return_" if name == "return" else name)
            for name in SECTIONS
        }
        for section, values in sections.items():
            for item in fields(values):
                value = getattr(values, item.name)
                default = item.default
                kind = type(default)
                valid = type(value) is kind
                if kind is float:
                    valid = (
                        not isinstance(value, bool)
                        and isinstance(value, (int, float))
                        and math.isfinite(value)
                    )
                if not valid:
                    raise ValueError(
                        f"{section}.{item.name} has an invalid type or non-finite value"
                    )
        for name, value in (
            ("server", self.server),
            ("client", self.client),
        ):
            if not 1 <= value.port <= 65535:
                raise ValueError(f"{name}.port must be in 1..65535")
        if not isinstance(self.server.host, str) or not self.server.host:
            raise ValueError("server.host must be a non-empty string")
        if not isinstance(self.server.serial_port, str):
            raise ValueError("server.serial_port must be a string")
        if not isinstance(self.server.activate, bool):
            raise ValueError("server.activate must be a boolean")
        if not isinstance(self.client.host, str) or not self.client.host:
            raise ValueError("client.host must be a non-empty string")
        if self.client.timeout_s <= 0:
            raise ValueError("client.timeout_s must be positive")
        for name in ("speed", "force"):
            value = getattr(self.client, name)
            if not isinstance(value, int) or not 0 <= value <= 255:
                raise ValueError(f"client.{name} must be an integer in 0..255")
        for name in ("open_pos", "closed_pos"):
            value = getattr(self.motion, name)
            if not isinstance(value, int) or not 0 <= value <= 255:
                raise ValueError(f"motion.{name} must be an integer in 0..255")
        if self.motion.open_pos == self.motion.closed_pos:
            raise ValueError("motion.open_pos and closed_pos must differ")
        if self.watch.interval_s <= 0:
            raise ValueError("watch.interval_s must be positive")


def load_config(path: str | Path | None = None) -> Config:
    selected = Path(path).resolve() if path is not None else DEFAULT_CONFIG
    if selected is None:
        data: dict[str, Any] = {}
    else:
        with Path(selected).open("rb") as stream:
            data = tomllib.load(stream)
    unknown = data.keys() - SECTIONS.keys()
    if unknown:
        raise ValueError(f"unknown configuration sections: {sorted(unknown)}")
    sections: dict[str, Any] = {}
    for name, cls in SECTIONS.items():
        values = data.get(name, {})
        if not isinstance(values, dict):
            raise ValueError(f"{name} must be a TOML table")
        unknown = values.keys() - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError(f"unknown {name} options: {sorted(unknown)}")
        try:
            sections[name] = cls(**values)
        except TypeError as exc:
            raise ValueError(f"invalid {name} options: {exc}") from exc
    result = Config(
        path=Path(selected) if selected is not None else None,
        **sections,
    )
    # Environment variables keep precedence over the file for the client.
    result = Config(
        path=result.path,
        server=result.server,
        client=ClientConfig(
            host=os.environ.get("GRIPPER_HOST", result.client.host),
            port=int(os.environ.get("GRIPPER_PORT", result.client.port)),
            timeout_s=result.client.timeout_s,
            speed=result.client.speed,
            force=result.client.force,
        ),
        motion=result.motion,
        watch=result.watch,
    )
    result.validate()
    return result
