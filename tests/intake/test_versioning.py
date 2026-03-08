"""Tests for document fingerprinting and in-memory version store behavior."""

from inv_man_intake.intake.versioning import (
    build_version_id,
    compute_sha256,
    create_fingerprint,
    normalize_received_at,
)
from inv_man_intake.storage.document_store import InMemoryDocumentStore


def test_compute_sha256_is_deterministic() -> None:
    payload = b"alpha-manager-deck"
    digest_1 = compute_sha256(payload)
    digest_2 = compute_sha256(payload)

    assert digest_1 == digest_2
    assert len(digest_1) == 64


def test_build_version_id_uses_hash_prefix_and_timestamp() -> None:
    sha = "a" * 64
    version_id = build_version_id(sha256=sha, received_at="2026-03-01T09:00:00Z")

    assert version_id.startswith("2026-03-01T09:00:00+00:00")
    assert version_id.endswith(":" + "a" * 16)


def test_create_fingerprint_normalizes_received_at() -> None:
    fingerprint = create_fingerprint(content=b"abc", received_at="2026-03-01T09:00:00Z")
    assert fingerprint.received_at == "2026-03-01T09:00:00+00:00"
    assert len(fingerprint.sha256) == 64


def test_normalize_received_at_converts_offsets_and_naive_values_to_utc() -> None:
    assert normalize_received_at("2026-03-01T09:00:00-05:00") == "2026-03-01T14:00:00+00:00"
    assert normalize_received_at("2026-03-01T14:00:00+00:00") == "2026-03-01T14:00:00+00:00"
    assert normalize_received_at("2026-03-01") == "2026-03-01T00:00:00+00:00"


def test_inmemory_store_idempotent_reingest_same_payload_same_timestamp() -> None:
    store = InMemoryDocumentStore()

    first = store.put(
        document_key="fund_1/deck",
        file_name="manager_deck.pdf",
        content=b"same-content",
        received_at="2026-03-01T09:00:00Z",
    )
    second = store.put(
        document_key="fund_1/deck",
        file_name="manager_deck.pdf",
        content=b"same-content",
        received_at="2026-03-01T09:00:00Z",
    )

    assert first.version_id == second.version_id
    assert first.file_hash == second.file_hash
    assert len(store.list_versions("fund_1/deck")) == 1


def test_inmemory_store_appends_new_version_for_changed_content() -> None:
    store = InMemoryDocumentStore()

    first = store.put(
        document_key="fund_1/deck",
        file_name="manager_deck.pdf",
        content=b"content-v1",
        received_at="2026-03-01T09:00:00Z",
    )
    second = store.put(
        document_key="fund_1/deck",
        file_name="manager_deck.pdf",
        content=b"content-v2",
        received_at="2026-03-01T09:00:00Z",
    )

    assert first.version_id != second.version_id
    assert len(store.list_versions("fund_1/deck")) == 2


def test_inmemory_store_idempotent_reingest_same_payload_different_timestamp() -> None:
    store = InMemoryDocumentStore()

    first = store.put(
        document_key="fund_1/deck",
        file_name="manager_deck.pdf",
        content=b"same-content",
        received_at="2026-03-01T09:00:00Z",
    )
    second = store.put(
        document_key="fund_1/deck",
        file_name="manager_deck.pdf",
        content=b"same-content",
        received_at="2026-03-01T10:30:00Z",
    )

    assert first.version_id == second.version_id
    assert len(store.list_versions("fund_1/deck")) == 1


def test_inmemory_store_get_and_exists_round_trip() -> None:
    store = InMemoryDocumentStore()
    created = store.put(
        document_key="fund_1/perf",
        file_name="returns.xlsx",
        content=b"returns-data",
        received_at="2026-03-01T10:00:00Z",
    )

    assert store.exists("fund_1/perf", created.version_id) is True
    assert store.get("fund_1/perf", created.version_id) == b"returns-data"
