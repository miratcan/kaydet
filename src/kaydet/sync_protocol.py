"""Sync protocol message types, shared between client and server."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# -- Change feed --


@dataclass
class SyncChange:
    """A single mutation in the changes feed."""

    id: int
    entry_id: str
    action: str  # 'created', 'updated', 'deleted'
    device_id: Optional[str] = None
    created_at: str = ""


@dataclass
class SyncChangesRequest:
    """Request changes since a given sync token."""

    since: int = 0  # sync_log id to start from


@dataclass
class SyncChangesResponse:
    """Response with changes since the requested token."""

    changes: List[SyncChange] = field(default_factory=list)
    new_token: int = 0
    has_more: bool = False


# -- Entry fetch --


@dataclass
class EntryData:
    """Serialized entry for transport."""

    entry_id: str
    source_file: str
    timestamp: str
    text: str
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    attachments: List[str] = field(default_factory=list)
    encrypted_secret: Optional[str] = None  # Base64 encoded Fernet token
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return asdict(self)



@dataclass
class SyncEntriesRequest:
    """Request full entry data for specific entry IDs."""

    entry_ids: List[str] = field(default_factory=list)


@dataclass
class SyncEntriesResponse:
    """Response with full entry data."""

    entries: List[EntryData] = field(default_factory=list)


# -- Push --


@dataclass
class PushEntriesRequest:
    """Push entries from client to server."""

    entries: List[EntryData] = field(default_factory=list)
    device_id: str = ""


@dataclass
class PushEntriesResponse:
    """Response after pushing entries."""

    accepted: int = 0
    conflicts: int = 0
    errors: List[str] = field(default_factory=list)


# -- Attachments --


@dataclass
class AttachmentGetRequest:
    """Request an attachment by filename."""

    filename: str = ""


@dataclass
class AttachmentGetResponse:
    """Response with attachment data (base64-encoded)."""

    filename: str = ""
    data: str = ""  # base64-encoded
    found: bool = False


@dataclass
class AttachmentPutRequest:
    """Upload an attachment."""

    filename: str = ""
    data: str = ""  # base64-encoded


@dataclass
class AttachmentPutResponse:
    """Response after uploading an attachment."""

    filename: str = ""
    stored: bool = False


# -- Search --


@dataclass
class SearchRequest:
    """Search entries by query string."""

    query: str = ""
    limit: int = 50


@dataclass
class SearchResponse:
    """Search results."""

    entries: List[EntryData] = field(default_factory=list)
    total: int = 0


# -- Delete / Update --


@dataclass
class DeleteEntryRequest:
    """Delete an entry by ID."""

    entry_id: str = ""
    device_id: str = ""


@dataclass
class DeleteEntryResponse:
    """Response after deleting an entry."""

    entry_id: str = ""
    deleted: bool = False
    error: str = ""


@dataclass
class UpdateEntryRequest:
    """Update an existing entry."""

    entry_id: str = ""
    text: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, str]] = None
    device_id: str = ""


@dataclass
class UpdateEntryResponse:
    """Response after updating an entry."""

    entry_id: str = ""
    updated: bool = False
    error: str = ""


# -- Protocol message envelope --


@dataclass
class ProtocolMessage:
    """Wire-format envelope for all sync messages."""

    method: str  # 'changes', 'entries', 'push', 'attachments'
    body: Dict[str, Any] = field(default_factory=dict)


# -- Serialization --

_REQUEST_TYPES = {
    "changes": SyncChangesRequest,
    "entries": SyncEntriesRequest,
    "push": PushEntriesRequest,
    "attachment_get": AttachmentGetRequest,
    "attachment_put": AttachmentPutRequest,
    "delete": DeleteEntryRequest,
    "update": UpdateEntryRequest,
    "search": SearchRequest,
}

_RESPONSE_TYPES = {
    "changes": SyncChangesResponse,
    "entries": SyncEntriesResponse,
    "push": PushEntriesResponse,
    "attachment_get": AttachmentGetResponse,
    "attachment_put": AttachmentPutResponse,
    "delete": DeleteEntryResponse,
    "update": UpdateEntryResponse,
    "search": SearchResponse,
}


def serialize_message(msg: ProtocolMessage) -> str:
    """Serialize a protocol message to JSON."""
    return json.dumps(asdict(msg), separators=(",", ":"))


def deserialize_message(raw: str) -> ProtocolMessage:
    """Deserialize a JSON string into a ProtocolMessage."""
    data = json.loads(raw)
    return ProtocolMessage(
        method=data["method"],
        body=data.get("body", {}),
    )


def parse_request(msg: ProtocolMessage) -> Any:
    """Parse a ProtocolMessage body into the appropriate request type."""
    cls = _REQUEST_TYPES.get(msg.method)
    if cls is None:
        raise ValueError(f"Unknown method: {msg.method}")
    return _from_dict(cls, msg.body)


def parse_response(method: str, body: dict) -> Any:
    """Parse a response body into the appropriate response type."""
    cls = _RESPONSE_TYPES.get(method)
    if cls is None:
        raise ValueError(f"Unknown method: {method}")
    return _from_dict(cls, body)


def make_response_message(method: str, response: Any) -> ProtocolMessage:
    """Wrap a response dataclass into a ProtocolMessage."""
    return ProtocolMessage(method=method, body=asdict(response))


def _from_dict(cls: type, data: dict) -> Any:
    """Construct a dataclass from a dict, handling nested types."""
    if cls == SyncChangesResponse:
        changes = [
            SyncChange(**c) for c in data.get("changes", [])
        ]
        return SyncChangesResponse(
            changes=changes,
            new_token=data.get("new_token", 0),
            has_more=data.get("has_more", False),
        )
    if cls == SyncEntriesResponse:
        entries = [
            EntryData(**e) for e in data.get("entries", [])
        ]
        return SyncEntriesResponse(entries=entries)
    if cls == SearchResponse:
        entries = [
            EntryData(**e) for e in data.get("entries", [])
        ]
        return SearchResponse(
            entries=entries, total=data.get("total", 0)
        )
    if cls == PushEntriesRequest:
        entries = [
            EntryData(**e) for e in data.get("entries", [])
        ]
        return PushEntriesRequest(
            entries=entries,
            device_id=data.get("device_id", ""),
        )
    fields = cls.__dataclass_fields__
    return cls(**{k: v for k, v in data.items() if k in fields})
