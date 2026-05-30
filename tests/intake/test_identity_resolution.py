"""Identity resolution coverage for firm/fund name variants during intake."""

from __future__ import annotations

import copy
import json
import sqlite3
from typing import Any

from inv_man_intake.data.repository import CoreRepository
from inv_man_intake.intake.integration import normalize_entity_name, register_intake_bundle
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


def test_normalize_entity_name_strips_common_legal_suffixes() -> None:
    assert normalize_entity_name("  Summit   Arc Advisors, L.L.C. ") == "summit arc advisors"
    assert normalize_entity_name("Summit Arc Special Situations L.P.") == (
        "summit arc special situations"
    )


def test_normalize_entity_name_collapses_unicode_spacing_before_id_minting() -> None:
    assert normalize_entity_name("Summit\u00a0Arc Advisors LLC") == "summit arc advisors"
