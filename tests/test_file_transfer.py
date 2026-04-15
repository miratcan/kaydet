"""Tests for the file transfer protocol (chunked upload, download, SHA-256)."""

from __future__ import annotations

import hashlib
import time

import pytest

from kaydet_core.sync_protocol import validate_attachment_filename
from kaydet_server.sync_server import FileTransferManager

# -- validate_attachment_filename --


class TestValidateAttachmentFilename:
    def test_valid_simple(self):
        assert validate_attachment_filename("d1_photo.jpg")

    def test_valid_with_dashes(self):
        assert validate_attachment_filename("d5_my-receipt.pdf")

    def test_valid_with_dots(self):
        assert validate_attachment_filename("abc_file.tar.gz")

    def test_rejects_path_traversal(self):
        assert not validate_attachment_filename("../etc/passwd")

    def test_rejects_slash(self):
        assert not validate_attachment_filename("dir/file.jpg")

    def test_rejects_backslash(self):
        assert not validate_attachment_filename("dir\\file.jpg")

    def test_rejects_no_underscore(self):
        assert not validate_attachment_filename("photo.jpg")

    def test_rejects_empty(self):
        assert not validate_attachment_filename("")

    def test_rejects_spaces(self):
        assert not validate_attachment_filename("d1_my photo.jpg")


# -- FileTransferManager --


@pytest.fixture
def storage(tmp_path):
    """Create a storage directory with attachments subdir."""
    att_dir = tmp_path / "attachments"
    att_dir.mkdir()
    return tmp_path


@pytest.fixture
def mgr(storage):
    return FileTransferManager(storage)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestFileTransferManager:
    def test_start_upload_creates_state(self, mgr):
        resp = mgr.start_upload("d1_photo.jpg", 1024, "abc123")
        assert resp.upload_id is not None
        assert resp.chunk_size == 1048576
        assert resp.existing_offset == 0
        assert not resp.already_exists

    def test_start_upload_invalid_filename(self, mgr):
        resp = mgr.start_upload("../hack.txt", 100, "abc")
        assert resp.upload_id is None
        assert not resp.already_exists

    def test_start_upload_already_exists(self, mgr, storage):
        data = b"hello world"
        target = storage / "attachments" / "d1_photo.jpg"
        target.write_bytes(data)

        resp = mgr.start_upload(
            "d1_photo.jpg", len(data), _sha256(data)
        )
        assert resp.already_exists

    def test_start_upload_already_exists_hash_mismatch(
        self, mgr, storage
    ):
        target = storage / "attachments" / "d1_photo.jpg"
        target.write_bytes(b"hello")

        resp = mgr.start_upload(
            "d1_photo.jpg", 5, "wrong_hash"
        )
        assert not resp.already_exists
        assert resp.upload_id is not None

    def test_full_upload_happy_path(self, mgr, storage):
        data = b"x" * 100
        sha = _sha256(data)

        start = mgr.start_upload("d1_file.bin", len(data), sha)
        assert start.upload_id

        result = mgr.write_chunk(start.upload_id, 0, data)
        assert result == (100, 100)

        finish = mgr.finish_upload(start.upload_id)
        assert finish.ok
        assert finish.sha256_match
        assert finish.filename == "d1_file.bin"
        assert finish.size == 100

        # File should be in attachments
        assert (storage / "attachments" / "d1_file.bin").exists()
        # Upload state should be cleaned up
        assert start.upload_id not in mgr._uploads

    def test_chunked_upload(self, mgr, storage):
        chunk1 = b"a" * 50
        chunk2 = b"b" * 50
        full = chunk1 + chunk2
        sha = _sha256(full)

        start = mgr.start_upload("d1_data.bin", 100, sha)
        mgr.write_chunk(start.upload_id, 0, chunk1)
        mgr.write_chunk(start.upload_id, 50, chunk2)

        finish = mgr.finish_upload(start.upload_id)
        assert finish.ok

        stored = (storage / "attachments" / "d1_data.bin").read_bytes()
        assert stored == full

    def test_chunk_offset_mismatch(self, mgr):
        start = mgr.start_upload("d1_test.bin", 100, "sha")
        result = mgr.write_chunk(start.upload_id, 10, b"data")
        assert result is None  # rejected

    def test_sha256_mismatch_on_finish(self, mgr, storage):
        data = b"hello"
        start = mgr.start_upload(
            "d1_bad.bin", len(data), "wrong_sha256"
        )
        mgr.write_chunk(start.upload_id, 0, data)
        finish = mgr.finish_upload(start.upload_id)

        assert not finish.ok
        assert not finish.sha256_match
        assert "mismatch" in finish.error.lower()
        # Part file should be cleaned up
        assert not (
            storage / "uploads" / f"{start.upload_id}.part"
        ).exists()

    def test_resume_upload(self, mgr, storage):
        chunk1 = b"first_half"
        full = chunk1 + b"second_half"
        sha = _sha256(full)

        # Start and send first chunk
        start1 = mgr.start_upload("d1_resume.bin", len(full), sha)
        mgr.write_chunk(start1.upload_id, 0, chunk1)

        # "Reconnect" - start again for same filename
        start2 = mgr.start_upload("d1_resume.bin", len(full), sha)
        assert start2.upload_id == start1.upload_id
        assert start2.existing_offset == len(chunk1)

        # Send remaining data
        mgr.write_chunk(
            start2.upload_id, len(chunk1), b"second_half"
        )
        finish = mgr.finish_upload(start2.upload_id)
        assert finish.ok

    def test_finish_unknown_upload(self, mgr):
        resp = mgr.finish_upload("nonexistent")
        assert not resp.ok
        assert "Unknown" in resp.error

    def test_get_file_path(self, mgr, storage):
        target = storage / "attachments" / "d1_test.jpg"
        target.write_bytes(b"img")

        assert mgr.get_file_path("d1_test.jpg") == target
        assert mgr.get_file_path("d1_missing.jpg") is None
        assert mgr.get_file_path("../hack") is None

    def test_compute_sha256(self, mgr, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"test data")
        assert mgr.compute_sha256(f) == _sha256(b"test data")

    def test_cleanup_stale(self, mgr, storage):
        mgr.cleanup_timeout = 0  # expire immediately

        start = mgr.start_upload("d1_stale.bin", 10, "sha")
        mgr.write_chunk(start.upload_id, 0, b"partial")

        # Backdate the state
        mgr._uploads[start.upload_id].created_at = (
            time.time() - 1
        )

        removed = mgr.cleanup_stale()
        assert removed == 1
        assert start.upload_id not in mgr._uploads
        assert not (
            storage / "uploads" / f"{start.upload_id}.part"
        ).exists()

    def test_write_chunk_unknown_upload(self, mgr):
        result = mgr.write_chunk("unknown", 0, b"data")
        assert result is None
