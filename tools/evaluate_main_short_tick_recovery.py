"""Evaluate main-scale short-tick recovery across the image dataset."""

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
from caliper.config import config


INPUT_DIR = ROOT / "tupian"
OUTPUT_DIR = ROOT / "debug_tupian_main_short_tick_recovery_20260719"


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Unable to read {path}")
    return image


def run_pipeline(path: Path, recovery_enabled: bool) -> dict:
    previous = config.main_scale.short_tick_recovery_enabled
    config.main_scale.short_tick_recovery_enabled = recovery_enabled
    try:
        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(read_image(path))
    finally:
        config.main_scale.short_tick_recovery_enabled = previous
    main = pipeline.step_results.get("main", {})
    recovered = [
        {"x": int(tick["x"]), "length": int(tick["length"])}
        for tick in main.get("main_ticks", [])
        if tick.get("is_recovered_short", False)
    ]
    return {
        "reading_mm": result.total,
        "main_scale_mm": result.main_scale,
        "main_tick_count": len(main.get("main_ticks", [])),
        "recovered_short_ticks": recovered,
        "recovered_count": len(recovered),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    records = []
    for path in sorted(INPUT_DIR.glob("*.jpg")):
        try:
            without_recovery = run_pipeline(path, recovery_enabled=False)
            with_recovery = run_pipeline(path, recovery_enabled=True)
            records.append({
                "image": path.name,
                "without_recovery": without_recovery,
                "with_recovery": with_recovery,
                "reading_delta_mm": round(
                    with_recovery["reading_mm"] - without_recovery["reading_mm"], 4
                ),
                "main_tick_delta": (
                    with_recovery["main_tick_count"] -
                    without_recovery["main_tick_count"]
                ),
            })
        except Exception as exc:
            records.append({"image": path.name, "error": str(exc)})

    (OUTPUT_DIR / "evaluation.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for record in records:
        if record.get("main_tick_delta", 0) or record.get("reading_delta_mm", 0):
            print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
