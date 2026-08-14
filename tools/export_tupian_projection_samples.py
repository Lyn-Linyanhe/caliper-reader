"""Export region-split projection diagnostics for representative dataset images."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from caliper.config import config
from caliper.preprocess import preprocess
from caliper.region_split import split_scales
from caliper.roi_extract import locate_roi_lowres, orient_caliper


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "tupian"
OUTPUT_DIR = ROOT / "debug_tupian_projection_samples"
SAMPLES = [
    "11.00.jpg",
    "20.00.jpg",
    "60.50.jpg",
    "70.92.jpg",
    "80.70.jpg",
    "90.28.jpg",
    "100.74.jpg",
    "120.60.jpg",
    "140.00.jpg",
]


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Unable to read image: {path}")
    return image


def write_image(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"Unable to encode image: {path}")
    encoded.tofile(str(path))


def make_contact_sheet(images: list[np.ndarray], labels: list[str]) -> np.ndarray:
    tiles = []
    for image, label in zip(images, labels):
        h, w = image.shape[:2]
        target_w = 880
        target_h = max(1, int(round(h * target_w / w)))
        tile = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_AREA)
        header = np.full((42, target_w, 3), 250, dtype=np.uint8)
        cv2.putText(header, label, (12, 29), cv2.FONT_HERSHEY_SIMPLEX,
                    0.75, (20, 20, 20), 2, cv2.LINE_AA)
        tiles.append(np.vstack((header, tile)))

    rows = []
    for index in range(0, len(tiles), 2):
        row_tiles = tiles[index:index + 2]
        if len(row_tiles) == 1:
            row_tiles.append(np.full_like(row_tiles[0], 238))
        height = max(tile.shape[0] for tile in row_tiles)
        aligned = []
        for tile in row_tiles:
            if tile.shape[0] < height:
                pad = np.full((height - tile.shape[0], tile.shape[1], 3), 238, dtype=np.uint8)
                tile = np.vstack((tile, pad))
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


def with_projection_settings(**updates):
    original = {key: getattr(config.region_split, key) for key in updates}
    for key, value in updates.items():
        setattr(config.region_split, key, value)
    return original


def restore_projection_settings(values: dict) -> None:
    for key, value in values.items():
        setattr(config.region_split, key, value)


def make_comparison(old_vis: np.ndarray, new_vis: np.ndarray) -> np.ndarray:
    target_w = 980
    resized = []
    for image in (old_vis, new_vis):
        h, w = image.shape[:2]
        resized.append(cv2.resize(image, (target_w, max(1, int(round(h * target_w / w)))),
                                  interpolation=cv2.INTER_AREA))
    title_old = np.full((44, target_w, 3), 238, dtype=np.uint8)
    title_new = title_old.copy()
    cv2.putText(title_old, "Before: full-width projection", (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(title_new, "After: component tick support", (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 20, 20), 2, cv2.LINE_AA)
    return np.vstack((title_old, resized[0], np.full((12, target_w, 3), 35, dtype=np.uint8),
                      title_new, resized[1]))


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    summaries = []
    visualizations = []
    labels = []

    params = {
        "clip_limit": config.preprocess.clahe_clip_limit,
        "bilateral_d": config.preprocess.bilateral_d,
        "bilateral_sigma": config.preprocess.bilateral_sigma,
        "gamma": config.preprocess.gamma,
        "median_ksize": config.preprocess.median_ksize,
    }

    for number, filename in enumerate(SAMPLES, start=1):
        path = INPUT_DIR / filename
        entry = {"image": filename, "truth_mm": float(path.stem)}
        try:
            source = read_image(path)
            old_settings = with_projection_settings(
                vertical_open_height_ratio=31.0 / source.shape[0],
                vertical_open_min_height=31,
                vertical_open_max_height=31,
                projection_use_components=False,
                projection_smooth_height_ratio=1.0 / 45.0,
                projection_smooth_min=5,
                projection_smooth_max=21,
                seam_use_component_endpoints=False,
            )
            _, _, baseline = run_split(source, params)
            restore_projection_settings(old_settings)

            roi, oriented, split = run_split(source, params)
            visualization = split["split_vis"]
            out_name = f"{number:02d}_{path.stem}_region_split.png"
            write_image(OUTPUT_DIR / out_name, visualization)
            compare_name = f"{number:02d}_{path.stem}_projection_compare.png"
            write_image(OUTPUT_DIR / compare_name, make_comparison(baseline["split_vis"], visualization))
            visualizations.append(visualization)
            labels.append(f"{number:02d}  {path.stem} mm")

            bands = split.get("tick_bands", {})
            entry.update({
                "status": "ok",
                "roi_box_original": roi.get("roi_box_original"),
                "roi_size": list(roi["roi_color"].shape[:2][::-1]),
                "orientation_angle": oriented.get("orient_angle"),
                "split_y": split.get("split_y"),
                "main_tick_band": bands.get("main_tick_band"),
                "vernier_tick_band": bands.get("vernier_tick_band"),
                "visualization": out_name,
                "comparison": compare_name,
                "baseline_split_y": baseline.get("split_y"),
            })
        except Exception as exc:
            entry.update({"status": "failed", "error": str(exc)})
        summaries.append(entry)
        print(json.dumps(entry, ensure_ascii=False))

    if visualizations:
        write_image(OUTPUT_DIR / "contact_sheet.png", make_contact_sheet(visualizations, labels))
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
