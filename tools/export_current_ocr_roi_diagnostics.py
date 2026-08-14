"""Export current ROI, tick, and OCR diagnostics for selected failures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caliper.pipeline import CaliperPipeline


INPUT_DIR = ROOT / "tupian"
OUTPUT_DIR = ROOT / "debug_tupian_ocr_large_reading_errors_20260722"
SAMPLES = ("60.50.jpg", "70.00.jpg", "73.54.jpg", "110.00.jpg")


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
    return next((image for key, image in debug_images.items() if key.startswith(prefix)), None)


def roi_overlay(image: np.ndarray, roi: dict) -> np.ndarray:
    canvas = image.copy()
    x1, y1, x2, y2 = roi.get("roi_box_original", (0, 0, 0, 0))
    cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 0, 255), 8)
    cv2.putText(canvas, roi.get("roi_source", "unknown"), (x1, max(40, y1 - 18)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
    return canvas


def ocr_overlay(split: dict, main_scale: dict, vernier: dict, derivation: dict):
    region = split.get("region_main", {})
    image = region.get("image")
    if image is None:
        return None
    canvas = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    for tick in main_scale.get("main_ticks", []):
        cv2.line(canvas, (int(tick["x"]), int(tick["y_start"])),
                 (int(tick["x"]), int(tick["y_end"])), (0, 190, 0), 1)
    zero_x = float(vernier.get("zero_x", 0.0) or 0.0)
    if zero_x > 0:
        cv2.line(canvas, (int(round(zero_x)), 0),
                 (int(round(zero_x)), canvas.shape[0] - 1), (0, 220, 255), 2)
    crop = derivation.get("ocr_crop")
    if crop and len(crop) == 4:
        x, y, w, h = (int(value) for value in crop)
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (255, 180, 0), 2)
    for candidate in derivation.get("ocr_candidates", []):
        bbox = candidate.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = (int(value) for value in bbox)
        color = (0, 220, 0) if candidate.get("selected") else (0, 0, 255)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        cv2.putText(canvas, candidate.get("text", "?"), (x1, max(18, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
    return canvas


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = []
    for index, filename in enumerate(SAMPLES, start=1):
        image = read_image(INPUT_DIR / filename)
        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(image)
        roi = pipeline.step_results.get("roi", {})
        split = pipeline.step_results.get("split", {})
        main_scale = pipeline.step_results.get("main", {})
        vernier = pipeline.step_results.get("vernier", {})
        derivation = result.extra_info.get("main_derivation", {})
        prefix = f"{index:02d}_{Path(filename).stem}"

        images = {
            "roi": roi_overlay(image, roi),
            "region_split": split.get("split_vis"),
            "main_ticks": main_scale.get("vis_ticks"),
            "vernier_ticks": vernier.get("vis_ticks"),
            "ocr": ocr_overlay(split, main_scale, vernier, derivation),
            "reading": result.image_annotated,
        }
        for suffix, diagnostic in images.items():
            if diagnostic is not None:
                write_image(OUTPUT_DIR / f"{prefix}_{suffix}.png", diagnostic)

        report.append({
            "image": filename,
            "reading_mm": result.total,
            "main_scale_mm": result.main_scale,
            "vernier_scale_mm": result.vernier_scale,
            "roi_source": roi.get("roi_source"),
            "roi_box_original": roi.get("roi_box_original"),
            "roi_selection": roi.get("roi_selection"),
            "split_y": split.get("split_y"),
            "seam_source": split.get("seam_source"),
            "main_tick_count": len(main_scale.get("main_ticks", [])),
            "vernier_tick_count": len(vernier.get("vernier_ticks", [])),
            "zero_x": vernier.get("zero_x"),
            "ocr_strategy": derivation.get("strategy"),
            "ocr_reason": derivation.get("ocr_reason"),
            "ocr_text": derivation.get("ocr_text"),
            "ocr_candidates": derivation.get("ocr_candidates", []),
        })

    (OUTPUT_DIR / "diagnostics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"Exported {len(report)} diagnostics to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
