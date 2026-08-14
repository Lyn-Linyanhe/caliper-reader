"""Evaluate the fast pipeline across the dataset after region splitting."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caliper.pipeline import CaliperPipeline
from tools.batch_evaluation_report import (
    build_report,
    normalize_row,
    truth_for_path,
    write_csv,
    write_json,
    write_xlsx,
)


INPUT_DIR = ROOT / "tupian"
OUTPUT_DIR = ROOT / "debug_tupian_batch_evaluation_20260806"
# The current dataset uses the corrected reading in each filename.  Keep the
# argument in the evaluation API for explicit future corrections, but do not
# carry mappings for filenames that are no longer present in ``tupian``.
MANUAL_TRUTH_MM = {}


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Unable to read {path}")
    return image


def build_pipeline_row(path: Path, tolerance: float, visual_tolerance: float) -> dict:
    truth, filename_truth, truth_source = truth_for_path(path, MANUAL_TRUTH_MM)
    record = {
        "image": path.name,
        "truth_mm": truth,
        "filename_truth_mm": filename_truth,
        "truth_source": truth_source,
    }
    start = time.perf_counter()
    pipeline = CaliperPipeline(fast_mode=True)
    result = pipeline.run(read_image(path))
    main = pipeline.step_results.get("main", {})
    vernier = pipeline.step_results.get("vernier", {})
    split = pipeline.step_results.get("split", {})
    roi = pipeline.step_results.get("roi", {})
    derivation = result.extra_info.get("main_derivation", {})
    strategy = derivation.get("strategy")
    ocr_ok = strategy != "ocr_failed"
    pipeline_error = result.extra_info.get("error")
    record.update({
        "status": "failed" if pipeline_error else "ok",
        "error": pipeline_error or "",
        "elapsed_ms": round((time.perf_counter() - start) * 1000.0, 2),
        "reading_mm": None if pipeline_error else result.total,
        "split_y": split.get("split_y"),
        "seam_source": split.get("seam_source"),
        "roi_valid": bool(roi.get("roi_box_original")) if roi else None,
        "main_tick_count": len(main.get("main_ticks", [])),
        "vernier_tick_count": len(vernier.get("vernier_ticks", [])),
        "main_ocr_ok": ocr_ok,
        "main_ocr_reason": derivation.get("ocr_reason"),
        "main_ocr_text": derivation.get("ocr_text"),
        "main_ocr_confidence": derivation.get("ocr_confidence"),
        "main_scale_mm": None if pipeline_error else result.main_scale,
        "vernier_scale_mm": None if pipeline_error else result.vernier_scale,
        "zero_x": vernier.get("zero_x"),
        "alignment_confidence": vernier.get("alignment_confidence"),
    })
    return normalize_row(record, tolerance, visual_tolerance)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=INPUT_DIR,
        help="Directory containing labelled .jpg images.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory where evaluation.json/csv/xlsx are written.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.02,
        help="Strict offline grid-match tolerance in millimetres.",
    )
    parser.add_argument(
        "--visual-tolerance",
        type=float,
        default=0.10,
        help="Loose tolerance for paper/manual-review recognition-error counting.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rows = []
    for path in sorted(args.input_dir.glob("*.jpg")):
        try:
            record = build_pipeline_row(path, args.tolerance, args.visual_tolerance)
        except Exception as exc:
            truth, filename_truth, truth_source = truth_for_path(path, MANUAL_TRUTH_MM)
            record = normalize_row({
                "image": path.name,
                "truth_mm": truth,
                "filename_truth_mm": filename_truth,
                "truth_source": truth_source,
                "status": "failed",
                "error": str(exc),
            }, args.tolerance, args.visual_tolerance)
        rows.append(record)
        print(json.dumps(record, ensure_ascii=False))

    report = build_report(
        rows,
        input_dir=args.input_dir,
        tolerance=args.tolerance,
        visual_tolerance=args.visual_tolerance,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "evaluation.json", report)
    write_csv(args.output_dir / "evaluation.csv", rows)
    write_xlsx(args.output_dir / "evaluation.xlsx", rows, report["summary"])


if __name__ == "__main__":
    main()
