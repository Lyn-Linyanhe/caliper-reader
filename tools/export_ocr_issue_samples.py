"""Export representative OCR diagnostics for the caliper dataset."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caliper.pipeline import CaliperPipeline
from caliper.main_scale import (
    _find_threshold_segments,
    find_digit_cc_candidates,
    find_nearest_cm_digit_region,
)
from caliper.ocr import get_ocr_reader_singleton
from caliper.utils import _tick_row_threshold, contiguous_segments


INPUT_DIR = ROOT / "tupian"
OUTPUT_DIR = ROOT / "debug_tupian_ocr_issues_20260718"
SAMPLES = [
    "100.00.jpg",  # High-confidence truncated label: 1 -> 11 mm.
    "14.80.jpg",   # OCR reads the visible 14; the zero anchor selected the wrong area.
    "40.30.jpg",   # OCR reads the visible 9; the zero anchor selected the wrong area.
    "38.30.jpg",   # OCR reads 3 correctly, but the zero/tick geometry gives 30 mm.
    "120.60.jpg",  # No digit connected component.
    "73.54.jpg",   # No digit connected component near zero.
    "80.70.jpg",   # OCR candidate is not left of the zero line.
    "100.60.jpg",  # Missing zero line, so OCR has no anchor input.
    "72.52.jpg",   # OCR digit is usable, but main tick count is off by 1 mm.
]

DIAGNOSES = {
    "100.00.jpg": "template_multidigit_truncation",
    "14.80.jpg": "ocr_and_zero_anchor_are_consistent",
    "40.30.jpg": "roi_caused_wrong_zero_anchor",
    "38.30.jpg": "wrong_zero_or_tick_geometry",
    "120.60.jpg": "expanded_retry_then_multidigit_gap_rejected",
    "73.54.jpg": "zero_anchor_at_left_edge",
    "80.70.jpg": "zero_anchor_side_filter_rejected_candidate",
    "100.60.jpg": "roi_caused_missing_zero_anchor",
    "72.52.jpg": "vernier_zero_slightly_left",
}


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Unable to read {path}")
    return image


def write_image(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"Unable to encode {path}")
    encoded.tofile(str(path))


def get_debug_image(debug_images: dict, prefix: str):
    for key, image in debug_images.items():
        if key.startswith(prefix):
            return image
    return None


def labeled(image: np.ndarray, title: str, target_w: int = 1100) -> np.ndarray:
    h, w = image.shape[:2]
    target_h = max(1, int(round(h * target_w / w)))
    resized = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_AREA)
    header = np.full((44, target_w, 3), 250, dtype=np.uint8)
    cv2.putText(header, title, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.65, (20, 20, 20), 2, cv2.LINE_AA)
    return np.vstack((header, resized))


def export_cc_diagnostic(pipeline: CaliperPipeline, prefix: str) -> None:
    split = pipeline.step_results["split"]
    main_result = pipeline.step_results["main"]
    vernier_result = pipeline.step_results["vernier"]
    region_main = split["region_main"]
    binary_crop, x_offset, y_offset = find_nearest_cm_digit_region(
        main_result["main_ticks"],
        main_result["main_gap"],
        vernier_result["zero_x"],
        region_main["binary"],
    )
    if binary_crop is None or binary_crop.size == 0:
        return

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(
        binary_crop, connectivity=8
    )
    height, width = binary_crop.shape
    effective_min_area = min(700, max(250, int(height * height * 0.09)))
    dynamic_max_area = max(3000, int(height * height * 0.20))
    rows = []
    for label in range(1, num_labels):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        w = int(stats[label, cv2.CC_STAT_WIDTH])
        h = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        aspect = h / max(w, 1)
        if area < effective_min_area:
            verdict = "area_too_small"
        elif area > dynamic_max_area:
            verdict = "area_too_large"
        elif w < 3 or h < 5:
            verdict = "size_too_small"
        elif aspect < 0.6:
            verdict = "aspect_too_wide"
        elif aspect > 3.5:
            verdict = "aspect_too_tall"
        else:
            verdict = "accepted"
        rows.append({
            "label": label,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "area": area,
            "aspect": round(aspect, 3),
            "verdict": verdict,
        })

    overlay = cv2.cvtColor(binary_crop, cv2.COLOR_GRAY2BGR)
    largest = sorted(rows, key=lambda row: row["area"], reverse=True)[:20]
    for row in largest:
        color = (40, 220, 40) if row["verdict"] == "accepted" else (40, 40, 255)
        x, y, w, h = row["x"], row["y"], row["w"], row["h"]
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
        cv2.putText(overlay, str(row["label"]), (x, max(12, y - 3)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)

    target_w = 1200
    target_h = max(1, int(round(overlay.shape[0] * target_w / overlay.shape[1])))
    overlay = cv2.resize(overlay, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
    table_h = 72 + 24 * len(largest)
    table = np.full((table_h, target_w, 3), 245, dtype=np.uint8)
    cv2.putText(
        table,
        f"crop={width}x{height} area=[{effective_min_area},{dynamic_max_area}] red=rejected green=accepted",
        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (20, 20, 20), 1, cv2.LINE_AA,
    )
    cv2.putText(table, "id    x    y    w    h    area  aspect  verdict", (10, 52),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (20, 20, 20), 1, cv2.LINE_AA)
    for index, row in enumerate(largest):
        line = (f"{row['label']:2d} {row['x']:4d} {row['y']:4d} {row['w']:4d} "
                f"{row['h']:4d} {row['area']:6d} {row['aspect']:6.2f}  {row['verdict']}")
        cv2.putText(table, line, (10, 76 + index * 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (20, 20, 20), 1, cv2.LINE_AA)
    write_image(OUTPUT_DIR / f"{prefix}_cc_filter.png", np.vstack((overlay, table)))
    (OUTPUT_DIR / f"{prefix}_cc_stats.json").write_text(
        json.dumps({
            "crop_shape": [height, width],
            "x_offset": x_offset,
            "y_offset": y_offset,
            "effective_min_area": effective_min_area,
            "dynamic_max_area": dynamic_max_area,
            "components": rows,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_label_tick_binding(pipeline: CaliperPipeline, prefix: str) -> None:
    split = pipeline.step_results["split"]
    main_result = pipeline.step_results["main"]
    vernier_result = pipeline.step_results["vernier"]
    region_main = split["region_main"]
    main_color = pipeline.step_results["orient"]["rotated_color"][:split["split_y"], :].copy()
    main_ticks = main_result["main_ticks"]
    main_gap = float(main_result["main_gap"])
    zero_x = float(vernier_result["zero_x"])
    crop, x_offset, y_offset = find_nearest_cm_digit_region(
        main_ticks, main_gap, zero_x, region_main["binary"],
        vertical_expand_gaps=1.0,
    )
    if crop is None or not main_ticks:
        return

    reader = get_ocr_reader_singleton()
    chars = []
    for cc in find_digit_cc_candidates(crop, x_offset, y_offset, zero_x):
        digit = reader.ocr_patch_to_digit(cc["digit_crop"], cc["bbox"], region_main["image"])
        if digit is not None:
            chars.append((digit, cc))
    chars.sort(key=lambda item: item[1]["bbox"][0])
    pair = None
    for left, right in zip(chars, chars[1:]):
        if left[0].text == "1" and right[0].text in {"0", "1", "2", "3", "4", "5"}:
            gap = right[1]["bbox"][0] - left[1]["bbox"][2]
            if gap <= main_gap * 0.55:
                pair = (left, right)
    if pair is None:
        return

    left, right = pair
    x1 = left[1]["bbox"][0]
    y1 = min(left[1]["bbox"][1], right[1]["bbox"][1])
    x2 = right[1]["bbox"][2]
    y2 = max(left[1]["bbox"][3], right[1]["bbox"][3])
    center_x = (x1 + x2) / 2.0
    nearest_tick = min(main_ticks, key=lambda tick: abs(float(tick["x"]) - center_x))
    first_tick = min(main_ticks, key=lambda tick: abs(float(tick["x"]) - left[1]["center_x"]))

    view_x1 = max(0, int(x1 - 6 * main_gap))
    view_x2 = min(main_color.shape[1], int(x2 + 4 * main_gap))
    view_y1 = max(0, int(y1 - 80))
    view_y2 = min(main_color.shape[0], int(max(t["y_end"] for t in main_ticks) + 20))
    canvas = main_color.copy()
    for tick in main_ticks:
        tx = int(tick["x"])
        if view_x1 <= tx <= view_x2:
            cv2.line(canvas, (tx, int(tick["y_start"])), (tx, int(tick["y_end"])),
                     (0, 220, 60), 2)

    base_x = int(first_tick["x"])
    for expected_x in range(base_x - int(2 * main_gap), base_x + int(5 * main_gap), int(round(main_gap))):
        if view_x1 <= expected_x <= view_x2:
            cv2.line(canvas, (expected_x, view_y1), (expected_x, view_y2),
                     (220, 70, 220), 1, cv2.LINE_AA)

    cv2.line(canvas, (int(zero_x), view_y1), (int(zero_x), view_y2), (0, 255, 255), 2)
    cv2.rectangle(canvas, (x1, y1), (x2, y2), (255, 120, 0), 2)
    cv2.line(canvas, (int(round(center_x)), view_y1), (int(round(center_x)), view_y2),
             (255, 120, 0), 2)
    cv2.line(canvas, (int(first_tick["x"]), view_y1), (int(first_tick["x"]), view_y2),
             (0, 80, 255), 2)
    cv2.putText(canvas, f"combined center={center_x:.0f}", (int(center_x) + 5, view_y1 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 120, 0), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"nearest detected tick={nearest_tick['x']} dist={abs(center_x - nearest_tick['x']):.0f}px",
                (view_x1 + 5, view_y1 + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.46,
                (0, 80, 255), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"main_gap={main_gap:.0f}px  yellow=zero  green=detected  purple=expected grid",
                (view_x1 + 5, view_y1 + 64), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                (30, 30, 30), 1, cv2.LINE_AA)
    cropped = canvas[view_y1:view_y2, view_x1:view_x2]
    write_image(OUTPUT_DIR / f"{prefix}_label_tick_binding.png", labeled(
        cropped,
        "120.60 label-to-tick binding: blue=combined '12' center, orange=nearest detected tick",
        target_w=1400,
    ))


def export_main_tick_diagnostic(pipeline: CaliperPipeline, prefix: str) -> None:
    split = pipeline.step_results["split"]
    main_result = pipeline.step_results["main"]
    binary = split["region_main"]["binary"]
    band_y1, band_y2 = split["region_main"]["tick_band"]
    band = binary[band_y1:band_y2, :]
    projection = np.sum(band > 0, axis=0).astype(float)
    norm = projection / np.max(projection) if np.max(projection) > 0 else projection
    coarse_xs = _find_threshold_segments(norm, threshold_factor=0.20)
    min_length = max(6, int(band.shape[0] * 0.25))
    final_xs = [int(tick["x"]) for tick in main_result["main_ticks"]]
    rows = []
    for x in coarse_xs:
        if not 1150 <= int(x) <= 1650:
            continue
        col = np.sum(band[:, max(0, x - 3):min(band.shape[1], x + 4)], axis=1)
        threshold = _tick_row_threshold(col)
        indices = np.where(col > threshold)[0]
        segments = contiguous_segments(indices, min_len=5)
        longest = max((end - begin for begin, end in segments), default=0)
        if len(indices) < min_length // 2:
            verdict = "rejected_insufficient_foreground"
        elif not segments:
            verdict = "rejected_no_contiguous_segment"
        elif longest < min_length:
            verdict = "rejected_short_vertical_segment"
        else:
            verdict = "passes_vertical_length_filter"
        rows.append({
            "x": int(x),
            "projection": round(float(norm[int(x)]), 3),
            "foreground_rows": int(len(indices)),
            "longest_vertical_segment": int(longest),
            "min_required_length": int(min_length),
            "verdict": verdict,
            "in_final_main_ticks": any(abs(final_x - int(x)) <= 4 for final_x in final_xs),
        })
    (OUTPUT_DIR / f"{prefix}_main_tick_diagnostics.json").write_text(
        json.dumps({
            "tick_band": [int(band_y1), int(band_y2)],
            "main_gap": main_result["main_gap"],
            "candidates": rows,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    records = []
    page_rows = []
    page_number = 1

    for number, filename in enumerate(SAMPLES, start=1):
        truth = float(Path(filename).stem)
        pipeline = CaliperPipeline(fast_mode=False)
        result = pipeline.run(read_image(INPUT_DIR / filename))
        derivation = result.extra_info.get("main_derivation", {})
        ocr_vis = get_debug_image(result.debug_images, "3b_")
        derivation_vis = get_debug_image(result.debug_images, "5b_")
        main_tick_vis = pipeline.step_results.get("main", {}).get("vis_ticks")
        prefix = f"{number:02d}_{Path(filename).stem}"

        if main_tick_vis is not None:
            write_image(OUTPUT_DIR / f"{prefix}_main_ticks_current.png", main_tick_vis)
        if ocr_vis is not None:
            write_image(OUTPUT_DIR / f"{prefix}_ocr.png", ocr_vis)
        if derivation_vis is not None:
            write_image(OUTPUT_DIR / f"{prefix}_reading_derivation.png", derivation_vis)

        record = {
            "image": filename,
            "truth_mm": truth,
            "expected_main_mm": math.floor(truth),
            "reading_mm": result.total,
            "main_scale_mm": result.main_scale,
            "vernier_scale_mm": result.vernier_scale,
            "ocr_status": derivation.get("strategy"),
            "ocr_reason": derivation.get("ocr_reason"),
            "ocr_text": derivation.get("ocr_text"),
            "ocr_confidence": derivation.get("ocr_confidence"),
            "zero_x": result.extra_info.get("zero_x"),
            "diagnosis": DIAGNOSES[filename],
        }
        records.append(record)

        if filename == "120.60.jpg":
            export_cc_diagnostic(pipeline, prefix)
            export_label_tick_binding(pipeline, prefix)
            export_main_tick_diagnostic(pipeline, prefix)

        if ocr_vis is not None:
            text = derivation.get("ocr_text") or "NONE"
            reason = derivation.get("ocr_reason") or "selected"
            title = (f"{prefix} truth={truth:.2f} OCR={text} main={result.main_scale:.0f} "
                     f"reason={reason} diagnosis={DIAGNOSES[filename]}")
            page_rows.append(labeled(ocr_vis, title))

        if len(page_rows) == 3 or number == len(SAMPLES):
            if page_rows:
                write_image(OUTPUT_DIR / f"contact_sheet_{page_number:02d}.png",
                            np.vstack(page_rows))
                page_rows.clear()
                page_number += 1

        print(json.dumps(record, ensure_ascii=False))

    (OUTPUT_DIR / "ocr_evaluation.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
