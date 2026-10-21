from __future__ import annotations

from pathlib import Path

import pytest

from xcore_gripper_2f85.cli import build_parser
from xcore_gripper_2f85.configuration import load_config
from xcore_gripper_2f85.gripper_server import parse_args


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "default.toml"
    path.write_text(text)
    return path


def test_defaults_match_previous_values() -> None:
    config = load_config()
    assert config.server.port == 5005
    assert config.client.host == "192.168.2.225"
    assert config.client.speed == 255
    assert config.motion.closed_pos == 255


def test_file_overrides_client_and_server(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        """
[server]
host = "127.0.0.1"
port = 5006
activate = false

[client]
host = "10.0.0.5"
speed = 100
""",
    )
    config = load_config(path)
    assert config.server.port == 5006
    assert config.server.activate is False
    assert config.client.speed == 100
    args = build_parser(config).parse_args(["move", "--pos", "1"])
    assert args.host is None
    server = parse_args(["--config", str(path)])
    assert server.port == 5006
    assert server.no_activate is True


def test_environment_wins_for_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRIPPER_HOST", "10.9.9.9")
    monkeypatch.setenv("GRIPPER_PORT", "6005")
    config = load_config(write(tmp_path, '[client]\nhost = "10.0.0.5"\n'))
    assert config.client.host == "10.9.9.9"
    assert config.client.port == 6005


def test_unknown_and_invalid_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown configuration sections"):
        load_config(write(tmp_path, "[nope]\nx = 1\n"))
    with pytest.raises(ValueError, match="unknown client options"):
        load_config(write(tmp_path, "[client]\nnope = 1\n"))
    with pytest.raises(ValueError, match="must differ"):
        load_config(write(tmp_path, "[motion]\nopen_pos = 10\nclosed_pos = 10\n"))


@pytest.mark.parametrize(
    "text",
    [
        "[server]\nport = true\n",
        "[client]\ntimeout_s = nan\n",
        "[watch]\ninterval_s = inf\n",
    ],
)
def test_invalid_types_and_nonfinite_values(tmp_path, text):
    with pytest.raises(ValueError):
        load_config(write(tmp_path, text))
