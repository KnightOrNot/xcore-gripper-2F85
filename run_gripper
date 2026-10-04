#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

HOST="${GRIPPER_HOST:-0.0.0.0}"
PORT="${GRIPPER_PORT:-5005}"

python3 gripper_server.py --host "$HOST" --port "$PORT"
