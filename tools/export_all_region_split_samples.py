"""Export current region-split diagnostics for all usable dataset images."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caliper.config import config
from caliper.preprocess import preprocess
from caliper.region_split import split_scales
from caliper.roi_extract import locate_roi_lowres, orient_caliper


INPUT_DIR = ROOT / "tupian"
OUTPUT_DIR = ROOT / "debug_tupian_region_split_all"
EXCLUDED = {"40.20.jpg"}
PAGE_SIZE = 12


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


def make_contact_sheet(images: list[np.ndarray], labels: list[str]) -> np.ndarray:
    tiles = []
    for image, label in zip(images, labels):
        h, w = image.shape[:2]
        target_w = 820
        target_h = max(1, int(round(h * target_w / w)))
        tile = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_AREA)
        header = np.full((38, target_w, 3), 250, dtype=np.uint8)
        cv2.putText(header, label, (10, 27), cv2.FONT_HERSHEY_SIMPLEX,
                    0.68, (20, 20, 20), 2, cv2.LINE_AA)
        tiles.append(np.vstack((header, tile)))

    rows = []
    for index in range(0, len(tiles), 2):
        pair = tiles[index:index + 2]
        if len(pair) == 1:
            pair.append(np.full_like(pair[0], 238))
        height = max(tile.shape[0] for tile in pair)
        aligned = []
        for tile in pair:
            if tile.shape[0] < height:
                tile = np.vstack((tile, np.full((height - tile.shape[0], tile.shape[1], 3), 238, dtype=np.uint8)))
            aligned.append(tile)
        rows.append(np.hstack((aligned[0], np.full((height, 12, 3), 35, dtype=np.uint8), aligned[1])))
    return np.vstack(rows)


def run_split(source: np.ndarray, params: dict) -> tuple[dict, dict, dict]:
    roi = locate_roi_lowres(source)
    if roi.get("roi_color") is None:
        raise RuntimeError("ROI localization failed")
    processed = preprocess(roi["roi_color"], make_debug=False, **params)
    oriented = orient_caliper(
        processed["color"], processed["enhanced"], processed["binary_adaptive"],
        make_debug=False,
    )
    split = split_scales(
        oriented["rotated_gray"], oriented["rotated_binary"],
        oriented["rotated_color"], make_debug=True,
    )
    return roi, oriented, split


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    filenames = [path.name for path in sorted(INPUT_DIR.glob("*.jpg")) if path.name not in EXCLUDED]
    params = {
        "clip_limit": config.preprocess.clahe_clip_limit,
        "bilateral_d": config.preprocess.bilateral_d,
        "bilateral_sigma": config.preprocess.bilateral_sigma,
        "gamma": config.preprocess.gamma,
        "median_ksize": config.preprocess.median_ksize,
    }
    summaries = []
    page_images = []
    page_labels = []
    page_number = 1

    for number, filename in enumerate(filenames, start=1):
        path = INPUT_DIR / filename
        entry = {"image": filename}
        try:
            roi, oriented, split = run_split(read_image(path), params)
            out_name = f"{number:02d}_{path.stem}_region_split.png"
            write_image(OUTPUT_DIR / out_name, split["split_vis"])
            bands = split.get("tick_bands", {})
            entry.update({
                "status": "ok",
                "roi_box_original": roi.get("roi_box_original"),
                "orientation_angle": oriented.get("orient_angle"),
                "split_y": split.get("split_y"),
                "seam_source": split.get("seam_source"),
                "main_tick_band": bands.get("main_tick_band"),
                "vernier_tick_band": bands.get("vernier_tick_band"),
                "visualization": out_name,
            })
            page_images.append(split["split_vis"])
            page_labels.append(f"{number:02d}  {path.stem}")
        except Exception as exc:
            entry.update({"status": "failed", "error": str(exc)})
        summaries.append(entry)
        print(json.dumps(entry, ensure_ascii=False))

        if len(page_images) == PAGE_SIZE or number == len(filenames):
            sheet_name = f"contact_sheet_{page_number:02d}.png"
            write_image(OUTPUT_DIR / sheet_name, make_contact_sheet(page_images, page_labels))
            page_images.clear()
            page_labels.clear()
            page_number += 1

    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
