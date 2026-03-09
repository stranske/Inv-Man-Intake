"""Ingestion lifecycle orchestration and deterministic status transitions."""

from __future__ import annotations

from inv_man_intake.intake.models import (
    EscalationPayload,
    IngestEvent,
    IngestRecord,
    IngestStatus,
    IntakeFile,
)

_ALLOWED_TRANSITIONS: dict[IngestStatus | None, set[IngestStatus]] = {
    None: {"received"},
    "received": {"processing", "escalated"},
    "processing": {"completed", "escalated"},
    "completed": set(),
    "escalated": set(),
}


class IngestionService:
    """In-memory lifecycle manager for intake package processing."""

    def __init__(self) -> None:
        self._records: dict[str, IngestRecord] = {}
        self._events: dict[str, list[IngestEvent]] = {}
        self._document_to_package: dict[str, str] = {}

    def receive_package(
        self,
        package_id: str,
        firm_id: str,
        fund_id: str,
        files: list[IntakeFile],
        at: str,
    ) -> IngestRecord:
        if package_id in self._records:
            raise ValueError(f"package_id={package_id} already exists")
        document_ids = self._resolve_document_ids(package_id=package_id, files=files)
        for document_id in document_ids:
            owner = self._document_to_package.get(document_id)
            if owner is not None:
                raise ValueError(
                    f"document_id={document_id} already exists on package_id={owner}"
                )

        record = IngestRecord(
            package_id=package_id,
            firm_id=firm_id,
            fund_id=fund_id,
            status="received",
            file_count=len(files),
            document_ids=tuple(document_ids),
            created_at=at,
            updated_at=at,
        )
        self._records[package_id] = record
        for document_id in document_ids:
            self._document_to_package[document_id] = package_id
        self._events[package_id] = [
            IngestEvent(
                package_id=package_id,
                from_status=None,
                to_status="received",
                at=at,
                note="package accepted",
            )
        ]
        return record

    def mark_processing(self, package_id: str, at: str) -> IngestRecord:
        return self._transition(package_id=package_id, to_status="processing", at=at, note=None)

    def mark_completed(self, package_id: str, at: str, note: str | None = None) -> IngestRecord:
        return self._transition(package_id=package_id, to_status="completed", at=at, note=note)

    def escalate(
        self,
        package_id: str,
        reason: str,
        at: str,
        retry_attempted: bool,
        fallback_tool: str | None = None,
    ) -> EscalationPayload:
        transitioned = self._transition(
            package_id=package_id,
            to_status="escalated",
            at=at,
            note=reason,
        )
        return EscalationPayload(
            package_id=transitioned.package_id,
            firm_id=transitioned.firm_id,
            fund_id=transitioned.fund_id,
            status=transitioned.status,
            reason=reason,
            retry_attempted=retry_attempted,
            fallback_tool=fallback_tool,
            file_count=transitioned.file_count,
            document_ids=transitioned.document_ids,
            event_at=at,
        )

    def get_record(self, package_id: str) -> IngestRecord:
        try:
            return self._records[package_id]
        except KeyError as exc:
            raise KeyError(f"unknown package_id={package_id}") from exc

    def get_events(self, package_id: str) -> tuple[IngestEvent, ...]:
        try:
            return tuple(self._events[package_id])
        except KeyError as exc:
            raise KeyError(f"unknown package_id={package_id}") from exc

    def get_record_by_document(self, document_id: str) -> IngestRecord:
        package_id = self._package_for_document(document_id)
        return self.get_record(package_id)

    def get_events_by_document(self, document_id: str) -> tuple[IngestEvent, ...]:
        package_id = self._package_for_document(document_id)
        return self.get_events(package_id)

    def _transition(
        self,
        package_id: str,
        to_status: IngestStatus,
        at: str,
        note: str | None,
    ) -> IngestRecord:
        current = self.get_record(package_id)
        allowed = _ALLOWED_TRANSITIONS.get(current.status, set())
        if to_status not in allowed:
            raise ValueError(f"invalid transition: {current.status} -> {to_status}")

        updated = IngestRecord(
            package_id=current.package_id,
            firm_id=current.firm_id,
            fund_id=current.fund_id,
            status=to_status,
            file_count=current.file_count,
            document_ids=current.document_ids,
            created_at=current.created_at,
            updated_at=at,
            note=note,
        )
        self._records[package_id] = updated
        self._events[package_id].append(
            IngestEvent(
                package_id=package_id,
                from_status=current.status,
                to_status=to_status,
                at=at,
                note=note,
            )
        )
        return updated

    def _package_for_document(self, document_id: str) -> str:
        try:
            return self._document_to_package[document_id]
        except KeyError as exc:
            raise KeyError(f"unknown document_id={document_id}") from exc

    @staticmethod
    def _resolve_document_ids(*, package_id: str, files: list[IntakeFile]) -> list[str]:
        seen: set[str] = set()
        resolved: list[str] = []
        for index, file_entry in enumerate(files):
            candidate = file_entry.document_id or f"{package_id}:doc:{index}"
            if candidate in seen:
                raise ValueError(f"duplicate document_id={candidate} in package_id={package_id}")
            seen.add(candidate)
            resolved.append(candidate)
        return resolved
