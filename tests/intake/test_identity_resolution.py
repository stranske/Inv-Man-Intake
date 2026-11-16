"""Identity resolution coverage for firm/fund name variants during intake."""

from __future__ import annotations

import copy
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from inv_man_intake.data.models import Firm, Fund
from inv_man_intake.data.repository import CoreRepository
from inv_man_intake.intake.integration import (
    IntakeRegistrationResult,
    normalize_entity_name,
    register_intake_bundle,
)
from inv_man_intake.intake.service import IngestionService
from inv_man_intake.storage.document_store import InMemoryDocumentStore


def _registry() -> tuple[CoreRepository, InMemoryDocumentStore]:
    repository = CoreRepository(sqlite3.connect(":memory:"))
    repository.ensure_core_schema()
    return repository, InMemoryDocumentStore()


def _bundle(*, package_id: str, firm_name: str, fund_name: str) -> dict[str, Any]:
    return {
        "package_id": package_id,
        "metadata": {
            "firm_name": firm_name,
            "fund_name": fund_name,
            "received_at": "2026-03-04T08:20:00Z",
            "source_channel": "internal_forward",
        },
        "files": [
            {
                "file_name": "summit_arc_investment_update.pdf",
                "role": "investment_deck",
                "source_ref": f"email:{package_id}",
            }
        ],
    }


def test_name_variant_reuses_existing_firm_and_records_aliases() -> None:
    service = IngestionService()
    repository, store = _registry()

    first = register_intake_bundle(
        _bundle(
            package_id="pkg_summit_arc_001",
            firm_name="Summit Arc Advisors",
            fund_name="Summit Arc Special Situations",
        ),
        service,
        core_repository=repository,
        document_store=store,
    )
    second = register_intake_bundle(
        _bundle(
            package_id="pkg_summit_arc_002",
            firm_name="Summit Arc Advisors LLC",
            fund_name="Summit Arc Special Situations LP",
        ),
        service,
        core_repository=repository,
        document_store=store,
    )

    assert first.accepted is True
    assert second.accepted is True
    assert service.get_record("pkg_summit_arc_001").firm_id == "firm_summit_arc_advisors"
    assert service.get_record("pkg_summit_arc_002").firm_id == "firm_summit_arc_advisors"
    assert service.get_record("pkg_summit_arc_002").fund_id == (
        "fund_summit_arc_special_situations"
    )
    assert repository.count_core_rows() == (1, 1, 2)

    firm = repository.get_firm("firm_summit_arc_advisors")
    assert firm is not None
    aliases = json.loads(firm.aliases_json or "[]")
    assert {"name": "Summit Arc Advisors", "normalized": "summit arc advisors"} in aliases
    assert {"name": "Summit Arc Advisors LLC", "normalized": "summit arc advisors"} in aliases

    fund = repository.get_fund("fund_summit_arc_special_situations")
    assert fund is not None
    assert fund.fund_name == "Summit Arc Special Situations"
    fund_aliases = json.loads(fund.aliases_json or "[]")
    assert {
        "name": "Summit Arc Special Situations",
        "normalized": "summit arc special situations",
    } in fund_aliases
    assert {
        "name": "Summit Arc Special Situations LP",
        "normalized": "summit arc special situations",
    } in fund_aliases


def test_distinct_firm_name_mints_fresh_entity() -> None:
    service = IngestionService()
    repository, store = _registry()

    summit = _bundle(
        package_id="pkg_summit_arc_001",
        firm_name="Summit Arc Advisors",
        fund_name="Summit Arc Special Situations",
    )
    crestline = copy.deepcopy(summit)
    crestline["package_id"] = "pkg_crestline_001"
    crestline["metadata"]["firm_name"] = "Crestline Capital"
    crestline["metadata"]["fund_name"] = "Crestline Credit Fund"

    register_intake_bundle(
        summit,
        service,
        core_repository=repository,
        document_store=store,
    )
    register_intake_bundle(
        crestline,
        service,
        core_repository=repository,
        document_store=store,
    )

    assert service.get_record("pkg_summit_arc_001").firm_id == "firm_summit_arc_advisors"
    assert service.get_record("pkg_crestline_001").firm_id == "firm_crestline_capital"
    assert repository.count_core_rows() == (2, 2, 2)


