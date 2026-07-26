"""No-egress spreadsheet exports for normalized return series."""

from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from io import BytesIO, StringIO

from inv_man_intake.export.manifest import ExportArtifact, ExportItem, ExportManifest
from inv_man_intake.extraction.providers.base import ExtractedTable
from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
)
from inv_man_intake.performance.normalize import NormalizedPerformancePayload, normalize_payload


def export_return_series(
    performance: PerformancePayload | NormalizedPerformancePayload | None,
    *,
    source_doc_id: str,
    source_page: int | None = None,
    method: str = "normalized-performance",
    tables: Sequence[ExtractedTable] = (),
) -> ExportManifest:
    """Export normalized performance rows as XLSX and CSV with source lineage.

    ``None`` is the explicit no-series path for callers that completed extraction
    without a usable return series.  Concrete payloads are normalized before any
    cell is written, which also reuses the existing finite-value validation.
    """

    if performance is None:
        return ExportManifest.from_items(
            (ExportItem(item_ref="return-series", skip_reason="no_series_found"),)
        )

    normalized = (
        performance
        if isinstance(performance, NormalizedPerformancePayload)
        else normalize_payload(performance)
    )
    rows = _return_rows(
        normalized, source_doc_id=source_doc_id, source_page=source_page, method=method
    )
    if not rows:
        return ExportManifest.from_items(
            (ExportItem(item_ref="return-series", skip_reason="no_series_found"),)
        )

    provenance_refs = tuple(sorted({row[3] for row in rows}))
    return ExportManifest.from_items(
        (
            ExportItem(
                item_ref="return-series.csv",
                artifact=ExportArtifact(
                    name="return-series.csv",
                    media_type="text/csv",
                    content=_build_csv(rows),
                    provenance_refs=provenance_refs,
                ),
            ),
            ExportItem(
                item_ref="return-series.xlsx",
                artifact=ExportArtifact(
                    name="return-series.xlsx",
                    media_type=(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ),
                    content=_build_workbook(rows, tables=tables, provenance_refs=provenance_refs),
                    provenance_refs=provenance_refs,
                ),
            ),
        )
    )


def _return_rows(
    normalized: NormalizedPerformancePayload,
    *,
    source_doc_id: str,
    source_page: int | None,
    method: str,
) -> tuple[tuple[str, float, str, str], ...]:
    provenance = f"{source_doc_id}:{source_page if source_page is not None else 'unknown'}:{method}"
    rows: list[tuple[str, float, str, str]] = []
    for series in (normalized.monthly, normalized.quarterly, normalized.annual):
        if series is not None:
            rows.extend(_series_rows(series, provenance=provenance))
    return tuple(rows)


def _series_rows(
    series: PerformanceSeries,
    *,
    provenance: str,
) -> tuple[tuple[str, float, str, str], ...]:
    rows: list[tuple[str, float, str, str]] = []
    for point in series.points:
        _require_finite(point)
        rows.append((point.as_of.isoformat(), point.value, series.frequency, provenance))
    return tuple(rows)


def _require_finite(point: PerformancePoint) -> None:
    if not math.isfinite(point.value):
        raise ValueError("return series contains a non-finite value")


def _build_csv(rows: Sequence[tuple[str, float, str, str]]) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("period", "value", "frequency", "provenance"))
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _build_workbook(
    rows: Sequence[tuple[str, float, str, str]],
    *,
    tables: Sequence[ExtractedTable],
    provenance_refs: Sequence[str],
) -> bytes:
    from openpyxl import Workbook  # type: ignore[import-untyped]

    workbook = Workbook()
    returns_sheet = workbook.active
    returns_sheet.title = "Return Series"
    returns_sheet.append(("period", "value", "frequency", "provenance"))
    for row in rows:
        returns_sheet.append(row)

    manifest_sheet = workbook.create_sheet("Manifest")
    manifest_sheet.append(("kind", "reference"))
    for reference in provenance_refs:
        manifest_sheet.append(("provenance", reference))
    for reference in _table_lineage(tables):
        manifest_sheet.append(("table_cell", reference))

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _table_lineage(tables: Sequence[ExtractedTable]) -> tuple[str, ...]:
    lineage: list[str] = []
    for table_index, table in enumerate(tables):
        location = getattr(table, "location", None)
        source_doc = getattr(location, "source_doc_id", "unknown")
        page = getattr(location, "source_page", None)
        table_id = getattr(table, "table_id", "") or str(table_index)
        for cell in table.cells:
            lineage.append(
                f"{source_doc}:{page if page is not None else 'unknown'}:table:{table_id}:"
                f"r{cell.row_index}:c{cell.column_index}={cell.value}"
            )
    return tuple(lineage)


__all__ = ["export_return_series"]
