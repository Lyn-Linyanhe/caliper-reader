# Batch Evaluation Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable batch-evaluation report for `tupian/` that writes JSON, CSV, and XLSX result tables with automatic suspected error-module labels and blank human-review columns.

**Architecture:** Keep `tools/evaluate_all_pipeline.py` as the user-facing batch command, but move reusable row-building, summary, CSV, and XLSX logic into a focused helper module. The helper consumes ordinary dictionaries and does not depend on image processing internals, so tests can run quickly without processing all images.

**Tech Stack:** Python standard library, OpenCV/NumPy only through the existing pipeline script, `pytest`, standard-library `csv`, `json`, `zipfile`, `xml.sax.saxutils`.

## Global Constraints

- Do not modify production recognition logic in `caliper/`.
- Do not use filenames to influence production recognition; filenames are only offline test truth.
- Do not force-fit 51 vernier ticks or generate missing ticks.
- Generate `evaluation.json`, `evaluation.csv`, and `evaluation.xlsx`.
- XLSX export must not add pandas or openpyxl dependencies.
- `suspected_error_module` is an automatic hint; `error_module_final` and `error_notes` remain blank for human review.
- A failed image must produce one `status=failed` row and must not stop the batch.

---

## File Structure

- Create `tools/batch_evaluation_report.py`
  - Owns truth parsing, row normalization, suspected-module classification, summary statistics, CSV export, and minimal XLSX export.
  - Exposes functions used by tests and `tools/evaluate_all_pipeline.py`.
- Modify `tools/evaluate_all_pipeline.py`
  - Keep the same batch behavior.
  - Use helper functions for row construction and exports.
  - Add optional CLI arguments for input directory, output directory, and tolerance.
- Create `tests/test_batch_evaluation_report.py`
  - Unit tests for helper functions and export artifacts.

### Task 1: Truth, Tolerance, and Row Normalization

**Files:**
- Create: `tools/batch_evaluation_report.py`
- Create: `tests/test_batch_evaluation_report.py`

**Interfaces:**
- Produces: `truth_from_name(path: Path) -> float | None`
- Produces: `truth_for_path(path: Path, manual_truth: Mapping[str, float]) -> tuple[float | None, float | None, str]`
- Produces: `is_within_tolerance(abs_error: float | None, tolerance: float) -> bool | None`
- Produces: `normalize_row(row: Mapping[str, Any], tolerance: float) -> dict[str, Any]`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

from tools.batch_evaluation_report import (
    is_within_tolerance,
    normalize_row,
    truth_for_path,
    truth_from_name,
)


def test_truth_from_numeric_filename():
    assert truth_from_name(Path("100.60.jpg")) == 100.60


def test_truth_from_non_numeric_filename_returns_none():
    assert truth_from_name(Path("wechat_sample.jpg")) is None


def test_manual_truth_overrides_filename_truth():
    truth, filename_truth, source = truth_for_path(
        Path("14.80.jpg"),
        {"14.80.jpg": 140.80},
    )
    assert truth == 140.80
    assert filename_truth == 14.80
    assert source == "manual_correction"


def test_tolerance_boundary_is_inclusive():
    assert is_within_tolerance(0.02, 0.02) is True
    assert is_within_tolerance(0.0201, 0.02) is False
    assert is_within_tolerance(None, 0.02) is None


