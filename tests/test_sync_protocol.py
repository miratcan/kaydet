"""Tests for the sync protocol message types."""

from dataclasses import asdict

import pytest

from kaydet.sync_protocol import (
    AttachmentGetRequest,
    AttachmentGetResponse,
    AttachmentPutRequest,
    AttachmentPutResponse,
    EntryData,
    ProtocolMessage,
    PushEntriesRequest,
    PushEntriesResponse,
    SyncChangesRequest,
    SyncChangesResponse,
    SyncEntriesRequest,
    SyncEntriesResponse,
    deserialize_message,
    make_response_message,
    parse_request,
    parse_response,
    serialize_message,
)


class TestSerialization:
    def test_serialize_deserialize_roundtrip(self):
        msg = ProtocolMessage(
            method="changes",
            body={"since": 42},
        )
        raw = serialize_message(msg)
        restored = deserialize_message(raw)
        assert restored.method == "changes"
        assert restored.body["since"] == 42

    def test_serialize_compact_json(self):
        msg = ProtocolMessage(method="test", body={"a": 1})
        raw = serialize_message(msg)
        assert " " not in raw  # compact separators


class TestParseRequest:
    def test_changes_request(self):
        msg = ProtocolMessage(
            method="changes", body={"since": 10}
        )
        req = parse_request(msg)
        assert isinstance(req, SyncChangesRequest)
        assert req.since == 10

    def test_entries_request(self):
        msg = ProtocolMessage(
            method="entries",
            body={"entry_ids": [1, 2, 3]},
        )
        req = parse_request(msg)
        assert isinstance(req, SyncEntriesRequest)
        assert req.entry_ids == [1, 2, 3]

    def test_push_request(self):
        entry = asdict(
            EntryData(
                entry_id=1,
                source_file="2025-01-01.txt",
                timestamp="10:00",
                text="hello",
                tags=["test"],
            )
        )
        msg = ProtocolMessage(
            method="push",
            body={
                "entries": [entry],
                "device_id": "laptop",
            },
        )
        req = parse_request(msg)
        assert isinstance(req, PushEntriesRequest)
        assert len(req.entries) == 1
        assert req.entries[0].text == "hello"
        assert req.device_id == "laptop"

    def test_attachment_get_request(self):
        msg = ProtocolMessage(
            method="attachment_get",
            body={"filename": "42_photo.jpg"},
        )
        req = parse_request(msg)
        assert isinstance(req, AttachmentGetRequest)
        assert req.filename == "42_photo.jpg"

    def test_attachment_put_request(self):
        msg = ProtocolMessage(
            method="attachment_put",
            body={"filename": "42_photo.jpg", "data": "abc"},
        )
        req = parse_request(msg)
        assert isinstance(req, AttachmentPutRequest)
        assert req.filename == "42_photo.jpg"

    def test_unknown_method_raises(self):
        msg = ProtocolMessage(method="invalid", body={})
        with pytest.raises(ValueError, match="Unknown method"):
            parse_request(msg)


class TestParseResponse:
    def test_changes_response(self):
        body = {
            "changes": [
                {
                    "id": 1,
                    "entry_id": 10,
                    "action": "created",
                    "device_id": "a",
                    "created_at": "2025-01-01",
                }
            ],
            "new_token": 1,
            "has_more": False,
        }
        resp = parse_response("changes", body)
        assert isinstance(resp, SyncChangesResponse)
        assert len(resp.changes) == 1
        assert resp.changes[0].action == "created"
        assert resp.new_token == 1

    def test_entries_response(self):
        body = {
            "entries": [
                {
                    "entry_id": 1,
                    "source_file": "2025-01-01.txt",
                    "timestamp": "10:00",
                    "text": "hello",
                }
            ]
        }
        resp = parse_response("entries", body)
        assert isinstance(resp, SyncEntriesResponse)
        assert resp.entries[0].text == "hello"

    def test_push_response(self):
        body = {
            "accepted": 5,
            "conflicts": 1,
            "errors": ["err"],
        }
        resp = parse_response("push", body)
        assert isinstance(resp, PushEntriesResponse)
        assert resp.accepted == 5

    def test_attachment_get_response(self):
        body = {
            "filename": "x.jpg",
            "data": "base64data",
            "found": True,
        }
        resp = parse_response("attachment_get", body)
        assert isinstance(resp, AttachmentGetResponse)
        assert resp.found is True

    def test_attachment_put_response(self):
        body = {"filename": "x.jpg", "stored": True}
        resp = parse_response("attachment_put", body)
        assert isinstance(resp, AttachmentPutResponse)
        assert resp.stored is True


class TestMakeResponse:
    def test_wraps_response(self):
        resp = SyncChangesResponse(
            changes=[], new_token=42, has_more=False
        )
        msg = make_response_message("changes", resp)
        assert msg.method == "changes"
        assert msg.body["new_token"] == 42
