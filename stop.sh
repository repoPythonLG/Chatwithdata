#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
CONFIG_PATH="${1:-$ROOT_DIR/cloudera_app_config.json}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" - "$ROOT_DIR" "$CONFIG_PATH" <<'PY'
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any


root = Path(sys.argv[1])
config_path = Path(sys.argv[2])


def load_config() -> dict[str, Any]:
    defaults = {"pid_file": ".data/chatwithdata.pid"}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            defaults.update(loaded)
    return defaults


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_until_stopped(pid: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_running(pid):
            return True
        time.sleep(0.5)
    return not is_running(pid)


def terminate_pid(pid: int, *, process_group: bool = False) -> None:
    if not is_running(pid):
        return
    try:
        if process_group:
            os.killpg(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception as exc:
        print(f"Warning: could not terminate PID {pid}: {exc}", file=sys.stderr)
        return
    if wait_until_stopped(pid):
        return
    try:
        if process_group:
            os.killpg(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except Exception as exc:
        print(f"Warning: could not kill PID {pid}: {exc}", file=sys.stderr)


config = load_config()
pid_file = resolve_path(str(config["pid_file"]))
if not pid_file.exists():
    print("Chat with Data is not running.")
    raise SystemExit(0)

try:
    with pid_file.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    data = {}

supervisor_pid = int(data.get("supervisor_pid") or 0)
backend_pid = int(data.get("backend_pid") or 0)
frontend_pid = int(data.get("frontend_pid") or 0)

if supervisor_pid and is_running(supervisor_pid):
    print(f"Stopping supervisor PID {supervisor_pid}...")
    terminate_pid(supervisor_pid)

for name, pid in (("frontend", frontend_pid), ("backend", backend_pid)):
    if pid and is_running(pid):
        print(f"Stopping {name} process group {pid}...")
        terminate_pid(pid, process_group=True)

pid_file.unlink(missing_ok=True)
print("Chat with Data stopped.")
PY
