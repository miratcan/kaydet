"""HTTP server for kaydet sync and file transfer."""

from __future__ import annotations

import json as _json
import mimetypes
import sqlite3
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kaydet_core.service import KaydetService
from kaydet_core.sync_protocol import (
    deserialize_message,
    serialize_message,
    validate_attachment_filename,
)

from .sync_server import (
    FileTransferManager,
    SyncServer,
    validate_api_key,
)


def start_http_server(
    conn: sqlite3.Connection,
    storage_dir: Path,
    config,
    config_dir: Path,
    host: str,
    port: int,
) -> None:
    """Start the HTTP sync server."""
    svc = KaydetService(
        config=config, config_dir=config_dir,
        storage_dir=storage_dir, conn=conn,
    )
    server_inst = SyncServer(svc)
    file_mgr = FileTransferManager(storage_dir)

    class SyncHandler(BaseHTTPRequestHandler):
        def _cors_headers(self):
            self.send_header(
                "Access-Control-Allow-Origin", "*"
            )
            self.send_header(
                "Access-Control-Allow-Methods",
                "GET, POST, OPTIONS",
            )
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, Authorization, "
                "X-Upload-Id, X-Chunk-Offset, Range",
            )
            self.send_header(
                "Access-Control-Expose-Headers",
                "X-SHA256, Content-Range",
            )

        def _check_auth(self) -> bool:
            """Validate Bearer token. Sends 401 on failure."""
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                self.send_response(401)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(b"Missing API key")
                return False
            if not validate_api_key(conn, auth[7:]):
                self.send_response(401)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(b"Invalid API key")
                return False
            return True

        def _json_response(self, code: int, obj: dict):
            body = _json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header(
                "Content-Type", "application/json"
            )
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors_headers()
            self.end_headers()

        def do_GET(self):
            if self.path == "/qr":
                self._handle_qr()
                return

            if not self.path.startswith("/files/"):
                self.send_response(404)
                self._cors_headers()
                self.end_headers()
                return

            if not self._check_auth():
                return

            filename = self.path[7:]  # strip "/files/"
            if not validate_attachment_filename(filename):
                self._json_response(
                    400, {"error": "Invalid filename"}
                )
                return

            filepath = file_mgr.get_file_path(filename)
            if not filepath:
                self._json_response(
                    404, {"error": "File not found"}
                )
                return

            file_size = filepath.stat().st_size
            sha256 = file_mgr.compute_sha256(filepath)
            content_type = (
                mimetypes.guess_type(filename)[0]
                or "application/octet-stream"
            )

            range_header = self.headers.get("Range")
            if range_header and range_header.startswith(
                "bytes="
            ):
                range_spec = range_header[6:]
                start_str, _, end_str = (
                    range_spec.partition("-")
                )
                start = int(start_str) if start_str else 0
                end = (
                    int(end_str) if end_str else file_size - 1
                )
                end = min(end, file_size - 1)
                length = end - start + 1

                self.send_response(206)
                self.send_header(
                    "Content-Type", content_type
                )
                self.send_header(
                    "Content-Length", str(length)
                )
                self.send_header(
                    "Content-Range",
                    f"bytes {start}-{end}/{file_size}",
                )
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("X-SHA256", sha256)
                self._cors_headers()
                self.end_headers()

                with open(filepath, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(
                            min(65536, remaining)
                        )
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            else:
                self.send_response(200)
                self.send_header(
                    "Content-Type", content_type
                )
                self.send_header(
                    "Content-Length", str(file_size)
                )
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("X-SHA256", sha256)
                self._cors_headers()
                self.end_headers()

                with open(filepath, "rb") as f:
                    while chunk := f.read(65536):
                        self.wfile.write(chunk)

        def do_POST(self):
            if self.path == "/sync":
                self._handle_sync_post()
            elif self.path == "/files/upload-start":
                self._handle_upload_start()
            elif self.path == "/files/upload-chunk":
                self._handle_upload_chunk()
            elif self.path == "/files/upload-finish":
                self._handle_upload_finish()
            else:
                self.send_response(404)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(b"Not found")

        def _handle_sync_post(self):
            if not self._check_auth():
                return

            length = int(
                self.headers.get("Content-Length", 0)
            )
            body = self.rfile.read(length).decode("utf-8")

            try:
                msg = deserialize_message(body)
                response = server_inst.handle_message(msg)
                resp_json = serialize_message(
                    response
                ).encode("utf-8")

                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/json"
                )
                self._cors_headers()
                self.end_headers()
                self.wfile.write(resp_json)
            except Exception as e:
                self.send_response(500)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))

        def _handle_upload_start(self):
            if not self._check_auth():
                return

            length = int(
                self.headers.get("Content-Length", 0)
            )
            body = _json.loads(
                self.rfile.read(length).decode("utf-8")
            )
            resp = file_mgr.start_upload(
                body.get("filename", ""),
                body.get("size", 0),
                body.get("sha256", ""),
            )
            if (
                resp.upload_id is None
                and not resp.already_exists
            ):
                self._json_response(
                    400, {"error": "Invalid filename"}
                )
                return
            self._json_response(200, asdict(resp))

        def _handle_upload_chunk(self):
            if not self._check_auth():
                return

            upload_id = self.headers.get("X-Upload-Id", "")
            offset_str = self.headers.get(
                "X-Chunk-Offset", ""
            )

            if not upload_id or not offset_str:
                self._json_response(
                    400,
                    {
                        "error": (
                            "Missing X-Upload-Id "
                            "or X-Chunk-Offset"
                        )
                    },
                )
                return

            if upload_id not in file_mgr._uploads:
                self._json_response(
                    404, {"error": "Unknown upload_id"}
                )
                return

            offset = int(offset_str)
            expected = file_mgr.get_expected_offset(
                upload_id
            )
            if offset != expected:
                self._json_response(
                    409,
                    {
                        "error": "Chunk offset mismatch",
                        "expected_offset": expected,
                    },
                )
                return

            length = int(
                self.headers.get("Content-Length", 0)
            )
            data = self.rfile.read(length)

            result = file_mgr.write_chunk(
                upload_id, offset, data
            )
            if result is None:
                self._json_response(
                    500, {"error": "Write failed"}
                )
                return

            received, total = result
            self._json_response(
                200,
                {
                    "received_bytes": received,
                    "total_received": total,
                },
            )

        def _handle_upload_finish(self):
            if not self._check_auth():
                return

            length = int(
                self.headers.get("Content-Length", 0)
            )
            body = _json.loads(
                self.rfile.read(length).decode("utf-8")
            )
            upload_id = body.get("upload_id", "")

            if upload_id not in file_mgr._uploads:
                self._json_response(
                    404, {"error": "Unknown upload_id"}
                )
                return

            resp = file_mgr.finish_upload(upload_id)
            code = 200 if resp.ok else 400
            self._json_response(code, asdict(resp))

        def _handle_qr(self):
            import io
            import qrcode

            # Pick the best API key from DB
            cursor = conn.cursor()
            cursor.execute(
                "SELECT key FROM api_keys LIMIT 1"
            )
            row = cursor.fetchone()
            if not row:
                self._json_response(
                    503, {"error": "No API key configured"}
                )
                return

            api_key = row[0]
            scheme = "http"
            server_host = self.headers.get(
                "Host", f"{host}:{port}"
            )
            server_url = f"{scheme}://{server_host}"
            payload = f"kaydet://{api_key}@{server_host}"

            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(payload)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            png_bytes = buf.getvalue()

            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header(
                "Content-Length", str(len(png_bytes))
            )
            self.send_header(
                "X-Server-Url", server_url
            )
            self._cors_headers()
            self.end_headers()
            self.wfile.write(png_bytes)

        def log_message(self, format, *a):
            print(
                f"[sync] {self.address_string()} "
                f"{format % a}"
            )

    httpd = HTTPServer((host, port), SyncHandler)
    print(f"Sync server listening on {host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
