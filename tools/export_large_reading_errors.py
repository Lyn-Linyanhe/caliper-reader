"""Export visual diagnostics for current full-reading errors above 0.10 mm."""

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
EVALUATION_PATH = ROOT / "debug_tupian_main_short_tick_recovery_20260719" / "evaluation.json"
OUTPUT_DIR = ROOT / "debug_tupian_large_reading_errors_20260719"
ERROR_THRESHOLD_MM = 0.10
MANUAL_TRUTH_MM = {
    "14.80.jpg": 140.80,
    "33.00.jpg": 30.30,
    "38.30.jpg": 30.84,
}

CATEGORIES = {
    "100.60.jpg": "ROI/zero anchor missing",
    "11.00.jpg": "ROI/zero anchor missing",
    "30.00.jpg": "ROI/zero anchor missing",
    "33.00.jpg": "ROI/zero anchor missing",
    "40.20.jpg": "ROI/zero anchor missing",
    "60.96.jpg": "ROI/zero anchor missing",
    "80.80.jpg": "ROI/zero anchor missing",
    "80.90.jpg": "ROI/zero anchor missing",
    "40.30.jpg": "ROI/zero anchor misplaced",
    "72.52.jpg": "vernier zero offset",
    "74.56.jpg": "main-scale tick geometry",
    "38.30.jpg": "main-scale tick geometry",
    "73.54.jpg": "OCR crop/anchor failure",
    "80.70.jpg": "OCR candidate-side failure",
    "130.70.jpg": "OCR crop/anchor failure",
    "14.80.jpg": "filename/unit needs review",
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


def labeled(image: np.ndarray, title: str, target_width: int = 960) -> np.ndarray:
    h, w = image.shape[:2]
    target_height = max(1, int(round(h * target_width / w)))
    resized = cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)
    header = np.full((44, target_width, 3), 250, dtype=np.uint8)
    cv2.putText(header, title, (10, 29), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (20, 20, 20), 1, cv2.LINE_AA)
    return np.vstack((header, resized))


def numeric_error(record: dict) -> tuple[float | None, float | None]:
    try:
        truth = MANUAL_TRUTH_MM.get(
            record["image"], float(Path(record["image"]).stem)
        )
    except ValueError:
        return None, None
    reading = float(record["with_recovery"]["reading_mm"])
    return truth, abs(reading - truth)


def main() -> None:
    records = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    errors = []
    for record in records:
        truth, error = numeric_error(record)
        if truth is not None and error is not None and error > ERROR_THRESHOLD_MM:
            errors.append((record, truth, error))
    errors.sort(key=lambda item: (-item[2], item[0]["image"]))

    OUTPUT_DIR.mkdir(exist_ok=True)
    report = []
    page_rows = []
    page_number = 1

    for number, (record, truth, error) in enumerate(errors, start=1):
        filename = record["image"]
        pipeline = CaliperPipeline(fast_mode=False)
        result = pipeline.run(read_image(INPUT_DIR / filename))
        main = pipeline.step_results.get("main", {})
        vernier = pipeline.step_results.get("vernier", {})
        split = pipeline.step_results.get("split", {})
        derivation = result.extra_info.get("main_derivation", {})
        prefix = f"{number:02d}_{Path(filename).stem}"

        images = {
            "region_split": split.get("split_vis"),
            "main_ticks": main.get("vis_ticks"),
            "vernier_ticks": vernier.get("vis_ticks"),
            "ocr": get_debug_image(result.debug_images, "3b_"),
            "final": result.image_annotated,
        }
        for suffix, image in images.items():
            if image is not None:
                write_image(OUTPUT_DIR / f"{prefix}_{suffix}.png", image)

        category = CATEGORIES.get(filename, "needs review")
        report.append({
            "image": filename,
            "truth_mm": truth,
            "reading_mm": result.total,
            "abs_error_mm": error,
            "category": category,
            "main_scale_mm": result.main_scale,
            "vernier_scale_mm": result.vernier_scale,
            "main_tick_count": len(main.get("main_ticks", [])),
            "vernier_tick_count": len(vernier.get("vernier_ticks", [])),
            "ocr_text": derivation.get("ocr_text"),
            "ocr_reason": derivation.get("ocr_reason"),
        })

        title = (f"{prefix} truth={truth:.2f} result={result.total:.2f} "
                 f"error={error:.2f} {category}")
        page_rows.append(labeled(result.image_annotated, title))
        if len(page_rows) == 4 or number == len(errors):
            write_image(OUTPUT_DIR / f"contact_sheet_{page_number:02d}.png", np.vstack(page_rows))
            page_rows.clear()
            page_number += 1

    (OUTPUT_DIR / "error_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Exported {len(report)} large-error samples to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
