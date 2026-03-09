from __future__ import annotations

from pathlib import Path

from pytest import CaptureFixture

from scripts.validate_child_issues import (
    REQUIRED_SECTIONS,
    main,
    render_epic_task_links_checklist,
    validate_epic_task_links,
    validate_issue_body,
)


def _issue_body_with_sections() -> str:
    return "\n\n".join(f"## {section}\ncontent" for section in REQUIRED_SECTIONS)


def _write_issue_files(directory: Path, body: str) -> None:
    for issue_number in range(8, 16):
        (directory / f"issue-{issue_number}.md").write_text(body, encoding="utf-8")


def _write_epic_issue(directory: Path, body: str) -> None:
    (directory / "issue-7.md").write_text(body, encoding="utf-8")


def _epic_body_with_task_links() -> str:
    links = "\n".join(
        f"- [#{issue}](https://github.com/stranske/Inv-Man-Intake/issues/{issue})"
        for issue in range(8, 16)
    )
    return f"## Why\nx\n\n## Tasks\n{links}\n\n## Acceptance Criteria\ny"


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


def test_validate_epic_task_links_success() -> None:
    result = validate_epic_task_links(
        epic_issue_number=7,
        epic_issue_body=_epic_body_with_task_links(),
        owner="stranske",
        repo="Inv-Man-Intake",
        start_issue=8,
        end_issue=15,
    )
    assert result.is_valid
    assert result.missing_issue_links == ()


def test_validate_epic_task_links_reports_missing_link() -> None:
    body = _epic_body_with_task_links().replace(
        "https://github.com/stranske/Inv-Man-Intake/issues/12",
        "https://github.com/stranske/Inv-Man-Intake/issues/1200",
    )
    result = validate_epic_task_links(
        epic_issue_number=7,
        epic_issue_body=body,
        owner="stranske",
        repo="Inv-Man-Intake",
        start_issue=8,
        end_issue=15,
    )
    assert not result.is_valid
    assert result.missing_issue_links == (12,)


def test_main_failure_when_epic_task_links_missing(tmp_path: Path) -> None:
    _write_issue_files(tmp_path, _issue_body_with_sections())
    _write_epic_issue(
        tmp_path,
        "## Tasks\n- [#8](https://github.com/stranske/Inv-Man-Intake/issues/8)\n",
    )
    exit_code = main(["--issues-dir", str(tmp_path), "--check-epic-task-links"])
    assert exit_code == 1


def test_main_success_with_epic_task_links_validation(tmp_path: Path) -> None:
    _write_issue_files(tmp_path, _issue_body_with_sections())
    _write_epic_issue(tmp_path, _epic_body_with_task_links())
    exit_code = main(["--issues-dir", str(tmp_path), "--check-epic-task-links"])
    assert exit_code == 0


def test_render_epic_task_links_checklist() -> None:
    output = render_epic_task_links_checklist(
        owner="stranske",
        repo="Inv-Man-Intake",
        start_issue=8,
        end_issue=10,
    )
    assert output == "\n".join(
        [
            "- [ ] [#8](https://github.com/stranske/Inv-Man-Intake/issues/8)",
            "- [ ] [#9](https://github.com/stranske/Inv-Man-Intake/issues/9)",
            "- [ ] [#10](https://github.com/stranske/Inv-Man-Intake/issues/10)",
        ]
    )


def test_main_print_epic_task_links_checklist(capsys: CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "--owner",
            "stranske",
            "--repo",
            "Inv-Man-Intake",
            "--start-issue",
            "8",
            "--end-issue",
            "9",
            "--print-epic-task-links-checklist",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert (
        captured.out.strip() == "- [ ] [#8](https://github.com/stranske/Inv-Man-Intake/issues/8)\n"
        "- [ ] [#9](https://github.com/stranske/Inv-Man-Intake/issues/9)"
    )
