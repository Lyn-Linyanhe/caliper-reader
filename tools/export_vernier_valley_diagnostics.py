"""Export the active vernier valley diagnostics for selected images."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caliper.pipeline import CaliperPipeline
from caliper.vernier_scale import _extract_vernier_tick_components


INPUT_DIR = ROOT / "tupian"
DEFAULT_OUTPUT_DIR = ROOT / "debug_tupian_vernier_valleys_20260721"


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


def make_contact_sheet(rows: list[dict], output_dir: Path) -> None:
    panels = []
    for row in rows:
        output = row.get("output")
        if output is None:
            continue
        data = np.fromfile(str(output_dir / output), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            continue
        panel_w, panel_h, header_h = 940, 460, 52
        h, w = image.shape[:2]
        scale = min(panel_w / w, panel_h / h)
        resized = cv2.resize(
            image, (max(1, round(w * scale)), max(1, round(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
        panel = np.full((panel_h + header_h, panel_w, 3), 245, dtype=np.uint8)
        x = (panel_w - resized.shape[1]) // 2
        y = header_h + (panel_h - resized.shape[0]) // 2
        panel[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
        text = (
            f"{row['image']} result={row['reading_mm']:.2f} "
            f"zero_x={row['zero_x']:.1f} ticks={row['tick_count']}"
        )
        cv2.putText(panel, text, (10, 33), cv2.FONT_HERSHEY_SIMPLEX,
                    0.62, (0, 0, 220), 2, cv2.LINE_AA)
        panels.append(panel)
    if not panels:
        return
    if len(panels) % 2:
        panels.append(np.full_like(panels[0], 245))
    sheet = np.vstack([
        np.hstack((panels[index], panels[index + 1]))
        for index in range(0, len(panels), 2)
    ])
    write_image(output_dir / "overview_valleys.png", sheet)


def draw_component_diagnostic(vernier: dict, filename: str) -> np.ndarray | None:
    detection = vernier.get("vernier_band_detection") or {}
    band = detection.get("band")
    candidates = detection.get("tick_candidates") or []
    roi = detection.get("vernier_tick_roi")
    if band is None or not candidates or roi is None:
        return None

    gap = max(3.0, float(detection.get("expected_gap", 0.0) or 0.0))
    x1 = max(0, int(round(roi[0] - gap * 2.0)))
    x2 = min(band.shape[1], int(round(roi[0] + gap * 11.0)))
    if x2 <= x1:
        return None
    crop = band[:, x1:x2]
    scale = max(1, min(4, int(round(1100 / max(1, crop.shape[1])))))
    canvas = cv2.resize(
        cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR),
        (crop.shape[1] * scale, crop.shape[0] * scale),
        interpolation=cv2.INTER_NEAREST,
    )
    foreground = (band > 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 7))
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground, connectivity=8)
    near_seam = max(8, min(18, band.shape[0] // 4))
    min_height = max(8, int(round(band.shape[0] * 0.35)))
    max_width = max(5, int(round(gap * 0.75)))
    for label in range(1, count):
        left = int(stats[label, cv2.CC_STAT_LEFT])
        top = int(stats[label, cv2.CC_STAT_TOP])
        width = int(stats[label, cv2.CC_STAT_WIDTH])
        height = int(stats[label, cv2.CC_STAT_HEIGHT])
        if not (x1 <= left + width / 2.0 < x2):
            continue
        reasons = []
        if top > near_seam:
            reasons.append("below-top")
        if height < min_height:
            reasons.append("short")
        if width > max_width:
            reasons.append("wide")
        color = (0, 220, 0) if not reasons else (0, 80, 255)
        box_left = int(round((left - x1) * scale))
        box_right = int(round((left + width - x1) * scale))
        box_top = int(top * scale)
        box_bottom = int((top + height) * scale)
        cv2.rectangle(canvas, (box_left, box_top), (box_right, box_bottom), color, 2)
        status = f"CC {label}" if not reasons else f"CC {label}: {'/'.join(reasons)}"
        cv2.putText(canvas, status, (box_left, max(16, box_top + 16)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)

    zero_x = float(vernier.get("zero_x", 0.0) or 0.0)
    for candidate in candidates:
        x = float(candidate["x_projection"])
        if not x1 <= x < x2:
            continue
        px = int(round((x - x1) * scale))
        supported = candidate.get("component_id") is not None
        color = (0, 220, 0) if supported else (0, 90, 255)
        thickness = 2 if supported else 1
        cv2.line(canvas, (px, 0), (px, canvas.shape[0] - 1), color, thickness)
        label = f"P {int(x)}" if supported else f"P {int(x)} no-CC"
        cv2.putText(canvas, label, (px + 3, canvas.shape[0] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)
    if x1 <= zero_x < x2:
        px = int(round((zero_x - x1) * scale))
        cv2.line(canvas, (px, 0), (px, canvas.shape[0] - 1), (255, 0, 255), 3)
        cv2.putText(canvas, "CURRENT ZERO", (px + 5, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 255), 2, cv2.LINE_AA)

    header = np.full((42, canvas.shape[1], 3), 30, dtype=np.uint8)
    cv2.putText(header, f"{filename}: green=qualified CC, orange=rejected raw CC/projection-only, magenta=current zero",
                (8, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.47, (240, 240, 240), 1, cv2.LINE_AA)
    return np.vstack((header, canvas))


def main(filenames: tuple[str, ...], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, filename in enumerate(filenames, start=1):
        pipeline = CaliperPipeline(fast_mode=False)
        result = pipeline.run(read_image(INPUT_DIR / filename))
        vernier = pipeline.step_results.get("vernier", {})
        detection = vernier.get("vernier_band_detection") or {}
        visualization = vernier.get("vis_valley")
        output = None
        if visualization is not None:
            output = f"{index:02d}_{Path(filename).stem}_valleys.png"
            write_image(output_dir / output, visualization)
        component_visualization = draw_component_diagnostic(vernier, filename)
        component_output = None
        if component_visualization is not None:
            component_output = f"{index:02d}_{Path(filename).stem}_components.png"
            write_image(output_dir / component_output, component_visualization)
        rows.append({
            "image": filename,
            "reading_mm": float(result.total),
            "zero_x": float(vernier.get("zero_x", 0.0) or 0.0),
            "tick_count": len(vernier.get("vernier_ticks", [])),
            "has_valley_visualization": visualization is not None,
            "selected_valley_pair": detection.get("selected_valley_pair"),
            "all_valley_segments": detection.get("all_valley_segments"),
            "period_clarity": detection.get("period_clarity"),
            "selection_score": detection.get("selection_score"),
            "output": output,
            "component_output": component_output,
        })
    (output_dir / "valley_report.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8",
    )
    make_contact_sheet(rows, output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="+")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    main(tuple(args.filenames), args.output_dir)
