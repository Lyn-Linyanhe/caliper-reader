"""Export all samples whose vernier tick count is below the expected range."""

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
EVALUATION_PATH = ROOT / "debug_tupian_region_split_all" / "pipeline_evaluation.json"
OUTPUT_DIR = ROOT / "debug_tupian_vernier_issues"
PAGE_SIZE = 3


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


def labeled(image: np.ndarray, title: str, target_w: int = 880) -> np.ndarray:
    h, w = image.shape[:2]
    target_h = max(1, int(round(h * target_w / w)))
    resized = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_AREA)
    header = np.full((38, target_w, 3), 250, dtype=np.uint8)
    cv2.putText(header, title, (10, 27), cv2.FONT_HERSHEY_SIMPLEX,
                0.68, (20, 20, 20), 2, cv2.LINE_AA)
    return np.vstack((header, resized))


def main() -> None:
    records = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    issues = [record for record in records
              if record.get("truth_mm") is not None and record.get("vernier_tick_count", 0) < 48]
    OUTPUT_DIR.mkdir(exist_ok=True)
    page_rows = []
    page_number = 1

    for number, record in enumerate(issues, start=1):
        filename = record["image"]
        pipeline = CaliperPipeline(fast_mode=False)
        pipeline.run(read_image(INPUT_DIR / filename))
        split = pipeline.step_results.get("split", {})
        main = pipeline.step_results.get("main", {})
        vernier = pipeline.step_results.get("vernier", {})
        prefix = f"{number:02d}_{Path(filename).stem}"
        split_vis = split.get("split_vis")
        main_vis = main.get("vis_ticks")
        vernier_vis = vernier.get("vis_ticks")

        if split_vis is not None:
            write_image(OUTPUT_DIR / f"{prefix}_region_split.png", split_vis)
        if main_vis is not None:
            write_image(OUTPUT_DIR / f"{prefix}_main_ticks.png", main_vis)
        if vernier_vis is not None:
            write_image(OUTPUT_DIR / f"{prefix}_vernier_ticks.png", vernier_vis)

        panels = []
        if split_vis is not None:
            panels.append(labeled(split_vis, f"{prefix}  split={split.get('split_y')}, vernier={len(vernier.get('vernier_ticks', []))}"))
        if vernier_vis is not None:
            panels.append(labeled(vernier_vis, f"{prefix}  vernier ticks"))
        if panels:
            width = max(panel.shape[1] for panel in panels)
            aligned = []
            for panel in panels:
                if panel.shape[1] != width:
                    panel = cv2.resize(panel, (width, int(round(panel.shape[0] * width / panel.shape[1]))),
                                       interpolation=cv2.INTER_AREA)
                aligned.append(panel)
            page_rows.append(np.vstack(aligned))

        if len(page_rows) == PAGE_SIZE or number == len(issues):
            write_image(OUTPUT_DIR / f"contact_sheet_{page_number:02d}.png", np.vstack(page_rows))
            page_rows.clear()
            page_number += 1
        print(f"{filename}: vernier={len(vernier.get('vernier_ticks', []))}")


if __name__ == "__main__":
    main()
