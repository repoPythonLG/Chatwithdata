#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "cloudera_app_config.json"


def load_config(path: Path) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "public_host": "",
        "frontend_port_env": "CDSW_APP_PORT",
        "frontend_host": "127.0.0.1",
        "frontend_port": 8090,
        "backend_host": "127.0.0.1",
        "backend_port": 8001,
        "node_bin": "",
        "npm_bin": "",
        "vite_hmr": False,
        "log_dir": ".data/logs",
        "pid_file": ".data/chatwithdata.pid",
    }
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError(f"Config file must contain a JSON object: {path}")
        defaults.update(loaded)
    return defaults


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def normalize_host(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        parsed = urlparse(raw)
        return parsed.hostname or ""
    # Cloudera often provides a hostname without a scheme. Strip any path/port.
    return raw.split("/", 1)[0].split(":", 1)[0]


def cloudera_public_host_from_env() -> str:
    public_host = os.getenv("CLOUDERA_PUBLIC_HOST", "").strip()
    if public_host:
        return public_host
    engine_id = os.getenv("CDSW_ENGINE_ID", "").strip()
    domain = os.getenv("CDSW_DOMAIN", "").strip()
    if engine_id and domain:
        return f"{engine_id}.{domain}"
    return ""


def cloudera_allowed_hosts(public_host: str) -> list[str]:
    hosts = {"localhost", "127.0.0.1"}
    normalized_public = normalize_host(public_host)
    if normalized_public:
        hosts.add(normalized_public)
    domain = os.getenv("CDSW_DOMAIN", "").strip()
    if domain:
        hosts.add(domain)
        # Vite accepts a leading dot to allow all subdomains of the domain.
        hosts.add(f".{domain.lstrip('.')}")
    return sorted(hosts)


def configured_frontend_port(config: dict[str, Any]) -> int:
    port_env_name = str(config.get("frontend_port_env") or "CDSW_APP_PORT").strip()
    port_value = os.getenv(port_env_name) if port_env_name else None
    if not port_value and os.getenv("CDSW_READONLY_PORT"):
        port_value = os.getenv("CDSW_READONLY_PORT")
    return int(port_value or config["frontend_port"])


def origin_values(public_host: str, frontend_host: str, frontend_port: int) -> list[str]:
    origins = {
        f"http://{frontend_host}:{frontend_port}",
        f"http://localhost:{frontend_port}",
        f"http://127.0.0.1:{frontend_port}",
    }
    raw_public = (public_host or "").strip()
    host = normalize_host(raw_public)
    if raw_public.startswith(("http://", "https://")):
        parsed = urlparse(raw_public)
        if parsed.scheme and parsed.netloc:
            origins.add(f"{parsed.scheme}://{parsed.netloc}")
    elif host:
        origins.add(f"https://{host}")
        origins.add(f"http://{host}")
    return sorted(origins)


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


def read_pid_file(pid_file: Path) -> dict[str, Any] | None:
    if not pid_file.exists():
        return None
    try:
        with pid_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def ensure_not_running(pid_file: Path) -> None:
    data = read_pid_file(pid_file)
    if not data:
        return
    supervisor_pid = int(data.get("supervisor_pid") or 0)
    if is_running(supervisor_pid):
        raise SystemExit(
            f"Chat with Data is already running under supervisor PID {supervisor_pid}. "
            "Use ./stop.sh first."
        )
    pid_file.unlink(missing_ok=True)


def backend_python() -> str:
    venv_python = ROOT / "backend" / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable


def executable_version(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except Exception:
        return ""


def parse_node_major(version: str) -> int:
    cleaned = version.strip().lstrip("v")
    try:
        return int(cleaned.split(".", 1)[0])
    except Exception:
        return 0


def select_node_bin(config: dict[str, Any]) -> Path:
    candidates = [
        str(config.get("node_bin") or ""),
        os.getenv("NODE_BIN", ""),
        shutil.which("node") or "",
        "/opt/homebrew/bin/node",
        "/usr/local/bin/node",
        "/usr/bin/node",
    ]
    checked: list[str] = []
    for candidate in dict.fromkeys(item for item in candidates if item):
        path = Path(candidate)
        if not path.exists():
            continue
        version = executable_version([str(path), "-v"])
        checked.append(f"{path} ({version or 'unknown version'})")
        if parse_node_major(version) >= 18:
            return path
    detail = ", ".join(checked) if checked else "no node executable found"
    raise RuntimeError(
        "Vite requires Node.js 18 or newer. Configure node_bin in "
        f"{DEFAULT_CONFIG.name} or set NODE_BIN. Checked: {detail}"
    )


def select_npm_bin(config: dict[str, Any], node_bin: Path) -> Path:
    candidates = [
        str(config.get("npm_bin") or ""),
        os.getenv("NPM_BIN", ""),
        str(node_bin.with_name("npm")),
        shutil.which("npm") or "",
        "/opt/homebrew/bin/npm",
        "/usr/local/bin/npm",
        "/usr/bin/npm",
    ]
    for candidate in dict.fromkeys(item for item in candidates if item):
        path = Path(candidate)
        if path.exists():
            return path
    raise RuntimeError("Could not find npm. Configure npm_bin in cloudera_app_config.json.")


def wait_for_url(url: str, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return True
        except Exception:
            time.sleep(1)
    return False


def wait_for_tcp(host: str, port: int, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            time.sleep(1)
    return False


def terminate_process_group(process: subprocess.Popen[Any], name: str) -> None:
    if process.poll() is not None:
        return
    print(f"Stopping {name} PID {process.pid}...", flush=True)
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        print(f"{name} did not stop gracefully; killing it.", flush=True)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Chat with Data for Cloudera.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to JSON config file.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    frontend_host = str(config["frontend_host"])
    frontend_port = configured_frontend_port(config)
    backend_host = str(config["backend_host"])
    backend_port = int(config["backend_port"])
    public_host = str(config.get("public_host") or "").strip() or cloudera_public_host_from_env()
    normalized_public_host = normalize_host(public_host)
    log_dir = resolve_path(config["log_dir"])
    pid_file = resolve_path(config["pid_file"])

    log_dir.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    ensure_not_running(pid_file)

    backend_url = f"http://{backend_host}:{backend_port}"
    frontend_url = f"http://{frontend_host}:{frontend_port}"
    allowed_hosts = cloudera_allowed_hosts(public_host)

    backend_env = os.environ.copy()
    backend_env["CORS_ORIGINS"] = json.dumps(
        origin_values(public_host, frontend_host, frontend_port)
    )
    backend_env.setdefault("ENVIRONMENT", "local")

    node_bin = select_node_bin(config)
    npm_bin = select_npm_bin(config, node_bin)
    node_path_prefix = str(node_bin.parent)

    frontend_env = os.environ.copy()
    frontend_env["PATH"] = f"{node_path_prefix}{os.pathsep}{frontend_env.get('PATH', '')}"
    frontend_env.update(
        {
            "CDSW_APP_POLLING_ENDPOINT": os.getenv("CDSW_APP_POLLING_ENDPOINT", "/healthz"),
            "VITE_API_BASE_URL": "/api",
            "VITE_API_PROXY_TARGET": backend_url,
            "VITE_HOST": frontend_host,
            "VITE_PORT": str(frontend_port),
            "VITE_ALLOWED_HOSTS": ",".join(dict.fromkeys(allowed_hosts)),
            "VITE_HMR": "true" if bool(config.get("vite_hmr")) else "false",
        }
    )
    if normalized_public_host:
        frontend_env["CLOUDERA_PUBLIC_HOST"] = normalized_public_host

    backend_log_path = log_dir / "backend.log"
    frontend_log_path = log_dir / "frontend.log"
    backend_log = backend_log_path.open("ab")
    frontend_log = frontend_log_path.open("ab")

    processes: dict[str, subprocess.Popen[Any]] = {}
    stopped = False

    def shutdown(_signum: int | None = None, _frame: Any | None = None) -> None:
        nonlocal stopped
        if stopped:
            return
        stopped = True
        for name, process in reversed(processes.items()):
            terminate_process_group(process, name)
        pid_file.unlink(missing_ok=True)
        backend_log.close()
        frontend_log.close()

    def handle_signal(signum: int, frame: Any | None) -> None:
        shutdown(signum, frame)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        backend_cmd = [
            backend_python(),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            backend_host,
            "--port",
            str(backend_port),
        ]
        frontend_cmd = [
            str(npm_bin),
            "run",
            "dev",
            "--",
            "--host",
            frontend_host,
            "--port",
            str(frontend_port),
            "--strictPort",
        ]

        print(f"Starting FastAPI on {backend_url}", flush=True)
        print(
            f"Using Node {executable_version([str(node_bin), '-v'])} at {node_bin}",
            flush=True,
        )
        processes["backend"] = subprocess.Popen(
            backend_cmd,
            cwd=ROOT / "backend",
            env=backend_env,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        print(f"Starting Vite on {frontend_url}", flush=True)
        processes["frontend"] = subprocess.Popen(
            frontend_cmd,
            cwd=ROOT / "frontend",
            env=frontend_env,
            stdout=frontend_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        pid_payload = {
            "supervisor_pid": os.getpid(),
            "backend_pid": processes["backend"].pid,
            "frontend_pid": processes["frontend"].pid,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "frontend_url": frontend_url,
            "backend_url": backend_url,
            "public_host": normalized_public_host,
            "config": str(config_path),
            "logs": {
                "backend": str(backend_log_path),
                "frontend": str(frontend_log_path),
            },
        }
        with pid_file.open("w", encoding="utf-8") as handle:
            json.dump(pid_payload, handle, indent=2)

        if not wait_for_tcp(backend_host, backend_port, 60):
            raise RuntimeError(f"FastAPI did not become available. Check {backend_log_path}.")
        if not wait_for_url(frontend_url, 60):
            raise RuntimeError(f"Vite did not become available. Check {frontend_log_path}.")

        print("Chat with Data is running.", flush=True)
        print(f"Frontend: {frontend_url}", flush=True)
        if normalized_public_host:
            print(f"Configured public host: {normalized_public_host}", flush=True)
        print(f"Logs: {log_dir}", flush=True)

        while True:
            for name, process in processes.items():
                exit_code = process.poll()
                if exit_code is not None:
                    raise RuntimeError(f"{name} exited unexpectedly with code {exit_code}.")
            time.sleep(2)
    except Exception as exc:
        print(f"Startup failed: {exc}", file=sys.stderr, flush=True)
        shutdown()
        return 1
    finally:
        shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
