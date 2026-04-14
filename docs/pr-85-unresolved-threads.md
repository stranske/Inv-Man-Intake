# PR #85 Unresolved Review Threads

Source issue: #24  
Source PR: #85  
Unresolved thread count at audit time: 9

## Classification Criteria

This follow-up classifies whether each audit-time thread still requires a bounded remediation.

### Warranted Fix

- The thread identifies a current correctness or data-integrity issue on `main`
- The thread identifies a real runtime/resource-management bug
- The thread identifies behavior that can mislead downstream consumers in normal usage

### Not-Warranted Disposition

- The thread is a design preference or refactor suggestion rather than a correctness gap
- The proposed change would introduce avoidable compatibility churn relative to the value gained
- The existing implementation already satisfies the shipped scope closely enough for audit closure

## Thread 1

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r2901962459
- **Reviewer**: Copilot
- **File Path**: `src/inv_man_intake/images/extractor.py`
- **Line Number(s)**: 167-174
- **Comment Summary**: `/FlateDecode` PDF image streams were labeled `image/png` even though the extractor stores raw undecoded stream bytes.
- **Classification**: warranted fix
- **Rationale**: This was a real correctness issue. The extractor does not decode or repackage `/FlateDecode` image streams into PNG files, so emitting `image/png` advertised semantics the payload did not actually satisfy. That can mislead downstream consumers and cause bad assumptions during storage or later processing. The follow-up changes this mapping to `application/octet-stream` and updates the test expectation to match the real behavior.
- **Disposition**: Fixed in this follow-up PR by changing `_pdf_mime_type()` and the associated extractor test.

## Thread 2

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r2901962469
- **Reviewer**: Copilot
- **File Path**: `src/inv_man_intake/images/extractor.py`
- **Line Number(s)**: 229-243
- **Comment Summary**: `artifact_id` derivation uses SHA-1 and suggested moving to truncated SHA-256 or BLAKE2.
- **Classification**: not-warranted disposition
- **Rationale**: This suggestion is reasonable as a future cleanup, but it is not the right audit follow-up now. `artifact_id` is already part of the persisted artifact identity contract, and changing the derivation algorithm after merge would churn IDs for the same source material across runs. The repo already stores `sha256` for content-level deduplication, so there is no current correctness defect requiring this compatibility-breaking change.
- **Disposition**: Dispositioned as not warranted for this audit follow-up; keep existing stable `artifact_id` derivation and preserve backward compatibility.

## Thread 3

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r2901962472
- **Reviewer**: Copilot
- **File Path**: `src/inv_man_intake/data/repository.py`
- **Line Number(s)**: 341-362
- **Comment Summary**: `VisualArtifactRepository.ensure_schema()` embeds DDL inline instead of using the broader migration framework.
- **Classification**: not-warranted disposition
- **Rationale**: This is an architectural consistency suggestion, not a demonstrated correctness bug. Moving the table creation into a dedicated migration would add process churn but does not materially change the shipped repository behavior or close a broken acceptance criterion from issue `#24`. The bounded audit follow-up should stay focused on concrete correctness and review-hygiene gaps rather than reworking the migration structure.
- **Disposition**: Dispositioned as not warranted for this audit follow-up; migration centralization can be handled separately if it becomes a broader repo standardization task.

## Thread 4

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r2901962478
- **Reviewer**: Copilot
- **File Path**: `src/inv_man_intake/data/repository.py`
- **Line Number(s)**: 341-357
- **Comment Summary**: `ensure_schema()` created a foreign-keyed table without first verifying that the core `documents` table existed.
- **Classification**: warranted fix
- **Rationale**: This was a legitimate setup/integrity concern. The artifact repository is coupled to the core schema through a foreign key, so proceeding without the `documents` table invites confusing failures later and obscures the true setup requirement. The follow-up adds an explicit precondition check that raises a clear error when the core schema is missing, and the tests now cover that failure mode directly.
- **Disposition**: Fixed in this follow-up PR by verifying the presence of `documents` before creating the visual-artifact schema.

