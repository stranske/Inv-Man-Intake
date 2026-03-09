from pathlib import Path

from scripts.verify_compare_disposition import (
    extract_concerns,
    main,
    render_disposition_markdown,
)


def test_extract_concerns_from_concerns_heading() -> None:
    report = """
## Provider Comparison Report
    ### Concerns
    - Missing status transition test for archived states.
    - Event timeline lacks UTC normalization.
    ### Agreements
    - No concern lines here.
"""
    concerns = extract_concerns(report, default_reference="https://example.test/output")
    assert [c.text for c in concerns] == [
        "Missing status transition test for archived states.",
        "Event timeline lacks UTC normalization.",
    ]
    assert all(c.reference == "https://example.test/output" for c in concerns)


def test_extract_concerns_deduplicates_across_formats() -> None:
    report = """
- **Concerns:**
  - Missing idempotency check in retry path.
- Concern: Missing idempotency check in retry path.
"""
    concerns = extract_concerns(report, default_reference="https://example.test/output")
    assert len(concerns) == 1
    assert concerns[0].text == "Missing idempotency check in retry path."


def test_render_disposition_markdown_contains_required_phrase() -> None:
    concerns = extract_concerns(
        "### Concerns\n- Ingestion ledger does not record retry attempts.",
        default_reference="https://example.test/output",
    )
    markdown = render_disposition_markdown(
        pr_number=53,
        pr_url="https://github.com/stranske/Inv-Man-Intake/pull/53",
        source_reference_url="https://example.test/output",
        concerns=concerns,
    )
    assert "| Ingestion ledger does not record retry attempts." in markdown
    assert "requires follow-up to address [specific change]" in markdown


def test_main_writes_output_file(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "verify-output.md"
    output_path = tmp_path / "disposition.md"
    input_path.write_text("### Concerns\n- Missing checksum verification.", encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_compare_disposition.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--pr-number",
            "53",
            "--pr-url",
            "https://github.com/stranske/Inv-Man-Intake/pull/53",
            "--source-reference-url",
            "https://example.test/output",
        ],
    )
    assert main() == 0
    generated = output_path.read_text(encoding="utf-8")
    assert "Missing checksum verification." in generated
