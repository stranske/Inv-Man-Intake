from __future__ import annotations

from pathlib import Path

import pytest
from pytest import CaptureFixture
from scripts.validate_child_issues import (
    REQUIRED_SECTIONS,
    ensure_epic_task_links,
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


def test_ensure_epic_task_links_adds_missing_link() -> None:
    body = _epic_body_with_task_links().replace(
        "https://github.com/stranske/Inv-Man-Intake/issues/12",
        "https://github.com/stranske/Inv-Man-Intake/issues/1200",
    )
    updated, added = ensure_epic_task_links(
        epic_issue_body=body,
        owner="stranske",
        repo="Inv-Man-Intake",
        start_issue=8,
        end_issue=15,
    )
    assert added == (12,)
    assert "https://github.com/stranske/Inv-Man-Intake/issues/12" in updated


def test_ensure_epic_task_links_requires_tasks_header() -> None:
    with pytest.raises(ValueError, match="## Tasks"):
        ensure_epic_task_links(
            epic_issue_body="## Why\nx",
            owner="stranske",
            repo="Inv-Man-Intake",
            start_issue=8,
            end_issue=15,
        )


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


def test_main_fix_epic_task_links_requires_issues_dir() -> None:
    exit_code = main(["--check-epic-task-links", "--fix-epic-task-links"])
    assert exit_code == 2


def test_main_fix_epic_task_links_updates_epic_file(tmp_path: Path) -> None:
    _write_issue_files(tmp_path, _issue_body_with_sections())
    _write_epic_issue(
        tmp_path,
        "## Tasks\n- [#8](https://github.com/stranske/Inv-Man-Intake/issues/8)\n",
    )
    exit_code = main(
        ["--issues-dir", str(tmp_path), "--check-epic-task-links", "--fix-epic-task-links"]
    )
    assert exit_code == 0
    updated_epic = (tmp_path / "issue-7.md").read_text(encoding="utf-8")
    for issue in range(8, 16):
        assert f"https://github.com/stranske/Inv-Man-Intake/issues/{issue}" in updated_epic


def test_main_fix_epic_task_links_updates_epic_body_file(tmp_path: Path) -> None:
    _write_issue_files(tmp_path, _issue_body_with_sections())
    epic_body_file = tmp_path / "epic-body.md"
    epic_body_file.write_text(
        "## Tasks\n- [#8](https://github.com/stranske/Inv-Man-Intake/issues/8)\n",
        encoding="utf-8",
    )
    exit_code = main(
        [
            "--issues-dir",
            str(tmp_path),
            "--check-epic-task-links",
            "--fix-epic-task-links",
            "--epic-body-file",
            str(epic_body_file),
        ]
    )
    assert exit_code == 0
    updated_epic = epic_body_file.read_text(encoding="utf-8")
    for issue in range(8, 16):
        assert f"https://github.com/stranske/Inv-Man-Intake/issues/{issue}" in updated_epic


def test_main_epic_body_file_requires_check_or_fix(tmp_path: Path) -> None:
    _write_issue_files(tmp_path, _issue_body_with_sections())
    epic_body_file = tmp_path / "epic-body.md"
    epic_body_file.write_text("## Tasks\n", encoding="utf-8")
    exit_code = main(["--issues-dir", str(tmp_path), "--epic-body-file", str(epic_body_file)])
    assert exit_code == 2


def test_main_epic_body_file_missing_path_errors() -> None:
    exit_code = main(
        [
            "--epic-body-file",
            "does-not-exist.md",
            "--check-epic-task-links",
        ]
    )
    assert exit_code == 2


def test_main_epic_links_only_requires_check_flag() -> None:
    exit_code = main(["--epic-links-only"])
    assert exit_code == 2


def test_main_epic_links_only_fixes_epic_body_without_issue_files(tmp_path: Path) -> None:
    epic_body_file = tmp_path / "epic-body.md"
    epic_body_file.write_text(
        "## Tasks\n- [#8](https://github.com/stranske/Inv-Man-Intake/issues/8)\n",
        encoding="utf-8",
    )
    exit_code = main(
        [
            "--check-epic-task-links",
            "--fix-epic-task-links",
            "--epic-links-only",
            "--epic-body-file",
            str(epic_body_file),
        ]
    )
    assert exit_code == 0
    updated_epic = epic_body_file.read_text(encoding="utf-8")
    for issue in range(8, 16):
        assert f"https://github.com/stranske/Inv-Man-Intake/issues/{issue}" in updated_epic


def test_main_fix_epic_task_links_remote_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    issue_body = _issue_body_with_sections()
    epic_body = "## Tasks\n- [#8](https://github.com/stranske/Inv-Man-Intake/issues/8)\n"

    def fake_loader(owner: str, repo: str, issue_number: int, token: str | None) -> str:
        return issue_body if issue_number != 7 else epic_body

    monkeypatch.setattr("scripts.validate_child_issues._load_issue_body_from_github", fake_loader)
    exit_code = main(["--check-epic-task-links", "--fix-epic-task-links", "--token", ""])
    assert exit_code == 2


def test_main_fix_epic_task_links_remote_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    issue_body = _issue_body_with_sections()
    epic_body = "## Tasks\n- [#8](https://github.com/stranske/Inv-Man-Intake/issues/8)\n"
    patched: dict[str, str] = {}

    def fake_loader(owner: str, repo: str, issue_number: int, token: str | None) -> str:
        return issue_body if issue_number != 7 else epic_body

    def fake_patcher(
        owner: str, repo: str, issue_number: int, body: str, token: str | None
    ) -> None:
        patched["body"] = body

    monkeypatch.setattr("scripts.validate_child_issues._load_issue_body_from_github", fake_loader)
    monkeypatch.setattr("scripts.validate_child_issues._patch_issue_body_on_github", fake_patcher)
    exit_code = main(["--check-epic-task-links", "--fix-epic-task-links", "--token", "test-token"])
    assert exit_code == 0
    for issue in range(8, 16):
        assert f"https://github.com/stranske/Inv-Man-Intake/issues/{issue}" in patched["body"]


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


def test_main_print_epic_task_links_checklist_default_range(capsys: CaptureFixture[str]) -> None:
    exit_code = main(["--print-epic-task-links-checklist"])
    captured = capsys.readouterr()
    assert exit_code == 0

    lines = captured.out.strip().splitlines()
    assert len(lines) == 8
    assert lines[0] == "- [ ] [#8](https://github.com/stranske/Inv-Man-Intake/issues/8)"
    assert lines[-1] == "- [ ] [#15](https://github.com/stranske/Inv-Man-Intake/issues/15)"


def test_main_print_fixed_epic_body_requires_check_flag() -> None:
    exit_code = main(["--print-fixed-epic-body"])
    assert exit_code == 2


def test_main_print_fixed_epic_body_outputs_patched_content(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_issue_files(tmp_path, _issue_body_with_sections())
    _write_epic_issue(
        tmp_path,
        "## Why\nx\n\n## Tasks\n- [#8](https://github.com/stranske/Inv-Man-Intake/issues/8)\n",
    )
    exit_code = main(
        [
            "--issues-dir",
            str(tmp_path),
            "--check-epic-task-links",
            "--epic-links-only",
            "--print-fixed-epic-body",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "--- BEGIN FIXED EPIC BODY ---" in captured.out
    assert "--- END FIXED EPIC BODY ---" in captured.out
    for issue in range(8, 16):
        assert f"https://github.com/stranske/Inv-Man-Intake/issues/{issue}" in captured.out
