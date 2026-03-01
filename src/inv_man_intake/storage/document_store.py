"""Document storage adapter interface and in-memory implementation for v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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

    def exists(self, document_key: str, version_id: str) -> bool:
        """Return true if the specified version exists."""

    def get(self, document_key: str, version_id: str) -> bytes:
        """Return the stored content for a given document version."""

    def list_versions(self, document_key: str) -> tuple[DocumentVersionRecord, ...]:
        """List all persisted versions for the document key."""


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
            if existing.version_id == version_id and existing.file_hash == fingerprint.sha256:
                # Idempotent re-ingest: same payload + timestamp returns prior record.
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
