"""Document storage adapter interface and local implementations for v1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from inv_man_intake.intake.versioning import build_version_id, create_fingerprint


@dataclass(frozen=True)
class DocumentVersionRecord:
    """Immutable version metadata for one persisted file payload."""

    document_key: str
    file_name: str
    version_id: str
    file_hash: str
    received_at: str
    byte_size: int


class DocumentStore(Protocol):
    """Storage interface for document payloads and version history."""

    def put(
        self,
        document_key: str,
        file_name: str,
        content: bytes,
        received_at: str,
    ) -> DocumentVersionRecord:
        """Store a document payload and return immutable version metadata."""
        ...

    def exists(self, document_key: str, version_id: str) -> bool:
        """Return true if the specified version exists."""
        ...

    def get(self, document_key: str, version_id: str) -> bytes:
        """Return the stored content for a given document version."""
        ...

    def list_versions(self, document_key: str) -> tuple[DocumentVersionRecord, ...]:
        """List all persisted versions for the document key."""
        ...


class InMemoryDocumentStore:
    """In-memory adapter with idempotent re-ingest behavior."""

    def __init__(self) -> None:
        self._content: dict[tuple[str, str], bytes] = {}
        self._versions: dict[str, list[DocumentVersionRecord]] = {}

    def put(
        self,
        document_key: str,
        file_name: str,
        content: bytes,
        received_at: str,
    ) -> DocumentVersionRecord:
        fingerprint = create_fingerprint(content=content, received_at=received_at)
        version_id = build_version_id(
            sha256=fingerprint.sha256, received_at=fingerprint.received_at
        )

        existing_versions = self._versions.setdefault(document_key, [])
        for existing in existing_versions:
            if existing.file_hash == fingerprint.sha256:
                # Idempotent re-ingest: identical payload returns prior record, regardless of timestamp.
                return existing

        record = DocumentVersionRecord(
            document_key=document_key,
            file_name=file_name,
            version_id=version_id,
            file_hash=fingerprint.sha256,
            received_at=fingerprint.received_at,
            byte_size=len(content),
        )
        existing_versions.append(record)
        self._content[(document_key, version_id)] = content
        return record

    def exists(self, document_key: str, version_id: str) -> bool:
        return (document_key, version_id) in self._content

    def get(self, document_key: str, version_id: str) -> bytes:
        try:
            return self._content[(document_key, version_id)]
        except KeyError as exc:
            raise KeyError(
                f"missing version for document_key={document_key}, version_id={version_id}"
            ) from exc

    def list_versions(self, document_key: str) -> tuple[DocumentVersionRecord, ...]:
        return tuple(self._versions.get(document_key, []))


class FilesystemDocumentStore:
    """Filesystem-backed adapter with reloadable version metadata and blobs."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._blob_root = self._root / "blobs"
        self._index_root = self._root / "index"
        self._blob_root.mkdir(parents=True, exist_ok=True)
        self._index_root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        document_key: str,
        file_name: str,
        content: bytes,
        received_at: str,
    ) -> DocumentVersionRecord:
        fingerprint = create_fingerprint(content=content, received_at=received_at)
        version_id = build_version_id(
            sha256=fingerprint.sha256, received_at=fingerprint.received_at
        )

        existing_versions = list(self.list_versions(document_key))
        for existing in existing_versions:
            if existing.file_hash == fingerprint.sha256:
                return existing

        record = DocumentVersionRecord(
            document_key=document_key,
            file_name=file_name,
            version_id=version_id,
            file_hash=fingerprint.sha256,
            received_at=fingerprint.received_at,
            byte_size=len(content),
        )
        self._blob_path(document_key, version_id).write_bytes(content)
        self._write_versions(document_key, (*existing_versions, record))
        return record

    def exists(self, document_key: str, version_id: str) -> bool:
        return self._blob_path(document_key, version_id).is_file()

    def get(self, document_key: str, version_id: str) -> bytes:
        path = self._blob_path(document_key, version_id)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise KeyError(
                f"missing version for document_key={document_key}, version_id={version_id}"
            ) from exc

    def list_versions(self, document_key: str) -> tuple[DocumentVersionRecord, ...]:
        path = self._index_path(document_key)
        if not path.exists():
            return ()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"invalid document store index for document_key={document_key}")
        return tuple(_record_from_json(item) for item in raw)

    def _write_versions(
        self, document_key: str, versions: tuple[DocumentVersionRecord, ...]
    ) -> None:
        path = self._index_path(document_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "document_key": version.document_key,
                "file_name": version.file_name,
                "version_id": version.version_id,
                "file_hash": version.file_hash,
                "received_at": version.received_at,
                "byte_size": version.byte_size,
            }
            for version in versions
        ]
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _blob_path(self, document_key: str, version_id: str) -> Path:
        key_dir = self._blob_root / _path_token(document_key)
        key_dir.mkdir(parents=True, exist_ok=True)
        return key_dir / f"{_path_token(version_id)}.bin"

    def _index_path(self, document_key: str) -> Path:
        return self._index_root / f"{_path_token(document_key)}.json"


def _path_token(value: str) -> str:
    return quote(value, safe="")


def _record_from_json(value: object) -> DocumentVersionRecord:
    if not isinstance(value, dict):
        raise ValueError("document store index entry must be an object")
    required = ("document_key", "file_name", "version_id", "file_hash", "received_at")
    for key in required:
        if not isinstance(value.get(key), str):
            raise ValueError(f"document store index entry has invalid {key}")
    byte_size = value.get("byte_size")
    if not isinstance(byte_size, int):
        raise ValueError("document store index entry has invalid byte_size")
    return DocumentVersionRecord(
        document_key=value["document_key"],
        file_name=value["file_name"],
        version_id=value["version_id"],
        file_hash=value["file_hash"],
        received_at=value["received_at"],
        byte_size=byte_size,
    )