## Thread 5

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r2901962484
- **Reviewer**: Copilot
- **File Path**: `tests/images/test_extractor.py`
- **Line Number(s)**: 52-67
- **Comment Summary**: The test encoded the same incorrect `image/png` expectation for `/FlateDecode` raw PDF streams.
- **Classification**: warranted fix
- **Rationale**: Once the extractor MIME behavior is corrected, the test needs to move with it so the repo asserts the actual delivered contract instead of the old incorrect assumption. Leaving the test unchanged would either preserve the wrong behavior or keep the repo green for the wrong reason. The follow-up updates the assertion to the generic binary MIME type that matches the undecoded payload.
- **Disposition**: Fixed in this follow-up PR by updating the extractor test expectation to `application/octet-stream`.

## Thread 6

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r2901962490
- **Reviewer**: Copilot
- **File Path**: `src/inv_man_intake/data/repository.py`
- **Line Number(s)**: 338-340
- **Comment Summary**: `VisualArtifactRepository` did not enable `PRAGMA foreign_keys = ON` in its own initializer.
- **Classification**: warranted fix
- **Rationale**: This was a real data-integrity issue because direct callers of `VisualArtifactRepository` could bypass foreign-key enforcement silently even though the repository depends on document linkage. The follow-up enables foreign keys in the repository initializer so the repository behaves correctly even when instantiated independently, and the tests now verify that the pragma is enabled automatically.
- **Disposition**: Fixed in this follow-up PR by enabling foreign keys in `VisualArtifactRepository.__init__()`.

## Thread 7

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r2901962505
- **Reviewer**: Copilot
- **File Path**: `src/inv_man_intake/images/extractor.py`
- **Line Number(s)**: 108-137
- **Comment Summary**: `_extract_pptx_artifacts()` opened a `ZipFile` without closing it.
- **Classification**: warranted fix
- **Rationale**: This was a legitimate resource-management bug. The extractor can be called repeatedly over many documents, and keeping the archive lifetime unbounded is unnecessary when a simple context manager resolves it. The follow-up switches the function to `with zipfile.ZipFile(...) as archive:` so the archive is always closed when extraction finishes, even on error paths.
- **Disposition**: Fixed in this follow-up PR by wrapping PPTX archive access in a context manager.

## Thread 8

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r2901962515
- **Reviewer**: Copilot
- **File Path**: `src/inv_man_intake/images/extractor.py`
- **Line Number(s)**: 148-152
- **Comment Summary**: Missing PDF stream bytes produced a zero-byte `VisualArtifact` instead of being treated as an extraction failure.
- **Classification**: warranted fix
- **Rationale**: This was a concrete correctness issue. A zero-byte artifact with a real hash and storage path looks like a successful extraction even though no usable image payload was found. The follow-up changes `_extract_pdf_stream()` to return `None` when the stream is missing or empty and updates artifact collection to skip those objects instead of emitting fake artifacts. A focused test now covers that path.
- **Disposition**: Fixed in this follow-up PR by skipping missing or empty PDF image streams.

## Thread 9

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r2901962529
- **Reviewer**: Copilot
- **File Path**: `src/inv_man_intake/data/repository.py`
- **Line Number(s)**: 365-386
- **Comment Summary**: `insert_artifact()` raised on duplicate stable artifact IDs during re-processing instead of behaving idempotently.
- **Classification**: warranted fix
- **Rationale**: This was a reasonable operational robustness issue for a catalog keyed by stable artifact IDs. Re-processing the same document should not turn a no-op deduplication scenario into a hard failure when the record already exists. The follow-up makes artifact insertion idempotent with `INSERT OR IGNORE` and adds a regression test showing that repeated inserts for the same record do not create duplicates or raise integrity errors.
- **Disposition**: Fixed in this follow-up PR by making artifact insertion idempotent for repeated stable IDs.

## Final Status

- Total threads: 9
- Warranted fixes: 7
- Not-warranted dispositions: 2
- Remaining unresolved: 0 after posting per-thread resolution comments on PR #85
