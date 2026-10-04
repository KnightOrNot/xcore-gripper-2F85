#!/usr/bin/env bash
# Start gripper_server.py on the machine that has the gripper USB/RS485 cable.
#
#   GRIPPER_HOST=0.0.0.0 GRIPPER_PORT=5005 ./run_gripper.sh
#   ./run_gripper.sh --serial-port /dev/ttyUSB0
set -euo pipefail

cd "$(dirname "$0")"

BIND_HOST="${GRIPPER_BIND_HOST:-${GRIPPER_HOST:-0.0.0.0}}"
BIND_PORT="${GRIPPER_BIND_PORT:-${GRIPPER_PORT:-5005}}"
SERIAL_PORT="${GRIPPER_SERIAL_PORT:-}"

args=(--host "$BIND_HOST" --port "$BIND_PORT")
if [[ -n "$SERIAL_PORT" ]]; then
    args+=(--serial-port "$SERIAL_PORT")
fi

# Prefer an installed environment (uv sync / pip install -e .); fall back to the
# source tree so the script also works before installation.
if [[ -x .venv/bin/gripper-server ]]; then
    exec .venv/bin/gripper-server "${args[@]}" "$@"
fi
if command -v gripper-server >/dev/null 2>&1; then
    exec gripper-server "${args[@]}" "$@"
fi

exec env PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m gripper_2f85.gripper_server "${args[@]}" "$@"