def test_normalize_row_adds_human_review_columns():
    row = normalize_row(
        {"image": "100.00.jpg", "truth_mm": 100.0, "reading_mm": 100.0, "status": "ok"},
        tolerance=0.02,
    )
    assert row["abs_error_mm"] == 0.0
    assert row["within_tolerance"] is True
    assert row["tolerance_mm"] == 0.02
    assert row["error_module_final"] == ""
    assert row["error_notes"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: FAIL because `tools.batch_evaluation_report` does not exist.

- [ ] **Step 3: Implement minimal helper functions**

Create `tools/batch_evaluation_report.py` with:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


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


def normalize_row(row: Mapping[str, Any], tolerance: float) -> dict[str, Any]:
    normalized = dict(row)
    truth = normalized.get("truth_mm")
    reading = normalized.get("reading_mm")
    abs_error = None
    if truth is not None and reading is not None:
        abs_error = round(abs(float(reading) - float(truth)), 4)
    normalized["abs_error_mm"] = abs_error
    normalized["within_tolerance"] = is_within_tolerance(abs_error, tolerance)
    normalized["tolerance_mm"] = tolerance
    normalized.setdefault("suspected_error_module", "unknown")
    normalized.setdefault("diagnostic_flags", "")
    normalized.setdefault("error_module_final", "")
    normalized.setdefault("error_notes", "")
    return normalized
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: PASS.

### Task 2: Suspected Error-Module Classification

**Files:**
- Modify: `tools/batch_evaluation_report.py`
- Modify: `tests/test_batch_evaluation_report.py`

**Interfaces:**
- Produces: `classify_suspected_error(row: Mapping[str, Any]) -> tuple[str, str]`
- Consumed by: `normalize_row()`

- [ ] **Step 1: Write failing tests**

```python
from tools.batch_evaluation_report import classify_suspected_error, normalize_row


def test_failed_row_classifies_as_pipeline():
    module, flags = classify_suspected_error({"status": "failed"})
    assert module == "pipeline"
    assert "status_failed" in flags


def test_ocr_failure_classifies_as_ocr_before_fusion():
    row = normalize_row(
        {
            "status": "ok",
            "truth_mm": 100.0,
            "reading_mm": 101.0,
            "main_ocr_ok": False,
            "zero_x": 123.0,
            "vernier_tick_count": 45,
            "main_tick_count": 30,
        },
        tolerance=0.02,
    )
    assert row["suspected_error_module"] == "ocr"
    assert "ocr_failed" in row["diagnostic_flags"]


def test_missing_zero_line_classifies_as_vernier_zero_line():
    row = normalize_row(
        {
            "status": "ok",
            "truth_mm": 72.52,
            "reading_mm": 71.52,
            "main_ocr_ok": True,
            "zero_x": None,
            "vernier_tick_count": 40,
            "main_tick_count": 30,
        },
        tolerance=0.02,
    )
    assert row["suspected_error_module"] == "vernier_zero_line"


def test_large_error_with_available_intermediates_classifies_as_reading_fusion():
    row = normalize_row(
        {
            "status": "ok",
            "truth_mm": 22.0,
            "reading_mm": 23.0,
            "main_ocr_ok": True,
            "zero_x": 100.0,
            "vernier_tick_count": 48,
            "main_tick_count": 35,
        },
        tolerance=0.02,
    )
    assert row["suspected_error_module"] == "reading_fusion"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: FAIL because `classify_suspected_error` is missing or `normalize_row` does not call it.

- [ ] **Step 3: Implement classification**

Add deterministic rules in this order:

```python
def _flag(condition: bool, name: str, flags: list[str]) -> None:
    if condition:
        flags.append(name)


def classify_suspected_error(row: Mapping[str, Any]) -> tuple[str, str]:
    flags: list[str] = []
    status_failed = row.get("status") != "ok"
    _flag(status_failed, "status_failed", flags)
    _flag(row.get("reading_mm") is None, "reading_missing", flags)
    _flag(row.get("roi_valid") is False, "roi_invalid", flags)
    _flag(row.get("split_y") is None, "split_missing", flags)
    _flag(row.get("main_ocr_ok") is False, "ocr_failed", flags)
    _flag(row.get("zero_x") is None, "zero_missing", flags)
    _flag(int(row.get("vernier_tick_count") or 0) <= 0, "vernier_ticks_empty", flags)
    _flag(int(row.get("main_tick_count") or 0) <= 0, "main_ticks_empty", flags)
    _flag(row.get("within_tolerance") is False, "large_error", flags)

    if status_failed or row.get("reading_mm") is None:
        module = "pipeline"
    elif row.get("roi_valid") is False:
        module = "roi"
    elif row.get("split_y") is None:
        module = "region_split"
    elif row.get("main_ocr_ok") is False:
        module = "ocr"
    elif row.get("zero_x") is None:
        module = "vernier_zero_line"
    elif int(row.get("vernier_tick_count") or 0) <= 0:
        module = "vernier_ticks"
    elif int(row.get("main_tick_count") or 0) <= 0:
        module = "main_ticks"
    elif row.get("within_tolerance") is False:
        module = "reading_fusion"
    else:
        module = "none"
    return module, ";".join(flags)
```

Update `normalize_row()` to call `classify_suspected_error()` after computing `within_tolerance`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: PASS.

### Task 3: Summary and CSV Export

**Files:**
- Modify: `tools/batch_evaluation_report.py`
- Modify: `tests/test_batch_evaluation_report.py`

**Interfaces:**
- Produces: `build_summary(rows: Sequence[Mapping[str, Any]], tolerances: Sequence[float] = (0.02, 0.10, 0.50)) -> dict[str, Any]`
- Produces: `write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None`
- Produces: `FIELDNAMES: tuple[str, ...]`

- [ ] **Step 1: Write failing tests**

```python
from tools.batch_evaluation_report import FIELDNAMES, build_summary, write_csv


def test_summary_counts_accuracy_and_modules():
    rows = [
        normalize_row({"image": "a.jpg", "status": "ok", "truth_mm": 1.0, "reading_mm": 1.0}, 0.02),
        normalize_row({"image": "b.jpg", "status": "ok", "truth_mm": 2.0, "reading_mm": 2.2}, 0.02),
        normalize_row({"image": "c.jpg", "status": "failed", "truth_mm": 3.0, "error": "boom"}, 0.02),
    ]
    summary = build_summary(rows)
    assert summary["count_total"] == 3
    assert summary["count_success"] == 2
    assert summary["count_failed"] == 1
    assert summary["within_0_02mm"] == 1
    assert summary["module_counts"]["pipeline"] == 1


def test_write_csv_uses_utf8_sig_and_fixed_header(tmp_path):
    path = tmp_path / "evaluation.csv"
    rows = [normalize_row({"image": "100.00.jpg", "status": "ok", "truth_mm": 100.0, "reading_mm": 100.0}, 0.02)]
    write_csv(path, rows)
    data = path.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    assert text.splitlines()[0].split(",")[:3] == list(FIELDNAMES[:3])
    assert "100.00.jpg" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: FAIL because `FIELDNAMES`, `build_summary`, and `write_csv` are missing.

- [ ] **Step 3: Implement summary and CSV**

Use `csv.DictWriter` with `encoding="utf-8-sig"` and `extrasaction="ignore"`. Summary computes counts from normalized rows and ignores failed rows for numeric error means.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: PASS.

### Task 4: Minimal XLSX Export

**Files:**
- Modify: `tools/batch_evaluation_report.py`
- Modify: `tests/test_batch_evaluation_report.py`

**Interfaces:**
- Produces: `write_xlsx(path: Path, rows: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> None`

- [ ] **Step 1: Write failing test**

```python
import zipfile

from tools.batch_evaluation_report import build_summary, write_xlsx


def test_write_xlsx_contains_rows_and_summary_sheets(tmp_path):
    path = tmp_path / "evaluation.xlsx"
    rows = [normalize_row({"image": "100.00.jpg", "status": "ok", "truth_mm": 100.0, "reading_mm": 100.0}, 0.02)]
    write_xlsx(path, rows, build_summary(rows))

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert "xl/workbook.xml" in names
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet2.xml" in names
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        assert 'name="summary"' in workbook
        assert 'name="rows"' in workbook
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: FAIL because `write_xlsx` is missing.

- [ ] **Step 3: Implement XLSX writer**

Implement a standard-library writer using `zipfile.ZipFile`, XML escaping, inline strings, numeric cells, workbook relationships, and two worksheets:

- `summary`: key/value rows, status counts, module counts.
- `rows`: `FIELDNAMES` header plus normalized row values.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: PASS.

### Task 5: Integrate Existing Batch Pipeline

**Files:**
- Modify: `tools/evaluate_all_pipeline.py`
- Modify: `tests/test_batch_evaluation_report.py`

**Interfaces:**
- Produces: CLI arguments `--input-dir`, `--output-dir`, `--tolerance`
- Consumes: helper functions from `tools.batch_evaluation_report`

- [ ] **Step 1: Write failing tests for non-image orchestration**

```python
from tools.batch_evaluation_report import build_report


def test_build_report_returns_rows_and_summary(tmp_path):
    rows = [
        normalize_row({"image": "100.00.jpg", "status": "ok", "truth_mm": 100.0, "reading_mm": 100.0}, 0.02),
    ]
    report = build_report(rows, input_dir=tmp_path, tolerance=0.02)
    assert report["summary"]["count_total"] == 1
    assert report["summary"]["input_dir"] == str(tmp_path)
    assert report["rows"][0]["image"] == "100.00.jpg"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: FAIL because `build_report` is missing.

- [ ] **Step 3: Implement report packaging and integrate CLI**

In `tools/evaluate_all_pipeline.py`:

- Parse CLI arguments with `argparse`.
- Default `--input-dir` to `ROOT / "tupian"`.
- Default `--output-dir` to `ROOT / "debug_tupian_batch_evaluation_20260806"`.
- Default `--tolerance` to `0.02`.
- For each image, run existing `CaliperPipeline(fast_mode=True)`.
- Build a raw row with pipeline diagnostics.
- Call `normalize_row(raw_row, tolerance)`.
- Write JSON, CSV, and XLSX through helper functions.

- [ ] **Step 4: Run unit tests**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: PASS.

### Task 6: Integration Run on `tupian/`

**Files:**
- No code changes expected after this task unless tests expose a defect.
- Output: `debug_tupian_batch_evaluation_20260806/evaluation.json`
- Output: `debug_tupian_batch_evaluation_20260806/evaluation.csv`
- Output: `debug_tupian_batch_evaluation_20260806/evaluation.xlsx`

**Interfaces:**
- Consumes: `python tools/evaluate_all_pipeline.py --tolerance 0.02`
- Produces: batch result files for the paper experiment table.

- [ ] **Step 1: Run focused unit tests**

Run: `pytest tests/test_batch_evaluation_report.py -q`

Expected: PASS.

- [ ] **Step 2: Run relevant existing regression tests**

Run: `pytest tests/test_roi_candidate_selection.py tests/test_vernier_valley_regressions.py tests/test_vernier_top_stroke_split.py tests/test_vernier_per_tick_correction.py -q`

Expected: PASS.

- [ ] **Step 3: Run batch evaluation**

Run: `python tools/evaluate_all_pipeline.py --tolerance 0.02`

Expected:

- command completes;
- all `.jpg` files under `tupian/` appear in `evaluation.json`;
- CSV and XLSX files exist;
- summary reports count totals and module counts.

- [ ] **Step 4: Inspect generated files**

Run:

```powershell
python -c "import json; p='debug_tupian_batch_evaluation_20260806/evaluation.json'; d=json.load(open(p,encoding='utf-8')); print(d['summary']); print(len(d['rows']))"
```

Expected: printed summary and row count matching the number of input images.

### Task 7: Final Handoff

**Files:**
- Report generated files in `debug_tupian_batch_evaluation_20260806/`

**Interfaces:**
- Consumes: generated report files and test output.
- Produces: user-facing summary.

- [ ] **Step 1: Summarize output locations**

Report exact paths to:

- `evaluation.json`
- `evaluation.csv`
- `evaluation.xlsx`

- [ ] **Step 2: Summarize statistics**

Include:

- total image count;
- successful run count;
- failed run count;
- within `0.02` mm / `0.10` mm / `0.50` mm counts;
- largest-error examples;
- suspected module counts.

- [ ] **Step 3: Explain review workflow**

Tell the user to edit `error_module_final` and `error_notes` in the Excel rows after inspecting visualizations. Emphasize that `suspected_error_module` is an automatic hint, not the final paper label.

## Self-Review

- Spec coverage: JSON, CSV, XLSX, row fields, summary, suspected labels, human-review columns, tolerance, no production-code changes, and no filename influence on recognition are all covered by tasks.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: helper function names and row fields are consistent across tasks.
