from __future__ import annotations

from pathlib import Path

from scripts.validate_child_issues import REQUIRED_SECTIONS, main, validate_issue_body


def _issue_body_with_sections() -> str:
    return "\n\n".join(f"## {section}\ncontent" for section in REQUIRED_SECTIONS)


def _write_issue_files(directory: Path, body: str) -> None:
    for issue_number in range(8, 16):
        (directory / f"issue-{issue_number}.md").write_text(body, encoding="utf-8")


def test_validate_issue_body_all_sections_present() -> None:
    result = validate_issue_body(8, _issue_body_with_sections())
    assert result.issue_number == 8
    assert result.missing_sections == ()
    assert result.is_valid


def test_validate_issue_body_reports_missing_sections() -> None:
    body = "## Why\nx\n\n## Scope\ny\n\n## Tasks\nz"
    result = validate_issue_body(9, body)
    assert result.issue_number == 9
    assert result.missing_sections == (
        "Non-Goals",
        "Acceptance Criteria",
        "Implementation Notes",
    )
    assert not result.is_valid


def test_main_success_with_local_issue_directory(tmp_path: Path) -> None:
    _write_issue_files(tmp_path, _issue_body_with_sections())
    exit_code = main(["--issues-dir", str(tmp_path)])
    assert exit_code == 0


def test_main_failure_when_section_missing(tmp_path: Path) -> None:
    good_body = _issue_body_with_sections()
    _write_issue_files(tmp_path, good_body)
    (tmp_path / "issue-12.md").write_text(
        good_body.replace("## Scope", "## Scope Missing"), encoding="utf-8"
    )

    exit_code = main(["--issues-dir", str(tmp_path)])
    assert exit_code == 1
