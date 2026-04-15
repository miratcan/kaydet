"""Transport abstraction for sync protocol communication."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from abc import ABC, abstractmethod
from configparser import SectionProxy
from pathlib import Path
from typing import Optional

from kaydet_core.sync_protocol import (
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
                    "kaydet_server.sync_server",
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

    def upload_file(
        self, filepath: Path, filename: str
    ) -> dict:
        """Upload a file using the 3-step chunked protocol."""
        import urllib.error
        import urllib.request

        file_size = filepath.stat().st_size
        sha256 = self._compute_sha256(filepath)

        # Step 1: upload-start
        start_body = json.dumps({
            "filename": filename,
            "size": file_size,
            "sha256": sha256,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.server_url}/files/upload-start",
            data=start_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            start_resp = json.loads(resp.read().decode("utf-8"))

        if start_resp.get("already_exists"):
            return {"filename": filename, "already_exists": True}

        upload_id = start_resp["upload_id"]
        chunk_size = start_resp.get("chunk_size", 1048576)
        offset = start_resp.get("existing_offset", 0)

        # Step 2: upload chunks
        with open(filepath, "rb") as f:
            f.seek(offset)
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                chunk_req = urllib.request.Request(
                    f"{self.server_url}/files/upload-chunk",
                    data=chunk,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Authorization": f"Bearer {self.api_key}",
                        "X-Upload-Id": upload_id,
                        "X-Chunk-Offset": str(offset),
                    },
                    method="POST",
                )
                with urllib.request.urlopen(chunk_req) as resp:
                    json.loads(resp.read().decode("utf-8"))

                offset += len(chunk)

        # Step 3: upload-finish
        finish_body = json.dumps({
            "upload_id": upload_id
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.server_url}/files/upload-finish",
            data=finish_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def download_file(
        self, filename: str, dest: Path
    ) -> dict:
        """Download a file and verify SHA-256."""
        import urllib.request

        url = f"{self.server_url}/files/{filename}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req) as resp:
            expected_sha256 = resp.headers.get("X-SHA256", "")

            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            h = hashlib.sha256()

            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)

        actual_sha256 = h.hexdigest()
        if expected_sha256 and actual_sha256 != expected_sha256:
            tmp.unlink(missing_ok=True)
            raise ValueError(
                f"SHA-256 mismatch for {filename}: "
                f"expected {expected_sha256}, "
                f"got {actual_sha256}"
            )

        tmp.rename(dest)
        return {
            "filename": filename,
            "size": dest.stat().st_size,
            "sha256_verified": bool(expected_sha256),
        }

    @staticmethod
    def _compute_sha256(filepath: Path) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()


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
