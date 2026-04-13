"""Transport abstraction for sync protocol communication."""

from __future__ import annotations

import subprocess
import sys
from abc import ABC, abstractmethod
from configparser import SectionProxy
from typing import Optional

from .sync_protocol import (
    ProtocolMessage,
    deserialize_message,
    serialize_message,
)


class SyncTransport(ABC):
    """Abstract transport for sending sync messages."""

    @abstractmethod
    def send(self, msg: ProtocolMessage) -> ProtocolMessage:
        """Send a message and return the response."""

    def close(self) -> None:  # noqa: B027
        """Clean up transport resources."""


class StdinTransport(SyncTransport):
    """Transport that spawns a server process, communicates via pipes."""

    def __init__(self, server_path: str) -> None:
        self.server_path = server_path
        self._process: Optional[subprocess.Popen] = None

    def _ensure_process(self) -> subprocess.Popen:
        if self._process is None or self._process.poll() is not None:
            self._process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "kaydet.sync_server",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        return self._process

    def send(self, msg: ProtocolMessage) -> ProtocolMessage:
        proc = self._ensure_process()
        line = serialize_message(msg) + "\n"
        proc.stdin.write(line)
        proc.stdin.flush()

        response_line = proc.stdout.readline()
        if not response_line:
            raise ConnectionError(
                "Server process closed unexpectedly"
            )
        return deserialize_message(response_line.strip())

    def close(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.stdin.close()
            self._process.wait(timeout=5)
            self._process = None


class HttpTransport(SyncTransport):
    """Transport that communicates with a remote HTTP server."""

    def __init__(
        self, server_url: str, api_key: str
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key

    def send(self, msg: ProtocolMessage) -> ProtocolMessage:
        import urllib.error
        import urllib.request

        url = f"{self.server_url}/sync"
        data = serialize_message(msg).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                body = resp.read().decode("utf-8")
                return deserialize_message(body)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ConnectionError(
                    "Authentication failed. "
                    "Check your API key."
                ) from e
            raise ConnectionError(
                f"Server error (HTTP {e.code}): "
                f"{e.reason}"
            ) from e
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot reach server at "
                f"{self.server_url}: {e.reason}"
            ) from e


def create_transport(config: SectionProxy) -> SyncTransport:
    """Create the appropriate transport from config."""
    transport_type = config.get("sync_transport", "stdin")

    if transport_type == "http":
        server = config.get("sync_server", "")
        api_key = config.get("sync_api_key", "")
        if not server:
            raise ValueError(
                "sync_server not configured. "
                "Run 'kaydet sync setup' first."
            )
        return HttpTransport(server, api_key)

    # Default: stdin transport
    server_path = config.get(
        "sync_server_path", "kaydet"
    )
    return StdinTransport(server_path)
