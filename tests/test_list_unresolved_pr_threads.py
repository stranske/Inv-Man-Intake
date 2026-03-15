from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "list_unresolved_pr_threads.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_script(
    *, tmp_path: Path, gh_script: str, disposition_doc: Path
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "gh", gh_script)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["DISPOSITION_DOC"] = str(disposition_doc)

    return subprocess.run(
        [str(SCRIPT_PATH), "76"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_script_falls_back_to_disposition_doc_when_github_api_fails(tmp_path: Path) -> None:
    disposition_doc = tmp_path / "pr-76-thread-disposition.md"
    disposition_doc.write_text(
        "\n".join(
            [
                "# PR #76 Unresolved Thread Disposition",
                "",
                "| Thread Slot | Thread ID | Location | Classification | Rationale | Follow-up Reference |",
                "|---|---|---|---|---|---|",
                "| 1 | thread-alpha | `src/example.py::handler` | warranted-fix | rationale | PR #172 |",
                "| 2 | thread-beta | `tests/test_example.py` | not-warranted | rationale | issue #136 |",
            ]
        ),
        encoding="utf-8",
    )
    result = _run_script(
        tmp_path=tmp_path,
        gh_script="#!/usr/bin/env bash\nexit 1\n",
        disposition_doc=disposition_doc,
    )

    assert result.returncode == 0
    assert "warning: gh api graphql failed; using fallback data" in result.stderr
    assert "thread-alpha\t`src/example.py::handler`\t-\tlocal-doc\t-" in result.stdout
    assert "thread-beta\t`tests/test_example.py`\t-\tlocal-doc\t-" in result.stdout
    assert "unresolved_threads_count: 2" in result.stdout


def test_script_lists_live_unresolved_threads_from_github_api_response(tmp_path: Path) -> None:
    disposition_doc = tmp_path / "unused.md"
    disposition_doc.write_text("# unused\n", encoding="utf-8")
    gh_output = """#!/usr/bin/env bash
cat <<'JSON'
{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[
  {"id":"THREAD_1","isResolved":false,"comments":{"nodes":[{"path":"src/a.py","line":14,"url":"https://example.test/t1","author":{"login":"reviewer-a"}}]}},
  {"id":"THREAD_2","isResolved":true,"comments":{"nodes":[{"path":"src/b.py","line":20,"url":"https://example.test/t2","author":{"login":"reviewer-b"}}]}},
  {"id":"THREAD_3","isResolved":false,"comments":{"nodes":[{"path":"tests/test_a.py","line":7,"url":"https://example.test/t3","author":{"login":"reviewer-c"}}]}}
]}}}}}
JSON
"""
    result = _run_script(tmp_path=tmp_path, gh_script=gh_output, disposition_doc=disposition_doc)

    assert result.returncode == 0
    assert result.stderr == ""
    assert "THREAD_1\tsrc/a.py\t14\treviewer-a\thttps://example.test/t1" in result.stdout
    assert "THREAD_3\ttests/test_a.py\t7\treviewer-c\thttps://example.test/t3" in result.stdout
    assert "THREAD_2" not in result.stdout
    assert "unresolved_threads_count: 2" in result.stdout


def test_script_uses_repo_disposition_doc_to_emit_seven_audit_time_threads(tmp_path: Path) -> None:
    result = _run_script(
        tmp_path=tmp_path,
        gh_script="#!/usr/bin/env bash\nexit 1\n",
        disposition_doc=REPO_ROOT / "docs" / "pr-76-thread-disposition.md",
    )

    assert result.returncode == 0
    assert "warning: gh api graphql failed; using fallback data" in result.stderr
    assert "pending-api-recovery-1" in result.stdout
    assert "pending-api-recovery-7" in result.stdout
    assert "unresolved_threads_count: 7" in result.stdout
