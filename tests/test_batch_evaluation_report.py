from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.batch_evaluation_report import (
    FIELDNAMES,
    build_report,
    build_summary,
    classify_suspected_error,
    is_within_tolerance,
    normalize_row,
    truth_for_path,
    truth_from_name,
    write_csv,
    write_xlsx,
)


def test_truth_from_numeric_filename():
    assert truth_from_name(Path("100.60.jpg")) == 100.60


def test_truth_from_numeric_filename_with_copy_suffix():
    assert truth_from_name(Path("70.94(1).jpg")) == 70.94


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
        {
            "image": "100.00.jpg",
            "truth_mm": 100.0,
            "reading_mm": 100.0,
            "status": "ok",
        },
        tolerance=0.02,
    )
    assert row["abs_error_mm"] == 0.0
    assert row["within_tolerance"] is True
    assert row["tolerance_mm"] == 0.02
    assert row["error_module_final"] == ""
    assert row["error_notes"] == ""


def test_summary_includes_requested_accuracy_bands_by_default():
    summary = build_summary(
        [
            normalize_row(
                {"image": "a.jpg", "truth_mm": 1.0, "reading_mm": 1.0, "status": "ok"},
                tolerance=0.02,
            )
        ]
    )
    for tolerance in (0.00, 0.02, 0.04, 0.06, 0.10, 0.50):
        assert f"within_{tolerance:.2f}mm".replace(".", "_") in summary


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


def test_split_starves_tick_regions_before_ocr_failure():
    row = normalize_row(
        {
            "status": "ok",
            "truth_mm": 40.2,
            "reading_mm": 0.0,
            "split_y": 573,
            "seam_source": "projection_valley",
            "main_ocr_ok": False,
            "zero_x": 0.0,
            "vernier_tick_count": 0,
            "main_tick_count": 11,
        },
        tolerance=0.02,
    )
    assert row["suspected_error_module"] == "region_split"
    assert "tick_region_starved" in row["diagnostic_flags"]


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


def test_small_visual_difference_is_not_counted_as_recognition_error():
    row = normalize_row(
        {
            "status": "ok",
            "truth_mm": 50.0,
            "reading_mm": 50.06,
            "main_ocr_ok": True,
            "zero_x": 100.0,
            "vernier_tick_count": 48,
            "main_tick_count": 35,
        },
        tolerance=0.02,
        visual_tolerance=0.10,
    )
    assert row["within_tolerance"] is False
    assert row["within_visual_tolerance"] is True
    assert row["visual_tolerance_mm"] == 0.10
    assert row["suspected_error_module"] == "none"
    assert "large_error" not in row["diagnostic_flags"]


def test_large_visual_difference_is_counted_as_recognition_error():
    row = normalize_row(
        {
            "status": "ok",
            "truth_mm": 50.0,
            "reading_mm": 50.20,
            "main_ocr_ok": True,
            "zero_x": 100.0,
            "vernier_tick_count": 48,
            "main_tick_count": 35,
        },
        tolerance=0.02,
        visual_tolerance=0.10,
    )
    assert row["within_tolerance"] is False
    assert row["within_visual_tolerance"] is False
    assert row["suspected_error_module"] == "reading_fusion"
    assert "large_error" in row["diagnostic_flags"]


def test_summary_counts_accuracy_and_modules():
    rows = [
        normalize_row(
            {
                "image": "a.jpg",
                "status": "ok",
                "truth_mm": 1.0,
                "reading_mm": 1.0,
            },
            0.02,
        ),
        normalize_row(
            {
                "image": "b.jpg",
                "status": "ok",
                "truth_mm": 2.0,
                "reading_mm": 2.2,
            },
            0.02,
        ),
        normalize_row(
            {
                "image": "c.jpg",
                "status": "failed",
                "truth_mm": 3.0,
                "error": "boom",
            },
            0.02,
        ),
    ]
    summary = build_summary(rows)
    assert summary["count_total"] == 3
    assert summary["count_success"] == 2
    assert summary["count_failed"] == 1
    assert summary["within_0_02mm"] == 1
    assert summary["within_0_10mm"] == 1
    assert summary["within_0_50mm"] == 2
    assert summary["module_counts"]["pipeline"] == 1


def test_write_csv_uses_utf8_sig_and_fixed_header(tmp_path):
    path = tmp_path / "evaluation.csv"
    rows = [
        normalize_row(
            {
                "image": "100.00.jpg",
                "status": "ok",
                "truth_mm": 100.0,
                "reading_mm": 100.0,
            },
            0.02,
        )
    ]
    write_csv(path, rows)
    data = path.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    assert text.splitlines()[0].split(",")[:3] == list(FIELDNAMES[:3])
    assert "100.00.jpg" in text


def test_write_xlsx_contains_rows_and_summary_sheets(tmp_path):
    path = tmp_path / "evaluation.xlsx"
    rows = [
        normalize_row(
            {
                "image": "100.00.jpg",
                "status": "ok",
                "truth_mm": 100.0,
                "reading_mm": 100.0,
            },
            0.02,
        )
    ]
    write_xlsx(path, rows, build_summary(rows))

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert "xl/workbook.xml" in names
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet2.xml" in names
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        assert 'name="summary"' in workbook
        assert 'name="rows"' in workbook


def test_build_report_returns_rows_and_summary(tmp_path):
    rows = [
        normalize_row(
            {
                "image": "100.00.jpg",
                "status": "ok",
                "truth_mm": 100.0,
                "reading_mm": 100.0,
            },
            0.02,
        )
    ]
    report = build_report(rows, input_dir=tmp_path, tolerance=0.02)
    assert report["summary"]["count_total"] == 1
    assert report["summary"]["input_dir"] == str(tmp_path)
    assert report["rows"][0]["image"] == "100.00.jpg"
