"""Export diagnostics for current labelled readings whose error exceeds 0.50 mm."""

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
EVALUATION_PATH = ROOT / "debug_tupian_all_results_20260719" / "evaluation.json"
OUTPUT_DIR = ROOT / "debug_tupian_large_errors_current_20260723"
ERROR_THRESHOLD_MM = 0.50


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


def debug_image(debug_images: dict, prefix: str):
    return next(
        (image for key, image in debug_images.items() if key.startswith(prefix)),
        None,
    )


def roi_visual(image: np.ndarray, roi: dict) -> np.ndarray:
    visual = image.copy()
    x1, y1, x2, y2 = roi["roi_box_original"]
    cv2.rectangle(visual, (x1, y1), (x2, y2), (0, 255, 0), 5, cv2.LINE_AA)
    source = roi.get("roi_source", "unknown")
    cv2.putText(visual, source, (20, 45), cv2.FONT_HERSHEY_SIMPLEX,
                1.1, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(visual, source, (20, 45), cv2.FONT_HERSHEY_SIMPLEX,
                1.1, (255, 255, 255), 2, cv2.LINE_AA)
    return visual


def labelled(image: np.ndarray, text: str, width: int = 1000) -> np.ndarray:
    height = max(1, int(round(image.shape[0] * width / image.shape[1])))
    resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    header = np.full((46, width, 3), 250, dtype=np.uint8)
    cv2.putText(header, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.62, (20, 20, 20), 1, cv2.LINE_AA)
    return np.vstack((header, resized))


def main() -> None:
    evaluation = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    rows = [
        row for row in evaluation["rows"]
        if row.get("truth_mm") is not None and row["abs_error_mm"] > ERROR_THRESHOLD_MM
    ]
    rows.sort(key=lambda row: (-row["abs_error_mm"], row["image"]))
    OUTPUT_DIR.mkdir(exist_ok=True)
    overview_rows = []
    report = []

    for index, row in enumerate(rows, start=1):
        filename = row["image"]
        image = read_image(INPUT_DIR / filename)
        pipeline = CaliperPipeline(fast_mode=False)
        result = pipeline.run(image)
        main_result = pipeline.step_results.get("main", {})
        vernier_result = pipeline.step_results.get("vernier", {})
        split_result = pipeline.step_results.get("split", {})
        prefix = f"{index:02d}_{Path(filename).stem}"
        images = {
            "roi": roi_visual(image, pipeline.step_results["roi"]),
            "region_split": split_result.get("split_vis"),
            "main_ticks": main_result.get("vis_ticks"),
            "vernier_ticks": vernier_result.get("vis_ticks"),
            "vernier_valley": vernier_result.get("vis_valley"),
            "ocr": debug_image(result.debug_images, "3b_"),
            "final": result.image_annotated,
        }
        for suffix, visual in images.items():
            if visual is not None:
                write_image(OUTPUT_DIR / f"{prefix}_{suffix}.png", visual)

        title = (f"{filename} truth={row['truth_mm']:.2f} result={result.total:.2f} "
                 f"error={abs(result.total - row['truth_mm']):.2f}")
        overview_rows.append(labelled(result.image_annotated, title))
        report.append({
            "image": filename,
            "truth_mm": row["truth_mm"],
            "reading_mm": result.total,
            "abs_error_mm": abs(result.total - row["truth_mm"]),
            "roi_source": pipeline.step_results["roi"].get("roi_source"),
            "roi_recovery": result.extra_info.get("roi_recovery"),
            "main_tick_count": len(main_result.get("main_ticks", [])),
            "vernier_tick_count": len(vernier_result.get("vernier_ticks", [])),
            "ocr_reason": result.extra_info.get("main_derivation", {}).get("ocr_reason"),
        })

    write_image(OUTPUT_DIR / "contact_sheet.png", np.vstack(overview_rows))
    (OUTPUT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Exported {len(rows)} samples to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
