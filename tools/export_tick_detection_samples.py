"""Export representative main and vernier tick-detection visualizations."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caliper.pipeline import CaliperPipeline


INPUT_DIR = ROOT / "tupian"
OUTPUT_DIR = ROOT / "debug_tupian_tick_detection_large_reading_errors_20260722"
SAMPLES = [
    "60.50.jpg",
    "70.00.jpg",
    "73.54.jpg",
    "110.00.jpg",
]


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


def labeled(image: np.ndarray, title: str) -> np.ndarray:
    h, w = image.shape[:2]
    target_w = 920
    target_h = max(1, int(round(h * target_w / w)))
    resized = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_AREA)
    header = np.full((40, target_w, 3), 250, dtype=np.uint8)
    cv2.putText(header, title, (10, 28), cv2.FONT_HERSHEY_SIMPLEX,
                0.70, (20, 20, 20), 2, cv2.LINE_AA)
    return np.vstack((header, resized))


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    rows = []
    for number, filename in enumerate(SAMPLES, start=1):
        pipeline = CaliperPipeline(fast_mode=False)
        result = pipeline.run(read_image(INPUT_DIR / filename))
        split = pipeline.step_results.get("split", {})
        main_result = pipeline.step_results.get("main", {})
        vernier_result = pipeline.step_results.get("vernier", {})
        prefix = f"{number:02d}_{Path(filename).stem}"

        split_vis = split.get("split_vis")
        main_vis = main_result.get("vis_ticks")
        vernier_vis = vernier_result.get("vis_ticks")
        if split_vis is not None:
            write_image(OUTPUT_DIR / f"{prefix}_region_split.png", split_vis)
        if main_vis is not None:
            write_image(OUTPUT_DIR / f"{prefix}_main_ticks.png", main_vis)
        if vernier_vis is not None:
            write_image(OUTPUT_DIR / f"{prefix}_vernier_ticks.png", vernier_vis)

        panels = []
        if main_vis is not None:
            panels.append(labeled(main_vis, f"{prefix}  main ticks: {len(main_result.get('main_ticks', []))}"))
        if vernier_vis is not None:
            panels.append(labeled(vernier_vis, f"{prefix}  vernier ticks: {len(vernier_result.get('vernier_ticks', []))}"))
        if panels:
            width = max(panel.shape[1] for panel in panels)
            aligned = []
            for panel in panels:
                if panel.shape[1] != width:
                    panel = cv2.resize(panel, (width, int(round(panel.shape[0] * width / panel.shape[1]))),
                                       interpolation=cv2.INTER_AREA)
                aligned.append(panel)
            rows.append(np.vstack(aligned))
        print(f"{filename}: result={result.total:.2f}, main={len(main_result.get('main_ticks', []))}, "
              f"vernier={len(vernier_result.get('vernier_ticks', []))}")

    if rows:
        max_width = max(row.shape[1] for row in rows)
        padded = []
        for row in rows:
            if row.shape[1] < max_width:
                row = np.hstack((row, np.full((row.shape[0], max_width - row.shape[1], 3), 238, dtype=np.uint8)))
            padded.append(row)
        write_image(OUTPUT_DIR / "contact_sheet.png", np.vstack(padded))


if __name__ == "__main__":
    main()
