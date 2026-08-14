"""Export per-tick binary vernier correction masks for inspection.

The exporter is diagnostic only.  It runs detailed recognition, consumes the
existing per-tick traces, and writes the raw/corrected binary tick ROI without
changing formal reading results.  Grayscale data remains internal to the
normal sub-pixel refinement path and is never moved by this exporter.
"""

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
from caliper.vernier_scale import _crop_per_tick_binary_output


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f'Unable to read image: {path}')
    return image


def write_image(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode('.png', np.asarray(image))
    if not ok:
        raise RuntimeError(f'Unable to encode image: {path}')
    encoded.tofile(str(path))


def _to_bgr(gray: np.ndarray) -> np.ndarray:
    gray = np.asarray(gray)
    if gray.ndim == 2:
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return gray.copy()


def _resize_for_review(image: np.ndarray, max_width: int = 1800,
                       scale_y: int = 3) -> np.ndarray:
    if image is None or np.asarray(image).size == 0:
        return np.zeros((80, max_width, 3), dtype=np.uint8)
    image = _to_bgr(image)
    height, width = image.shape[:2]
    target_width = min(max_width, max(1, width))
    target_height = max(1, int(round(height * target_width / max(1, width))))
    target_height = max(target_height, min(500, height * scale_y))
    return cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_NEAREST)


