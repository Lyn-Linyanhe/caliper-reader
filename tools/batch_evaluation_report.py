"""Helpers for exporting batch caliper evaluation reports."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


FIELDNAMES: tuple[str, ...] = (
    "image",
    "truth_mm",
    "filename_truth_mm",
    "truth_source",
    "status",
    "error",
    "reading_mm",
    "abs_error_mm",
    "within_tolerance",
    "tolerance_mm",
    "within_visual_tolerance",
    "visual_tolerance_mm",
    "suspected_error_module",
    "diagnostic_flags",
    "error_module_final",
    "error_notes",
    "elapsed_ms",
    "main_scale_mm",
    "vernier_scale_mm",
    "split_y",
    "seam_source",
    "main_tick_count",
    "vernier_tick_count",
    "zero_x",
    "alignment_confidence",
    "main_ocr_ok",
    "main_ocr_reason",
    "main_ocr_text",
    "main_ocr_confidence",
)


def truth_from_name(path: Path) -> float | None:
    try:
        return float(path.stem)
    except ValueError:
        return None


def truth_for_path(
    path: Path,
    manual_truth: Mapping[str, float],
) -> tuple[float | None, float | None, str]:
    filename_truth = truth_from_name(path)
    if path.name in manual_truth:
        return float(manual_truth[path.name]), filename_truth, "manual_correction"
    return filename_truth, filename_truth, "filename"


def is_within_tolerance(abs_error: float | None, tolerance: float) -> bool | None:
    if abs_error is None:
        return None
    return abs_error <= tolerance


def _flag(condition: bool, name: str, flags: list[str]) -> None:
    if condition:
        flags.append(name)


def classify_suspected_error(row: Mapping[str, Any]) -> tuple[str, str]:
    flags: list[str] = []
    status_failed = row.get("status") != "ok"
    vernier_count = int(row.get("vernier_tick_count") or 0)
    main_count = int(row.get("main_tick_count") or 0)
    if "within_visual_tolerance" in row:
        large_error = row.get("within_visual_tolerance") is False
    else:
        large_error = row.get("within_tolerance") is False
    tick_region_starved = (
        "split_y" in row
        and row.get("split_y") is not None
        and 0 < main_count <= 20
        and vernier_count <= 0
    )

    _flag(status_failed, "status_failed", flags)
    _flag(row.get("reading_mm") is None, "reading_missing", flags)
    _flag(row.get("roi_valid") is False, "roi_invalid", flags)
    _flag("split_y" in row and row.get("split_y") is None, "split_missing", flags)
    _flag(tick_region_starved, "tick_region_starved", flags)
    _flag(row.get("main_ocr_ok") is False, "ocr_failed", flags)
    _flag(row.get("zero_x") is None, "zero_missing", flags)
    _flag(vernier_count <= 0, "vernier_ticks_empty", flags)
    _flag(main_count <= 0, "main_ticks_empty", flags)
    _flag(large_error, "large_error", flags)

    if status_failed or row.get("reading_mm") is None:
        module = "pipeline"
    elif row.get("roi_valid") is False:
        module = "roi"
    elif "split_y" in row and row.get("split_y") is None:
        module = "region_split"
    elif tick_region_starved:
        module = "region_split"
    elif row.get("main_ocr_ok") is False:
        module = "ocr"
    elif row.get("zero_x") is None:
        module = "vernier_zero_line"
    elif vernier_count <= 0:
        module = "vernier_ticks"
    elif main_count <= 0:
        module = "main_ticks"
    elif large_error:
        module = "reading_fusion"
    else:
        module = "none"
    return module, ";".join(flags)


def normalize_row(
    row: Mapping[str, Any],
    tolerance: float,
    visual_tolerance: float = 0.10,
) -> dict[str, Any]:
    normalized = dict(row)
    truth = normalized.get("truth_mm")
    reading = normalized.get("reading_mm")
    abs_error = None
    if truth is not None and reading is not None:
        abs_error = round(abs(float(reading) - float(truth)), 4)
    normalized["abs_error_mm"] = abs_error
    normalized["within_tolerance"] = is_within_tolerance(abs_error, tolerance)
    normalized["tolerance_mm"] = tolerance
    normalized["within_visual_tolerance"] = is_within_tolerance(abs_error, visual_tolerance)
    normalized["visual_tolerance_mm"] = visual_tolerance
    module, flags = classify_suspected_error(normalized)
    normalized["suspected_error_module"] = module
    normalized["diagnostic_flags"] = flags
    normalized.setdefault("error_module_final", "")
    normalized.setdefault("error_notes", "")
    for field in FIELDNAMES:
        normalized.setdefault(field, "")
    return normalized


def build_summary(
    rows: Sequence[Mapping[str, Any]],
    tolerances: Sequence[float] = (0.02, 0.10, 0.50),
) -> dict[str, Any]:
    labelled = [
        row for row in rows
        if row.get("truth_mm") not in (None, "") and row.get("status") == "ok"
    ]
    errors = [
        float(row["abs_error_mm"]) for row in labelled
        if row.get("abs_error_mm") not in (None, "")
    ]
    summary: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count_total": len(rows),
        "count_with_truth": len(labelled),
        "count_success": sum(1 for row in rows if row.get("status") == "ok"),
        "count_failed": sum(1 for row in rows if row.get("status") != "ok"),
        "mean_abs_error_mm": round(sum(errors) / len(errors), 4) if errors else None,
        "max_abs_error_mm": round(max(errors), 4) if errors else None,
        "module_counts": dict(Counter(str(row.get("suspected_error_module", "unknown")) for row in rows)),
        "status_counts": dict(Counter(str(row.get("status", "unknown")) for row in rows)),
    }
    for tolerance in tolerances:
        key = f"within_{tolerance:.2f}mm".replace(".", "_")
        summary[key] = sum(error <= tolerance for error in errors)
        ratio_key = f"{key}_ratio"
        summary[ratio_key] = round(summary[key] / len(errors), 4) if errors else None
    return summary


def build_report(
    rows: Sequence[Mapping[str, Any]],
    input_dir: Path,
    tolerance: float,
    visual_tolerance: float = 0.10,
) -> dict[str, Any]:
    summary = build_summary(rows)
    summary["input_dir"] = str(input_dir)
    summary["tolerance_mm"] = tolerance
    summary["visual_tolerance_mm"] = visual_tolerance
    return {"summary": summary, "rows": list(rows)}


def write_json(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def _col_name(index: int) -> str:
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(ord("A") + rem) + name
    return name


def _cell_xml(row_index: int, col_index: int, value: Any) -> str:
    ref = f"{_col_name(col_index)}{row_index}"
    if value is None:
        value = ""
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _sheet_xml(rows: Sequence[Sequence[Any]], freeze: bool = False) -> str:
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(
            _cell_xml(row_index, col_index, value)
            for col_index, value in enumerate(row, start=1)
        )
        row_xml.append(f'<row r="{row_index}">{cells}</row>')
    max_col = _col_name(max((len(row) for row in rows), default=1))
    max_row = max(len(rows), 1)
    sheet_views = ""
    if freeze:
        sheet_views = (
            '<sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>'
        )
    auto_filter = f'<autoFilter ref="A1:{max_col}{max_row}"/>' if rows else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{sheet_views}<sheetData>{''.join(row_xml)}</sheetData>{auto_filter}"
        '</worksheet>'
    )


def _summary_rows(summary: Mapping[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = [["metric", "value"]]
    for key, value in summary.items():
        if isinstance(value, dict):
            continue
        rows.append([key, value])
    rows.append([])
    rows.append(["status", "count"])
    for key, value in dict(summary.get("status_counts", {})).items():
        rows.append([key, value])
    rows.append([])
    rows.append(["suspected_error_module", "count"])
    for key, value in dict(summary.get("module_counts", {})).items():
        rows.append([key, value])
    return rows


def write_xlsx(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_sheet = [list(FIELDNAMES)]
    rows_sheet.extend([[row.get(field, "") for field in FIELDNAMES] for row in rows])
    summary_sheet = _summary_rows(summary)

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>'
        '<sheet name="summary" sheetId="1" r:id="rId1"/>'
        '<sheet name="rows" sheetId="2" r:id="rId2"/>'
        '</sheets>'
        '</workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        '</Relationships>'
    )

    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(summary_sheet))
        archive.writestr("xl/worksheets/sheet2.xml", _sheet_xml(rows_sheet, freeze=True))