def test_explicit_ids_are_preserved_over_normalized_name_matches() -> None:
    service = IngestionService()
    repository, store = _registry()

    register_intake_bundle(
        _bundle(
            package_id="pkg_summit_arc_001",
            firm_name="Summit Arc Advisors",
            fund_name="Summit Arc Special Situations",
        ),
        service,
        core_repository=repository,
        document_store=store,
    )
    explicit = _bundle(
        package_id="pkg_summit_arc_002",
        firm_name="Summit Arc Advisors LLC",
        fund_name="Summit Arc Special Situations LP",
    )
    explicit["metadata"]["firm_id"] = "firm_custom_summit_arc"
    explicit["metadata"]["fund_id"] = "fund_custom_special_situations"

    result = register_intake_bundle(
        explicit,
        service,
        core_repository=repository,
        document_store=store,
    )

    assert result.accepted is True
    assert service.get_record("pkg_summit_arc_002").firm_id == "firm_custom_summit_arc"
    assert service.get_record("pkg_summit_arc_002").fund_id == "fund_custom_special_situations"
    assert repository.get_firm("firm_custom_summit_arc") is not None
    assert repository.get_fund("fund_custom_special_situations") is not None


def test_same_fund_name_under_two_firms_stays_distinct() -> None:
    service = IngestionService()
    repository, store = _registry()
    alpha = _bundle(
        package_id="pkg_alpha",
        firm_name="Alpha Advisors",
        fund_name="Global Opportunities",
    )
    beta = _bundle(
        package_id="pkg_beta",
        firm_name="Beta Advisors",
        fund_name="Global Opportunities",
    )

    first = register_intake_bundle(alpha, service, repository, store)
    assert first.accepted
    alpha_record = service.get_record("pkg_alpha")
    original = repository.get_fund(alpha_record.fund_id)
    assert original is not None
    assert original.fund_id == "fund_global_opportunities"
    assert original.firm_id == "firm_alpha_advisors"

    second = register_intake_bundle(beta, service, repository, store)
    assert second.accepted
    beta_record = service.get_record("pkg_beta")
    assert alpha_record.fund_id != beta_record.fund_id
    assert beta_record.fund_id == "fund_global_opportunities__firm_beta_advisors"
    assert repository.get_fund(original.fund_id) == original
    assert repository.count_core_rows() == (2, 2, 2)

    for record, expected_firm in (
        (alpha_record, "firm_alpha_advisors"),
        (beta_record, "firm_beta_advisors"),
    ):
        document = repository.get_document(record.document_ids[0])
        assert document is not None
        assert document.fund_id == record.fund_id
        document_fund = repository.get_fund(document.fund_id)
        assert document_fund is not None
        assert document_fund.firm_id == record.firm_id == expected_firm

    beta_alias = _bundle(
        package_id="pkg_beta_alias",
        firm_name="Beta Advisors LLC",
        fund_name="Global Opportunities LP",
    )
    assert register_intake_bundle(beta_alias, service, repository, store).accepted
    assert service.get_record("pkg_beta_alias").fund_id == beta_record.fund_id
    assert repository.count_core_rows() == (2, 2, 3)


def test_explicit_fund_id_reused_across_firms_is_rejected() -> None:
    service = IngestionService()
    connection = sqlite3.connect(":memory:")
    repository = CoreRepository(connection)
    store = InMemoryDocumentStore()
    alpha = _bundle(
        package_id="pkg_alpha",
        firm_name="Alpha Advisors",
        fund_name="Global Opportunities",
    )
    first = register_intake_bundle(alpha, service, repository, store)
    assert first.accepted
    (original_version,) = first.persisted_documents
    original_rows = tuple(connection.iterdump())

    beta = _bundle(
        package_id="pkg_beta",
        firm_name="Beta Advisors",
        fund_name="Global Opportunities",
    )
    beta["metadata"]["fund_id"] = "fund_global_opportunities"
    beta["files"][0]["document_id"] = "doc_beta"
    result = register_intake_bundle(beta, service, repository, store)

    assert not result.accepted
    (error,) = result.errors
    assert error.code == "identity_resolution_error"
    assert error.path == "metadata"
    assert error.message == (
        "fund_id='fund_global_opportunities' belongs to firm_id='firm_alpha_advisors', "
        "not firm_id='firm_beta_advisors'"
    )
    assert result.persisted_documents == ()
    with pytest.raises(KeyError, match="unknown package_id=pkg_beta"):
        service.get_record("pkg_beta")
    assert tuple(connection.iterdump()) == original_rows
    assert store.list_versions(original_version.document_key) == (original_version,)
    assert store.list_versions("fund_global_opportunities/doc_beta") == ()