def _draw_correction_compare(raw: np.ndarray,
                             corrected: np.ndarray,
                             correction: dict,
                             title: str,
                             continuous: np.ndarray = None) -> np.ndarray:
    """Render raw, strict evidence, and continuous display masks together."""
    if continuous is None:
        continuous = corrected
    views = [
        ('raw binary tick mask', raw, (235, 235, 235)),
        ('strict per-tick evidence mask', corrected, (80, 220, 255)),
        ('continuous display mask (yellow = synthetic)', continuous, (100, 240, 150)),
    ]
    rendered = [(_resize_for_review(image), label, color)
                for label, image, color in views]
    width = max(view.shape[1] for view, _label, _color in rendered)
    height = max(view.shape[0] for view, _label, _color in rendered)
    gap = 28
    canvas = np.full(
        (height * len(rendered) + gap * (len(rendered) - 1), width, 3),
        (24, 24, 30), dtype=np.uint8
    )
    panel_y = []
    for index, (view, _label, _color) in enumerate(rendered):
        y = index * (height + gap)
        panel_y.append(y)
        canvas[y:y + view.shape[0], :view.shape[1]] = view

    cv2.putText(canvas, f'{title} | {rendered[0][1]}', (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, rendered[0][2], 1, cv2.LINE_AA)
    for y, (_view, label, color) in zip(panel_y[1:], rendered[1:]):
        cv2.putText(canvas, label, (8, y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)

    scale_x = width / max(1, int(correction.get('roi_width', raw.shape[1])))
    roi_start = int(correction.get('x_start', 0) or 0)
    for state in correction.get('candidate_states', []):
        if state.get('status') == 'traced':
            x = float(state.get('reference_x', state.get('approx_x', 0))) - roi_start
            color = (80, 220, 100)
        else:
            x = float(state.get('approx_x', 0)) - roi_start
            color = (60, 100, 255)
        sx = int(round(x * scale_x))
        if 0 <= sx < width:
            for y in panel_y:
                cv2.line(canvas, (sx, y + 24), (sx, y + height - 1),
                         color, 1, cv2.LINE_AA)

    synthetic = correction.get('synthetic_gap_mask')
    if synthetic is not None:
        synthetic_view = _resize_for_review(synthetic)
        y = panel_y[-1]
        mask = np.any(synthetic_view > 0, axis=2) if synthetic_view.ndim == 3 else synthetic_view > 0
        canvas[y:y + synthetic_view.shape[0], :synthetic_view.shape[1]][mask] = (0, 220, 255)

    text = (
        f"height={correction.get('band_height', raw.shape[0])} px; "
        f"x=[{correction.get('x_start', 0)},{correction.get('x_end', raw.shape[1])}); "
        f"strict={correction.get('trace_count', 0)}/"
        f"{correction.get('candidate_count', 0)}; "
        f"synthetic_pixels={correction.get('display_synthetic_pixels', 0)}"
    )
    cv2.putText(canvas, text, (8, canvas.shape[0] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.46, (185, 185, 195), 1, cv2.LINE_AA)
    return canvas


def export_images(input_dir: Path, output_dir: Path,
                  filenames: list[str]) -> dict:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    for filename in filenames:
        sample = {'filename': filename, 'error': None, 'figures': {}}
        try:
            pipeline = CaliperPipeline(fast_mode=False)
            pipeline.run(read_image(input_dir / filename))
            detection = pipeline.step_results['vernier'].get('vernier_band_detection') or {}
            correction = detection.get('per_tick_correction') or {}
            raw = correction.get('raw_band')
            corrected = _crop_per_tick_binary_output(detection)
            continuous = _crop_per_tick_binary_output(
                detection, output_key='continuous_band'
            )
            synthetic = _crop_per_tick_binary_output(
                detection, output_key='synthetic_gap_mask'
            )
            if raw is None or corrected.size == 0:
                raise RuntimeError('vernier_binary_correction_unavailable')
            x_start = int(correction.get('x_start', 0) or 0)
            x_end = int(correction.get('x_end', raw.shape[1]))
            raw_array = np.asarray(raw)
            raw_start = max(0, min(raw_array.shape[1], x_start))
            raw_end = max(raw_start, min(raw_array.shape[1], x_end))
            raw_roi = raw_array[:, raw_start:raw_end].copy()
            if raw_roi.shape != corrected.shape:
                raise RuntimeError(
                    f'raw/corrected ROI shape mismatch: {raw_roi.shape} != {corrected.shape}'
                )
            if continuous.shape != corrected.shape:
                raise RuntimeError(
                    f'strict/continuous ROI shape mismatch: '
                    f'{corrected.shape} != {continuous.shape}'
                )
            if synthetic.shape != corrected.shape:
                raise RuntimeError(
                    f'strict/synthetic ROI shape mismatch: '
                    f'{corrected.shape} != {synthetic.shape}'
                )
            display_correction = dict(correction)
            display_correction['x_start'] = raw_start
            display_correction['x_end'] = raw_end
            display_correction['synthetic_gap_mask'] = synthetic

            stem = Path(filename).stem
            raw_name = f'{stem}_vernier_raw_binary_roi.png'
            corrected_name = f'{stem}_vernier_straightened_binary_roi.png'
            continuous_name = f'{stem}_vernier_continuous_display_roi.png'
            synthetic_name = f'{stem}_vernier_synthetic_gap_mask.png'
            compare_name = f'{stem}_vernier_pixel_correction_compare.png'
            write_image(output_dir / raw_name, raw_roi)
            write_image(output_dir / corrected_name, corrected)
            write_image(output_dir / continuous_name, continuous)
            write_image(output_dir / synthetic_name, synthetic)
            write_image(
                output_dir / compare_name,
                _draw_correction_compare(
                    raw_roi, corrected, display_correction, stem,
                    continuous=continuous,
                ),
            )
            sample['figures'] = {
                'raw_binary': raw_name,
                'corrected_binary': corrected_name,
                'continuous_binary': continuous_name,
                'synthetic_gap_mask': synthetic_name,
                'compare': compare_name,
                'height': int(corrected.shape[0]),
                'width': int(corrected.shape[1]),
                'band_y': [
                    int(correction.get('band_y1', detection.get('band_y1', 0))),
                    int(correction.get('band_y2', detection.get('band_y2', corrected.shape[0]))),
                ],
                'x_start': x_start,
                'x_end': x_end,
                'traced_count': int(correction.get('trace_count', 0)),
                'untraced_count': int(correction.get('untraced_count', 0)),
                'candidate_count': int(correction.get('candidate_count', 0)),
                'display_trace_count': int(correction.get('display_trace_count', 0)),
                'display_filled_gap_rows': int(
                    correction.get('display_filled_gap_rows', 0)
                ),
                'display_synthetic_pixels': int(
                    correction.get('display_synthetic_pixels', 0)
                ),
                'output_kind': 'binary_tick_mask',
            }
        except Exception as exc:
            sample['error'] = str(exc)
        samples.append(sample)

    report = {'samples': samples}
    (output_dir / 'vernier_pixel_correction_summary.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'tupian')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--image', dest='filenames', action='append', required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    report = export_images(args.input_dir, args.output_dir, args.filenames)
    print(f"Exported {len(report['samples'])} samples to {args.output_dir}")


if __name__ == '__main__':
    main()
