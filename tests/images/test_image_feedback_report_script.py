from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from inv_man_intake.contracts.image_feedback_contract import ImageFeedbackRecord
from inv_man_intake.data.migrations.core_schema import apply_core_schema
from inv_man_intake.data.provenance import VisualArtifactRecord
from inv_man_intake.data.repository import VisualArtifactRepository
from inv_man_intake.images.feedback_service import VisualArtifactFeedbackService


def _seed_database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        apply_core_schema(conn)
        conn.execute(
            "INSERT INTO firms (firm_id, legal_name, aliases_json, created_at) VALUES (?, ?, ?, ?)",
            ("firm_1", "Alpha Capital", None, "2026-03-01T08:00:00Z"),
        )
        conn.execute(
            (
                "INSERT INTO funds (fund_id, firm_id, fund_name, strategy, asset_class, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            ),
            (
                "fund_1",
                "firm_1",
                "Alpha Fund",
                "market_neutral",
                "equity_market_neutral",
                "2026-03-01T08:30:00Z",
            ),
        )
        conn.execute(
            (
                "INSERT INTO documents (document_id, fund_id, file_name, file_hash, received_at, "
                "version_date, source_channel, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                "doc_1",
                "fund_1",
                "manager_deck.pdf",
                "hash_doc_1",
                "2026-03-01T09:00:00Z",
                "2026-03-01",
                "email",
                "2026-03-01T09:00:00Z",
            ),
        )
        conn.commit()

        repo = VisualArtifactRepository(conn)
        repo.ensure_schema()
        repo.insert_artifact(
            VisualArtifactRecord(
                artifact_id="va_1",
                document_id="doc_1",
                source_type="pdf",
                source_page=1,
                source_slide=None,
                source_ref="pdf-object-1",
                storage_path="artifacts/doc_1/pdf/page-1/object.bin",
                sha256="hash-va-1",
                mime_type="image/jpeg",
                byte_size=128,
                extracted_at="2026-03-01T09:10:00Z",
            )
        )
        repo.ensure_feedback_schema()
        service = VisualArtifactFeedbackService(repo)
        service.record_feedback(
            ImageFeedbackRecord(
                artifact_id="va_1",
                is_informative=True,
                quality_rank=5,
                reviewer="analyst-a",
                timestamp="2026-03-01T10:00:00Z",
            )
        )


def test_image_feedback_report_bundle_writes_json_and_csv(tmp_path: Path) -> None:
    database_path = tmp_path / "feedback.sqlite"
    _seed_database(database_path)
    bundle_dir = tmp_path / "reports"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/image_feedback_report.py",
            "--database",
            str(database_path),
            "--bundle-dir",
            str(bundle_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == ""

    json_files = sorted(bundle_dir.glob("image-feedback-*.json"))
    csv_files = sorted(bundle_dir.glob("image-feedback-*.csv"))
    assert len(json_files) == 1
    assert len(csv_files) == 1

    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["summary"]["total_feedback_records"] == 1
    assert "artifact_id,feedback_count,reviewer_count" in csv_files[0].read_text(encoding="utf-8")
