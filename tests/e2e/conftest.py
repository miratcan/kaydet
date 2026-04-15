"""E2E test fixtures: kaydet HTTP server + Expo web dev server."""

from __future__ import annotations

import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Generator

import pytest
import requests

MOBILE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "packages"
    / "mobile"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(url: str, timeout: int = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code < 500:
                return
        except requests.ConnectionError:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"{url} not ready after {timeout}s")


@pytest.fixture(scope="session")
def kaydet_server(tmp_path_factory) -> Generator[dict, None, None]:
    """Start a kaydet HTTP server in a background thread."""
    from kaydet_core.database import (  # noqa: PLC0415
        INDEX_FILENAME,
        get_db_connection,
        initialize_database,
    )
    from configparser import RawConfigParser

    from kaydet_core.utils import DEFAULT_SETTINGS
    from kaydet_server.http_server import start_http_server
    from kaydet_server.sync_server import generate_api_key

    storage = tmp_path_factory.mktemp("storage")
    config_dir = tmp_path_factory.mktemp("config")

    # Write full config with all defaults
    cp = RawConfigParser()
    cp.add_section("SETTINGS")
    for k, v in DEFAULT_SETTINGS.items():
        cp.set("SETTINGS", k, str(v))
    cp.set("SETTINGS", "storage_dir", str(storage))
    cp.set("SETTINGS", "log_dir", str(config_dir))
    cp.set("SETTINGS", "device_prefix", "e2e")
    config_file = config_dir / "config.ini"
    with open(config_file, "w") as f:
        cp.write(f)

    config = cp["SETTINGS"]

    # Init DB and generate API key
    db_path = config_dir / INDEX_FILENAME
    conn = get_db_connection(db_path)
    initialize_database(conn)
    api_key = generate_api_key(conn, "e2e-test")
    conn.close()

    port = _free_port()
    host = "127.0.0.1"

    def _run_server():
        # Create a new connection in the server thread
        server_conn = get_db_connection(db_path)
        start_http_server(
            server_conn, storage, config, config_dir, host, port
        )

    thread = threading.Thread(
        target=_run_server,
        daemon=True,
    )
    thread.start()

    server_url = f"http://{host}:{port}"
    _wait_for(server_url, timeout=10)

    yield {
        "url": server_url,
        "api_key": api_key,
        "port": port,
        "storage": storage,
    }

    # Daemon thread dies with the process


@pytest.fixture(scope="session")
def expo_web(kaydet_server) -> Generator[str, None, None]:
    """Start Expo web dev server."""
    port = _free_port()
    proc = subprocess.Popen(
        ["npx", "expo", "start", "--web", "--port", str(port)],
        cwd=str(MOBILE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    url = f"http://localhost:{port}"
    try:
        _wait_for(url, timeout=60)
    except TimeoutError:
        proc.kill()
        stdout = proc.stdout.read().decode() if proc.stdout else ""
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        raise TimeoutError(
            f"{url} not ready.\nstdout: {stdout}\nstderr: {stderr}"
        )

    yield url

    proc.terminate()
    proc.wait(timeout=5)
