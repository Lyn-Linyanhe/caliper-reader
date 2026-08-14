"""Create compact review sheets for the vernier pixel-correction exports.

The images are diagnostic only.  Every panel is a display rendering of the
already exported binary masks; no recognition result is recalculated here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


BACKGROUND = (24, 24, 30)
RAW_COLOR = (210, 210, 210)
STRICT_COLOR = (220, 200, 80)       # BGR: blue-green evidence pixels
TRUE_COLOR = (150, 220, 170)        # BGR: pixels present in the strict mask
SYNTHETIC_COLOR = (75, 211, 255)    # BGR: yellow synthetic-gap pixels
MISSING_COLOR = (220, 80, 220)      # BGR: strict pixels absent from continuous
TEXT_COLOR = (232, 232, 238)
SUBTLE_TEXT = (175, 175, 188)


def _read_gray(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(f'Unable to read image: {path}')
    return image


def _write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode('.png', np.asarray(image))
    if not ok:
        raise RuntimeError(f'Unable to encode image: {path}')
    encoded.tofile(str(path))


def _stem(value: str) -> str:
    name = Path(value).name
    for suffix in ('.jpeg', '.jpg', '.png', '.bmp', '.tif', '.tiff'):
        if name.lower().endswith(suffix):
            return name[:-len(suffix)]
    return name


def _mask_to_canvas(mask: np.ndarray, color: tuple[int, int, int],
                    width: int, max_height: int = 220,
                    min_height: int = 90, vertical_stretch: float = 3.0
                    ) -> np.ndarray:
    """Fit a binary mask into a fixed-width review canvas.

    The vertical dimension is intentionally enlarged for legibility.  This is
    a display transformation only and is kept identical across all stages of
    one sample.
    """
    mask = np.asarray(mask)
    if mask.ndim == 3:
        return _color_to_canvas(mask, width, max_height, min_height,
                                vertical_stretch)
    if mask.ndim != 2 or mask.size == 0:
        return np.full((min_height, width, 3), BACKGROUND, dtype=np.uint8)
    source_height, source_width = mask.shape
    target_width = min(width - 8, max(1, source_width))
    natural_height = max(1, int(round(source_height * target_width / source_width)))
    target_height = min(
        max_height,
        max(min_height, int(round(natural_height * vertical_stretch))),
    )
    resized = cv2.resize(
        (mask > 0).astype(np.uint8),
        (target_width, target_height),
        interpolation=cv2.INTER_NEAREST,
    )
    canvas = np.full((target_height, width, 3), BACKGROUND, dtype=np.uint8)
    x0 = (width - target_width) // 2
    canvas[:, x0:x0 + target_width][resized > 0] = color
    return canvas


def _color_to_canvas(image: np.ndarray, width: int, max_height: int = 220,
                     min_height: int = 90, vertical_stretch: float = 3.0
                     ) -> np.ndarray:
    """Fit an already colorized diagnostic image using the mask geometry."""
    image = np.asarray(image)
    if image.ndim != 3 or image.shape[2] != 3 or image.size == 0:
        return np.full((min_height, width, 3), BACKGROUND, dtype=np.uint8)
    source_height, source_width = image.shape[:2]
    target_width = min(width - 8, max(1, source_width))
    natural_height = max(1, int(round(source_height * target_width / source_width)))
    target_height = min(
        max_height,
        max(min_height, int(round(natural_height * vertical_stretch))),
    )
    resized = cv2.resize(image, (target_width, target_height),
                         interpolation=cv2.INTER_NEAREST)
    canvas = np.full((target_height, width, 3), BACKGROUND, dtype=np.uint8)
    x0 = (width - target_width) // 2
    canvas[:, x0:x0 + target_width] = resized
    return canvas


def _panel(image: np.ndarray, title: str, footer: str = '') -> np.ndarray:
    title_height = 32
    footer_height = 24 if footer else 0
    height, width = image.shape[:2]
    panel = np.full(
        (height + title_height + footer_height, width, 3),
        BACKGROUND,
        dtype=np.uint8,
    )
    panel[title_height:title_height + height] = image
    cv2.putText(panel, title, (10, 21), cv2.FONT_HERSHEY_SIMPLEX,
                0.60, TEXT_COLOR, 1, cv2.LINE_AA)
    if footer:
        cv2.putText(panel, footer, (10, height + title_height + 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, SUBTLE_TEXT, 1,
                    cv2.LINE_AA)
    cv2.rectangle(panel, (0, 0), (width - 1, panel.shape[0] - 1),
                  (90, 90, 104), 1)
    return panel


def _row(panels: list[np.ndarray], gap: int = 18) -> np.ndarray:
    height = max(panel.shape[0] for panel in panels)
    width = sum(panel.shape[1] for panel in panels) + gap * (len(panels) - 1)
    canvas = np.full((height, width, 3), BACKGROUND, dtype=np.uint8)
    x = 0
    for panel in panels:
        y = (height - panel.shape[0]) // 2
        canvas[y:y + panel.shape[0], x:x + panel.shape[1]] = panel
        x += panel.shape[1] + gap
    return canvas


def _stack(rows: list[np.ndarray], title: str, legend: list[tuple[str, tuple[int, int, int]]],
           gap: int = 22) -> np.ndarray:
    body_width = max(row.shape[1] for row in rows)
    header_height = 70
    body_height = sum(row.shape[0] for row in rows) + gap * (len(rows) - 1)
    canvas = np.full((header_height + body_height, body_width, 3),
                     BACKGROUND, dtype=np.uint8)
    cv2.putText(canvas, title, (14, 28), cv2.FONT_HERSHEY_SIMPLEX,
                0.78, TEXT_COLOR, 1, cv2.LINE_AA)
    x = 14
    for label, color in legend:
        cv2.rectangle(canvas, (x, 46), (x + 18, 62), color, -1)
        cv2.putText(canvas, label, (x + 25, 59), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, SUBTLE_TEXT, 1, cv2.LINE_AA)
        x += 175 if len(label) < 16 else 235
    y = header_height
    for index, row in enumerate(rows):
        x0 = (body_width - row.shape[1]) // 2
        canvas[y:y + row.shape[0], x0:x0 + row.shape[1]] = row
        y += row.shape[0]
        if index < len(rows) - 1:
            y += gap
    return canvas


def _continuous_overlay(strict: np.ndarray, continuous: np.ndarray,
                        synthetic: np.ndarray) -> np.ndarray:
    strict_mask = np.asarray(strict) > 0
    continuous_mask = np.asarray(continuous) > 0
    synthetic_mask = np.asarray(synthetic) > 0
    synthetic_mask |= continuous_mask & ~strict_mask
    image = np.full((*strict_mask.shape, 3), BACKGROUND, dtype=np.uint8)
    image[strict_mask & continuous_mask] = TRUE_COLOR
    image[synthetic_mask] = SYNTHETIC_COLOR
    return image


def _difference_overlay(strict: np.ndarray, continuous: np.ndarray,
                        synthetic: np.ndarray) -> np.ndarray:
    strict_mask = np.asarray(strict) > 0
    continuous_mask = np.asarray(continuous) > 0
    synthetic_mask = np.asarray(synthetic) > 0
    synthetic_mask |= continuous_mask & ~strict_mask
    missing_mask = strict_mask & ~continuous_mask
    common_mask = strict_mask & continuous_mask
    image = np.full((*strict_mask.shape, 3), BACKGROUND, dtype=np.uint8)
    image[common_mask] = TRUE_COLOR
    image[synthetic_mask] = SYNTHETIC_COLOR
    image[missing_mask] = MISSING_COLOR
    return image


def _load_sample(input_dir: Path, sample: str) -> dict[str, np.ndarray | str]:
    stem = _stem(sample)
    paths = {
        'raw': input_dir / f'{stem}_vernier_raw_binary_roi.png',
        'strict': input_dir / f'{stem}_vernier_straightened_binary_roi.png',
        'continuous': input_dir / f'{stem}_vernier_continuous_display_roi.png',
        'synthetic': input_dir / f'{stem}_vernier_synthetic_gap_mask.png',
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(', '.join(missing))
    arrays = {name: _read_gray(path) for name, path in paths.items()}
    shape = arrays['raw'].shape
    if any(array.shape != shape for array in arrays.values()):
        raise ValueError(f'{stem}: exported masks do not share one shape')
    arrays['stem'] = stem
    return arrays


def _footer(summary: dict, key: str) -> str:
    if not summary:
        return ''
    return (f"traced={summary.get('traced_count', '?')}/"
            f"{summary.get('candidate_count', '?')}; "
            f"synthetic_px={summary.get('display_synthetic_pixels', '?')}")


def _read_summary(input_dir: Path) -> dict[str, dict]:
    path = input_dir / 'vernier_pixel_correction_summary.json'
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    result = {}
    for sample in data.get('samples', []):
        stem = _stem(sample.get('filename', ''))
        result[stem] = sample.get('figures', {})
    return result


def merge_images(input_dir: Path, output_dir: Path,
                 samples: list[str], panel_width: int = 1180) -> dict:
    """Write three multi-sample review sheets and return their manifest."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = _read_summary(input_dir)
    loaded = [_load_sample(input_dir, sample) for sample in samples]
    three_stage_rows = []
    continuous_rows = []
    difference_rows = []
    for item in loaded:
        stem = str(item['stem'])
        info = summary.get(stem, {})
        raw = np.asarray(item['raw'])
        strict = np.asarray(item['strict'])
        continuous = np.asarray(item['continuous'])
        synthetic = np.asarray(item['synthetic'])
        # One row uses the same display dimensions for all three stages.
        raw_canvas = _mask_to_canvas(raw, RAW_COLOR, panel_width)
        strict_canvas = _mask_to_canvas(strict, STRICT_COLOR, panel_width,
                                        max_height=raw_canvas.shape[0],
                                        min_height=raw_canvas.shape[0],
                                        vertical_stretch=1.0)
        continuous_canvas = _mask_to_canvas(continuous, TRUE_COLOR, panel_width,
                                            max_height=raw_canvas.shape[0],
                                            min_height=raw_canvas.shape[0],
                                            vertical_stretch=1.0)
        three_stage_rows.append(_row([
            _panel(raw_canvas, f'{stem} | raw binary'),
            _panel(strict_canvas, 'strict evidence'),
            _panel(continuous_canvas, 'continuous display', _footer(info, 'continuous')),
        ]))

        overlay_resized = _color_to_canvas(
            _continuous_overlay(strict, continuous, synthetic), panel_width
        )
        continuous_rows.append(_row([
            _panel(overlay_resized, f'{stem} | continuous overlay', _footer(info, 'continuous')),
        ]))

        diff = _difference_overlay(strict, continuous, synthetic)
        strict_diff_canvas = _mask_to_canvas(strict, TRUE_COLOR, panel_width)
        continuous_diff_canvas = _mask_to_canvas(_continuous_overlay(strict, continuous, synthetic),
                                                 TRUE_COLOR, panel_width,
                                                 max_height=strict_diff_canvas.shape[0],
                                                 min_height=strict_diff_canvas.shape[0],
                                                 vertical_stretch=1.0)
        diff_canvas = _color_to_canvas(diff, panel_width,
                                       max_height=strict_diff_canvas.shape[0],
                                       min_height=strict_diff_canvas.shape[0],
                                       vertical_stretch=1.0)
        difference_rows.append(_row([
            _panel(strict_diff_canvas, f'{stem} | strict'),
            _panel(continuous_diff_canvas, 'continuous'),
            _panel(diff_canvas, 'difference: yellow=new, magenta=missing', _footer(info, 'diff')),
        ]))

    outputs = [
        'vernier_pixel_correction_merged_three_stage.png',
        'vernier_pixel_correction_merged_continuous_overview.png',
        'vernier_pixel_correction_merged_strict_continuous_diff.png',
    ]
    images = [
        _stack(three_stage_rows, 'Vernier pixel correction | three stages',
               [('mask pixels', RAW_COLOR)]),
        _stack(continuous_rows, 'Vernier pixel correction | continuous overview',
               [('traced pixels', TRUE_COLOR), ('synthetic gap pixels', SYNTHETIC_COLOR)]),
        _stack(difference_rows, 'Vernier pixel correction | strict vs continuous',
               [('common/traced', TRUE_COLOR), ('synthetic/new', SYNTHETIC_COLOR),
                ('strict-only/missing', MISSING_COLOR)]),
    ]
    for name, image in zip(outputs, images):
        _write_image(output_dir / name, image)
    report = {
        'sample_count': len(samples),
        'samples': [_stem(sample) for sample in samples],
        'outputs': outputs,
        'display_note': 'Masks are nearest-neighbour resized with vertical display enlargement; geometry is not used for measurement.',
    }
    (output_dir / 'vernier_pixel_correction_merged_summary.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--sample', dest='samples', action='append', required=True,
                        help='Sample stem or exported image filename; repeat for multiple samples.')
    parser.add_argument('--panel-width', type=int, default=1180)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    report = merge_images(args.input_dir, args.output_dir, args.samples,
                          panel_width=max(300, args.panel_width))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