def test_normalize_entity_name_strips_common_legal_suffixes() -> None:
    assert normalize_entity_name("  Summit   Arc Advisors, L.L.C. ") == "summit arc advisors"
    assert normalize_entity_name("Summit Arc Special Situations L.P.") == (
        "summit arc special situations"
    )


def test_normalize_entity_name_collapses_unicode_spacing_before_id_minting() -> None:
    assert normalize_entity_name("Summit\u00a0Arc Advisors LLC") == "summit arc advisors"


def test_race_overlapping_automatic_registrations_keep_distinct_ownership(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "identity_race.sqlite"
    barrier = threading.Barrier(2)
    results: list[IntakeRegistrationResult] = []
    errors: list[BaseException] = []

    def _register(
        *,
        package_id: str,
        firm_name: str,
        document_id: str,
    ) -> None:
        connection = sqlite3.connect(db_path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout = 30000")
        repository = CoreRepository(connection)
        repository.ensure_core_schema()
        bundle = _bundle(
            package_id=package_id,
            firm_name=firm_name,
            fund_name="Global Opportunities",
        )
        bundle["files"][0]["document_id"] = document_id
        try:
            barrier.wait(timeout=30.0)
            results.append(
                register_intake_bundle(
                    bundle,
                    IngestionService(),
                    core_repository=repository,
                    document_store=InMemoryDocumentStore(),
                )
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            connection.close()

    alpha = threading.Thread(
        target=_register,
        kwargs={
            "package_id": "pkg_alpha",
            "firm_name": "Alpha Advisors",
            "document_id": "doc_alpha",
        },
    )
    beta = threading.Thread(
        target=_register,
        kwargs={
            "package_id": "pkg_beta",
            "firm_name": "Beta Advisors",
            "document_id": "doc_beta",
        },
    )
    alpha.start()
    beta.start()
    alpha.join(timeout=30.0)
    beta.join(timeout=30.0)

    assert not errors
    assert len(results) == 2
    assert all(result.accepted for result in results)
    inspect_connection = sqlite3.connect(db_path)
    inspect_repository = CoreRepository(inspect_connection)
    inspect_repository.ensure_core_schema()
    legacy_fund = inspect_repository.get_fund("fund_global_opportunities")
    scoped_fund = None
    for candidate_id in (
        "fund_global_opportunities__firm_beta_advisors",
        "fund_global_opportunities__firm_alpha_advisors",
    ):
        scoped_fund = inspect_repository.get_fund(candidate_id)
        if scoped_fund is not None:
            break
    assert legacy_fund is not None
    assert scoped_fund is not None
    assert {legacy_fund.firm_id, scoped_fund.firm_id} == {
        "firm_alpha_advisors",
        "firm_beta_advisors",
    }
    assert inspect_repository.count_core_rows() == (2, 2, 2)

    for result in results:
        (document_version,) = result.persisted_documents
        _, document_id = document_version.document_key.split("/", 1)
        document = inspect_repository.get_document(document_id)
        assert document is not None
        fund = inspect_repository.get_fund(document.fund_id)
        assert fund is not None
        if document_id == "doc_alpha":
            assert fund.firm_id == "firm_alpha_advisors"
        else:
            assert fund.firm_id == "firm_beta_advisors"

    inspect_connection.close()


def test_race_explicit_cross_firm_fund_id_rejected_without_writes(tmp_path: Path) -> None:
    db_path = tmp_path / "identity_explicit_race.sqlite"
    seed_connection = sqlite3.connect(db_path)
    seed_repository = CoreRepository(seed_connection)
    seed_repository.ensure_core_schema()
    seed_repository.create_firm(
        Firm(
            firm_id="firm_alpha_advisors",
            legal_name="Alpha Advisors",
            aliases_json=json.dumps(
                [{"name": "Alpha Advisors", "normalized": "alpha advisors"}],
                sort_keys=True,
            ),
            created_at="2026-03-04T08:20:00Z",
        )
    )
    seed_repository.create_fund(
        Fund(
            fund_id="fund_global_opportunities",
            firm_id="firm_alpha_advisors",
            fund_name="Global Opportunities",
            strategy=None,
            asset_class=None,
            created_at="2026-03-04T08:20:00Z",
            aliases_json=json.dumps(
                [{"name": "Global Opportunities", "normalized": "global opportunities"}],
                sort_keys=True,
            ),
        )
    )
    seed_connection.close()

    barrier = threading.Barrier(2)
    results: list[IntakeRegistrationResult] = []
    errors: list[BaseException] = []

    def _register_alpha() -> None:
        connection = sqlite3.connect(db_path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout = 30000")
        repository = CoreRepository(connection)
        repository.ensure_core_schema()
        bundle = _bundle(
            package_id="pkg_alpha",
            firm_name="Alpha Advisors",
            fund_name="Global Opportunities",
        )
        bundle["files"][0]["document_id"] = "doc_alpha"
        try:
            barrier.wait(timeout=30.0)
            results.append(
                register_intake_bundle(
                    bundle,
                    IngestionService(),
                    core_repository=repository,
                    document_store=InMemoryDocumentStore(),
                )
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            connection.close()

    def _register_beta_explicit() -> None:
        connection = sqlite3.connect(db_path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout = 30000")
        repository = CoreRepository(connection)
        repository.ensure_core_schema()
        bundle = _bundle(
            package_id="pkg_beta",
            firm_name="Beta Advisors",
            fund_name="Global Opportunities",
        )
        bundle["metadata"]["fund_id"] = "fund_global_opportunities"
        bundle["files"][0]["document_id"] = "doc_beta"
        try:
            barrier.wait(timeout=30.0)
            results.append(
                register_intake_bundle(
                    bundle,
                    IngestionService(),
                    core_repository=repository,
                    document_store=InMemoryDocumentStore(),
                )
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            connection.close()

    alpha = threading.Thread(target=_register_alpha)
    beta = threading.Thread(target=_register_beta_explicit)
    alpha.start()
    beta.start()
    alpha.join(timeout=30.0)
    beta.join(timeout=30.0)

    assert not errors
    assert len(results) == 2

    accepted = tuple(result for result in results if result.accepted)
    rejected = tuple(result for result in results if not result.accepted)
    assert len(accepted) == 1
    assert len(rejected) == 1
    (failure,) = rejected
    (error,) = failure.errors
    assert error.code == "identity_resolution_error"
    assert failure.persisted_documents == ()
    assert failure.package_id == "pkg_beta"

    inspect_connection = sqlite3.connect(db_path)
    inspect_repository = CoreRepository(inspect_connection)
    assert inspect_repository.count_core_rows() == (1, 1, 1)
    alpha_fund = inspect_repository.get_fund("fund_global_opportunities")
    assert alpha_fund is not None
    assert alpha_fund.firm_id == "firm_alpha_advisors"
    assert inspect_repository.get_document("doc_alpha") is not None
    assert inspect_repository.get_document("doc_beta") is None
    inspect_connection.close()


def test_duplicate_package_id_leaves_no_additional_firm_fund_rows() -> None:
    service = IngestionService()
    repository, store = _registry()
    bundle = _bundle(
        package_id="pkg_summit_arc_dup",
        firm_name="Summit Arc Advisors",
        fund_name="Summit Arc Special Situations",
    )

    first = register_intake_bundle(
        bundle, service, core_repository=repository, document_store=store
    )
    rows_after_first = repository.count_core_rows()

    second = register_intake_bundle(
        bundle, service, core_repository=repository, document_store=store
    )

    assert first.accepted is True
    assert second.accepted is False
    assert second.errors[0].code == "duplicate_package_id"
    assert repository.count_core_rows() == rows_after_first


def test_occupied_scoped_fallback_cannot_capture_unrelated_fund() -> None:
    service = IngestionService()
    repository, store = _registry()
    alpha = _bundle(
        package_id="pkg_alpha", firm_name="Alpha Advisors", fund_name="Global Opportunities"
    )
    assert register_intake_bundle(alpha, service, repository, store).accepted

    beta_income = _bundle(
        package_id="pkg_beta_income", firm_name="Beta Advisors", fund_name="Income"
    )
    scoped_id = "fund_global_opportunities__firm_beta_advisors"
    beta_income["metadata"]["fund_id"] = scoped_id
    assert register_intake_bundle(beta_income, service, repository, store).accepted
    original = repository.get_fund(scoped_id)

    beta_global = _bundle(
        package_id="pkg_beta_global", firm_name="Beta Advisors", fund_name="Global Opportunities"
    )
    result = register_intake_bundle(beta_global, service, repository, store)

    assert not result.accepted
    assert result.errors[0].code == "identity_resolution_error"
    assert repository.get_fund(scoped_id) == original
    assert repository.count_core_rows() == (2, 2, 2)
    with pytest.raises(KeyError, match="unknown package_id=pkg_beta_global"):
        service.get_record("pkg_beta_global")
