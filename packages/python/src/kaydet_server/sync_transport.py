"""Transport abstraction for sync protocol communication."""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from configparser import SectionProxy
from pathlib import Path
from typing import Optional

from kaydet_core.sync_protocol import (
    ProtocolMessage,
    deserialize_message,
    serialize_message,
)

CHUNK_SIZE = 256 * 1024  # 256 KB — per spec


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
                [sys.executable, "-m", "kaydet_server.sync_server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        return self._process

    def send(self, msg: ProtocolMessage) -> ProtocolMessage:
        import select

        proc = self._ensure_process()
        line = serialize_message(msg) + "\n"
        proc.stdin.write(line)
        proc.stdin.flush()

        ready, _, _ = select.select([proc.stdout], [], [], 60)
        if not ready:
            raise ConnectionError("Timed out waiting for server response")
        response_line = proc.stdout.readline()
        if not response_line:
            raise ConnectionError("Server process closed unexpectedly")
        return deserialize_message(response_line.strip())

    def close(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.stdin.close()
            self._process.wait(timeout=5)
            self._process = None


class HttpTransport(SyncTransport):
    """Transport that communicates with the Rust kaydet-srv over HTTP."""

    def __init__(self, server_url: str, api_key: str) -> None:
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key

    def _headers(self, content_type: str = "application/json") -> dict:
        return {
            "Content-Type": content_type,
            "Authorization": f"Bearer {self.api_key}",
        }

    def _request(self, url: str, data: bytes, headers: dict, method: str = "POST") -> bytes:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ConnectionError("Authentication failed. Check your API key.") from e
            raise ConnectionError(f"Server error (HTTP {e.code}): {e.reason}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Cannot reach server at {self.server_url}: {e.reason}") from e

    def send(self, msg: ProtocolMessage) -> ProtocolMessage:
        """POST /sync — send sync request, receive changes."""
        # Rust server expects the body dict directly (no ProtocolMessage wrapper)
        body = json.dumps(msg.body).encode("utf-8")
        raw = self._request(
            f"{self.server_url}/sync",
            data=body,
            headers=self._headers("application/json"),
        )
        resp_body = json.loads(raw.decode("utf-8"))
        return ProtocolMessage(method=msg.method, body=resp_body)

    def upload_packet(self, entry_id: str, packet_bytes: bytes) -> bool:
        """POST /v1/packets/{entry_id} — upload KYDT packet in chunks.

        Returns True on success. Supports resume via status endpoint.
        """
        total_size = len(packet_bytes)

        # Check for existing partial upload (resume)
        offset = self._get_upload_offset(entry_id)

        pos = offset
        while pos < total_size:
            chunk = packet_bytes[pos:pos + CHUNK_SIZE]
            is_last = (pos + len(chunk)) >= total_size

            headers = {
                **self._headers("application/octet-stream"),
                "X-Kaydet-Chunk-Offset": str(pos),
                "X-Kaydet-Total-Size": str(total_size),
                "X-Kaydet-Chunk-Size": str(len(chunk)),
            }

            raw = self._request(
                f"{self.server_url}/v1/packets/{entry_id}",
                data=chunk,
                headers=headers,
            )

            resp = json.loads(raw.decode("utf-8"))
            if is_last and resp.get("status") == "complete":
                return True

            pos += len(chunk)

        return False

    def download_packet(self, entry_id: str) -> bytes:
        """GET /v1/packets/{entry_id} — download KYDT packet."""
        req = urllib.request.Request(
            f"{self.server_url}/v1/packets/{entry_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise FileNotFoundError(f"Packet not found: {entry_id}") from e
            raise ConnectionError(f"Server error (HTTP {e.code})") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Cannot reach server: {e.reason}") from e

    def _get_upload_offset(self, entry_id: str) -> int:
        """GET /v1/packets/{entry_id}/status — resume offset."""
        req = urllib.request.Request(
            f"{self.server_url}/v1/packets/{entry_id}/status",
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                return data.get("received", 0)
        except Exception:
            return 0


def create_transport(config: SectionProxy) -> SyncTransport:
    """Create the appropriate transport from config."""
    transport_type = config.get("sync_transport", "stdin")

    if transport_type == "http":
        server = config.get("sync_server", "")
        api_key = config.get("sync_api_key", "")
        if not server:
            raise ValueError(
                "sync_server not configured. Run 'kaydet sync setup' first."
            )
        return HttpTransport(server, api_key)

    return StdinTransport(config.get("sync_server_path", "kaydet"))
