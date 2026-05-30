"""Integration helpers for registering intake bundles from fixture-style payloads."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from inv_man_intake.contracts.intake_contract import IntakeValidationIssue, validate_intake_payload
from inv_man_intake.data.models import Document, Firm, Fund
from inv_man_intake.data.repository import CoreRepository
from inv_man_intake.intake.models import IngestStatus, IntakeFile
from inv_man_intake.intake.service import IngestionService
from inv_man_intake.storage.document_store import (
    DocumentStore,
    DocumentVersionRecord,
    FilesystemDocumentStore,
)


@dataclass(frozen=True)
class IntakeRegistrationResult:
    """Outcome for one intake bundle registration attempt."""

    accepted: bool
    package_id: str | None
    status: IngestStatus | None
    errors: tuple[IntakeValidationIssue, ...]
    warnings: tuple[IntakeValidationIssue, ...]
    persisted_documents: tuple[DocumentVersionRecord, ...] = ()


def register_intake_bundle(
    bundle: dict[str, Any],
    service: IngestionService,
    core_repository: CoreRepository | None = None,
    document_store: DocumentStore | None = None,
    content_resolver: DocumentContentResolver | None = None,
) -> IntakeRegistrationResult:
    """Validate and register one intake bundle with deterministic errors."""

    if not isinstance(bundle, dict):
        return IntakeRegistrationResult(
            accepted=False,
            package_id=None,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="invalid_bundle_structure",
                    path="$",
                    message="bundle root must be an object",
                ),
            ),
            warnings=(),
        )

    validation = validate_intake_payload(bundle)
    package_id = _as_non_empty_str(bundle.get("package_id"))
    if not package_id:
        return IntakeRegistrationResult(
            accepted=False,
            package_id=None,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="missing_package_id",
                    path="package_id",
                    message="package_id is required",
                ),
                *validation.errors,
            ),
            warnings=validation.warnings,
        )

    if not validation.is_valid:
        return IntakeRegistrationResult(
            accepted=False,
            package_id=package_id,
            status=None,
            errors=validation.errors,
            warnings=validation.warnings,
        )

    metadata = bundle["metadata"]
    normalized_firm_name = _normalized_name(_as_non_empty_str(metadata.get("firm_name")))
    normalized_fund_name = _normalized_name(_as_non_empty_str(metadata.get("fund_name")))
    firm_id = _stable_identifier(
        preferred=metadata.get("firm_id"),
        fallback=normalized_firm_name,
        prefix="firm",
    )
    fund_id = _stable_identifier(
        preferred=metadata.get("fund_id"),
        fallback=normalized_fund_name,
        prefix="fund",
    )
    if core_repository is not None and document_store is not None:
        core_repository.ensure_core_schema()
        firm_name = _as_non_empty_str(metadata.get("firm_name")) or firm_id
        try:
            firm_id = _resolve_firm_id(
                core_repository=core_repository,
                explicit_id=_as_non_empty_str(metadata.get("firm_id")),
                fallback_id=firm_id,
                name=firm_name,
            )
            fund_id = _resolve_fund_id(
                core_repository=core_repository,
                explicit_id=_as_non_empty_str(metadata.get("fund_id")),
                fallback_id=fund_id,
                firm_id=firm_id,
                name=_as_non_empty_str(metadata.get("fund_name")) or fund_id,
            )
        except ValueError as exc:
            return IntakeRegistrationResult(
                accepted=False,
                package_id=package_id,
                status=None,
                errors=(
                    IntakeValidationIssue(
                        code="identity_resolution_error",
                        path="metadata",
                        message=str(exc),
                    ),
                ),
                warnings=validation.warnings,
            )

    file_entries = [entry for entry in bundle["files"] if isinstance(entry, dict)]
    files = [
        IntakeFile(
            file_name=_as_non_empty_str(entry.get("file_name")),
            role=_as_non_empty_str(entry.get("role")),
            source_ref=_as_non_empty_str(entry.get("source_ref")) or None,
            document_id=_as_non_empty_str(entry.get("document_id")) or None,
        )
        for entry in file_entries
    ]

    try:
        record = service.receive_package(
            package_id=package_id,
            firm_id=firm_id,
            fund_id=fund_id,
            files=files,
            at=_as_non_empty_str(metadata.get("received_at")),
        )
    except ValueError as exc:
        return IntakeRegistrationResult(
            accepted=False,
            package_id=package_id,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="duplicate_package_id",
                    path="package_id",
                    message=str(exc),
                ),
            ),
            warnings=validation.warnings,
        )

    persisted_documents: tuple[DocumentVersionRecord, ...] = ()
    if core_repository is not None and document_store is not None:
        persisted_documents = _persist_accepted_bundle(
            core_repository=core_repository,
            document_store=document_store,
            content_resolver=content_resolver or deterministic_fixture_content,
            package_id=record.package_id,
            firm_id=record.firm_id,
            fund_id=record.fund_id,
            document_ids=record.document_ids,
            metadata=metadata,
            file_entries=file_entries,
        )

    return IntakeRegistrationResult(
        accepted=True,
        package_id=record.package_id,
        status=record.status,
        errors=(),
        warnings=validation.warnings,
        persisted_documents=persisted_documents,
    )


def register_intake_bundle_file(
    path: Path | str,
    service: IngestionService,
    core_repository: CoreRepository | None = None,
    document_store: DocumentStore | None = None,
    content_resolver: DocumentContentResolver | None = None,
) -> IntakeRegistrationResult:
    """Load, validate, and register an intake bundle from disk."""

    bundle_path = Path(path)
    try:
        raw_text = bundle_path.read_text(encoding="utf-8")
    except OSError as exc:
        return IntakeRegistrationResult(
            accepted=False,
            package_id=None,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="bundle_read_error",
                    path=str(bundle_path),
                    message=_stable_read_error_message(exc),
                ),
            ),
            warnings=(),
        )

    try:
        parsed = json.loads(raw_text)
    except JSONDecodeError as exc:
        return IntakeRegistrationResult(
            accepted=False,
            package_id=None,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="invalid_json_bundle",
                    path=str(bundle_path),
                    message=(f"malformed JSON at line {exc.lineno}, column {exc.colno}"),
                ),
            ),
            warnings=(),
        )

    if not isinstance(parsed, dict):
        return IntakeRegistrationResult(
            accepted=False,
            package_id=None,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="invalid_bundle_structure",
                    path=str(bundle_path),
                    message="bundle root must be an object",
                ),
            ),
            warnings=(),
        )

    return register_intake_bundle(
        parsed,
        service,
        core_repository=core_repository,
        document_store=document_store,
        content_resolver=content_resolver,
    )


def register_intake_bundle_to_path(
    bundle_path: Path | str,
    *,
    db_path: Path | str,
    store_root: Path | str,
    service: IngestionService | None = None,
    content_resolver: DocumentContentResolver | None = None,
) -> IntakeRegistrationResult:
    """Register an intake bundle using on-disk SQLite and filesystem document storage."""

    sqlite_path = Path(db_path)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(sqlite_path)
    try:
        return register_intake_bundle_file(
            bundle_path,
            service or IngestionService(),
            core_repository=CoreRepository(connection),
            document_store=FilesystemDocumentStore(store_root),
            content_resolver=content_resolver,
        )
    finally:
        connection.close()


type DocumentContentResolver = Callable[[dict[str, Any], str], bytes]

_LEGAL_SUFFIX_PATTERN = re.compile(
    r"\b(l\.?\s*l\.?\s*c\.?|l\.?\s*p\.?|ltd\.?|inc\.?)\b\.?$",
    flags=re.IGNORECASE,
)


def deterministic_fixture_content(entry: dict[str, Any], package_id: str) -> bytes:
    """Resolve deterministic bytes for fixture-style intake bundles."""
    file_name = _as_non_empty_str(entry.get("file_name"))
    source_ref = _as_non_empty_str(entry.get("source_ref"))
    return f"{package_id}\n{file_name}\n{source_ref}\n".encode()


def _persist_accepted_bundle(
    *,
    core_repository: CoreRepository,
    document_store: DocumentStore,
    content_resolver: DocumentContentResolver,
    package_id: str,
    firm_id: str,
    fund_id: str,
    document_ids: tuple[str, ...],
    metadata: dict[str, Any],
    file_entries: list[dict[str, Any]],
) -> tuple[DocumentVersionRecord, ...]:
    core_repository.ensure_core_schema()
    received_at = _as_non_empty_str(metadata.get("received_at"))
    source_channel = _as_non_empty_str(metadata.get("source_channel"))
    version_date = _version_date(metadata, received_at)

    firm_name = _as_non_empty_str(metadata.get("firm_name")) or firm_id
    resolved_firm_id = firm_id
    fund_name = _as_non_empty_str(metadata.get("fund_name")) or fund_id
    resolved_fund_id = fund_id

    if core_repository.get_firm(resolved_firm_id) is None:
        core_repository.create_firm(
            Firm(
                firm_id=resolved_firm_id,
                legal_name=firm_name,
                aliases_json=_aliases_json_for_name(firm_name),
                created_at=received_at,
            )
        )
    else:
        _append_firm_alias(core_repository, resolved_firm_id, firm_name)

    fund = Fund(
        fund_id=resolved_fund_id,
        firm_id=resolved_firm_id,
        fund_name=fund_name,
        strategy=_as_non_empty_str(metadata.get("strategy")) or None,
        asset_class=_as_non_empty_str(metadata.get("asset_class")) or None,
        created_at=received_at,
        aliases_json=_aliases_json_for_name(fund_name),
    )
    existing_fund = core_repository.get_fund(resolved_fund_id)
    if existing_fund is None:
        core_repository.create_fund(fund)
    else:
        merged_fund = _merge_fund(existing=existing_fund, incoming=fund)
        if merged_fund != existing_fund:
            core_repository.update_fund(merged_fund)

    version_records: list[DocumentVersionRecord] = []
    for document_id, entry in zip(document_ids, file_entries, strict=True):
        file_name = _as_non_empty_str(entry.get("file_name"))
        document_key = _document_key(fund_id=resolved_fund_id, document_id=document_id)
        content = content_resolver(entry, package_id)
        version = document_store.put(
            document_key=document_key,
            file_name=file_name,
            content=content,
            received_at=received_at,
        )
        document = Document(
            document_id=document_id,
            fund_id=resolved_fund_id,
            file_name=file_name,
            file_hash=version.file_hash,
            received_at=version.received_at,
            version_date=version_date,
            source_channel=source_channel,
            created_at=received_at,
        )
        existing_document = core_repository.get_document(document_id)
        if existing_document is None:
            core_repository.create_document(document)
        else:
            _ensure_document_invariants(existing=existing_document, incoming=document)
            core_repository.update_document(document)
        version_records.append(version)

    return tuple(version_records)


def _as_non_empty_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize_entity_name(name: str) -> str:
    """Normalize a firm or fund name, stripping trailing legal suffix chains."""
    normalized = _normalized_name(name)
    previous = None
    while previous != normalized:
        previous = normalized
        normalized = _LEGAL_SUFFIX_PATTERN.sub("", normalized).strip()
        normalized = normalized.rstrip(",").strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _stable_identifier(preferred: Any, fallback: Any, prefix: str) -> str:
    preferred_value = _as_non_empty_str(preferred)
    if preferred_value:
        return preferred_value

    fallback_value = normalize_entity_name(_as_non_empty_str(fallback))
    slug = re.sub(r"[^a-z0-9]+", "_", fallback_value).strip("_")
    return f"{prefix}_{slug or 'unknown'}"


def _normalized_name(name: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name).casefold()).strip()


def _document_key(*, fund_id: str, document_id: str) -> str:
    return f"{fund_id}/{document_id}"


def _version_date(metadata: dict[str, Any], received_at: str) -> str:
    explicit_version_date = _as_non_empty_str(metadata.get("version_date"))
    if explicit_version_date and _is_iso_date(explicit_version_date):
        return explicit_version_date
    return received_at[:10]


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _resolve_firm_id(
    *,
    core_repository: CoreRepository,
    explicit_id: str,
    fallback_id: str,
    name: str,
) -> str:
    if explicit_id:
        return explicit_id

    normalized = normalize_entity_name(name)
    matches = [
        firm.firm_id for firm in core_repository.list_firms() if _firm_has_alias(firm, normalized)
    ]
    unique_matches = sorted(set(matches))
    if len(unique_matches) > 1:
        raise ValueError(
            f"ambiguous firm identity for normalized_name={normalized!r}: "
            + ", ".join(unique_matches)
        )
    if unique_matches:
        return unique_matches[0]
    return fallback_id


def _resolve_fund_id(
    *,
    core_repository: CoreRepository,
    explicit_id: str,
    fallback_id: str,
    firm_id: str,
    name: str,
) -> str:
    if explicit_id:
        return explicit_id

    normalized = normalize_entity_name(name)
    matches = [
        fund.fund_id
        for fund in core_repository.list_funds(firm_id)
        if _fund_has_alias(fund, normalized)
    ]
    unique_matches = sorted(set(matches))
    if len(unique_matches) > 1:
        raise ValueError(
            f"ambiguous fund identity for firm_id={firm_id!r}, normalized_name={normalized!r}: "
            + ", ".join(unique_matches)
        )
    if unique_matches:
        return unique_matches[0]
    return fallback_id


def _firm_has_alias(firm: Firm, normalized_name: str) -> bool:
    if normalize_entity_name(firm.legal_name) == normalized_name:
        return True
    return any(
        normalize_entity_name(str(alias["name"])) == normalized_name
        for alias in _load_alias_entries(firm.aliases_json)
        if isinstance(alias.get("name"), str)
    )


def _fund_has_alias(fund: Fund, normalized_name: str) -> bool:
    if normalize_entity_name(fund.fund_name) == normalized_name:
        return True
    return any(
        normalize_entity_name(str(alias["name"])) == normalized_name
        for alias in _load_alias_entries(fund.aliases_json)
        if isinstance(alias.get("name"), str)
    )


def _append_firm_alias(
    core_repository: CoreRepository,
    firm_id: str,
    name: str,
) -> None:
    firm = core_repository.get_firm(firm_id)
    if firm is None:
        raise KeyError(f"unknown firm_id={firm_id}")

    updated = _merge_alias_entries(firm.aliases_json, name)
    if updated != firm.aliases_json:
        core_repository.update_firm_aliases(firm_id, updated)


def _aliases_json_for_name(name: str) -> str:
    return _merge_alias_entries(None, name)


def _merge_alias_entries(aliases_json: str | None, name: str) -> str:
    entries = _load_alias_entries(aliases_json)
    normalized = normalize_entity_name(name)
    if not any(entry.get("name") == name for entry in entries):
        entries.append({"name": name, "normalized": normalized})

    entries.sort(key=lambda entry: (str(entry.get("normalized", "")), str(entry.get("name", ""))))
    return json.dumps(entries, sort_keys=True)


def _load_alias_entries(aliases_json: str | None) -> list[dict[str, str]]:
    if aliases_json is None:
        return []
    try:
        parsed = json.loads(aliases_json)
    except JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []

    entries: list[dict[str, str]] = []
    for item in parsed:
        if isinstance(item, str):
            entries.append({"name": item, "normalized": normalize_entity_name(item)})
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            name = str(item["name"])
            normalized = item.get("normalized")
            entries.append(
                {
                    "name": name,
                    "normalized": (
                        str(normalized)
                        if isinstance(normalized, str)
                        else normalize_entity_name(name)
                    ),
                }
            )
    return entries


def _merge_fund(*, existing: Fund, incoming: Fund) -> Fund:
    """Preserve canonical fund identity while recording incoming name variants."""
    return replace(
        existing,
        firm_id=incoming.firm_id or existing.firm_id,
        fund_name=existing.fund_name,
        strategy=incoming.strategy if incoming.strategy is not None else existing.strategy,
        asset_class=(
            incoming.asset_class if incoming.asset_class is not None else existing.asset_class
        ),
        aliases_json=_merge_alias_entries(existing.aliases_json, incoming.fund_name),
    )


def _ensure_document_invariants(*, existing: Document, incoming: Document) -> None:
    """Reject document_id collisions where structural identity has changed."""
    mismatches: list[str] = []
    if existing.fund_id != incoming.fund_id:
        mismatches.append(f"fund_id={existing.fund_id!r}->{incoming.fund_id!r}")
    if existing.file_hash != incoming.file_hash:
        mismatches.append(f"file_hash={existing.file_hash!r}->{incoming.file_hash!r}")
    if mismatches:
        raise ValueError(
            f"document_id={incoming.document_id!r} collision: " + ", ".join(mismatches)
        )


def _stable_read_error_message(exc: OSError) -> str:
    """Normalize OSError text for deterministic malformed-bundle output."""
    if isinstance(exc, FileNotFoundError):
        return "bundle file not found"
    if isinstance(exc, PermissionError):
        return "bundle file is not readable"
    if isinstance(exc, IsADirectoryError):
        return "bundle path must reference a file"
    return "failed to read bundle file"
