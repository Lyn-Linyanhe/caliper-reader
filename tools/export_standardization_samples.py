"""Export detailed main/vernier standardization evidence for selected images."""

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


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f'Unable to read image: {path}')
    return image


def write_image(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode('.png', image)
    if not ok:
        raise RuntimeError(f'Unable to encode image: {path}')
    encoded.tofile(str(path))


def _classification(standardization: dict | None) -> dict:
    classification = (standardization or {}).get('classification', {})
    return {
        'mode': classification.get('mode', 'unknown'),
        'centers': list(classification.get('centers', [])),
        'counts': list(classification.get('counts', [])),
        'separation': float(classification.get('separation', 0.0) or 0.0),
        'threshold': classification.get('threshold'),
    }


def _curve_width(standardization: dict | None) -> int | None:
    if not standardization:
        return None
    return int(standardization.get('width', 0))


def export_samples(input_dir: Path,
                   output_dir: Path,
                   filenames: list[str]) -> dict:
    """Run detailed mode and export two existing UI panels per image."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    for filename in filenames:
        pipeline = CaliperPipeline(fast_mode=False)
        sample = {
            'filename': filename,
            'reading_mm': None,
            'error': None,
            'main': {},
            'vernier': {},
        }
        try:
            result = pipeline.run(read_image(input_dir / filename))
            main = pipeline.step_results.get('main', {})
            vernier = pipeline.step_results.get('vernier', {})
            main_standardization = main.get('standardization')
            vernier_standardization = vernier.get('standardization')
            standardizations = {
                'main': main_standardization,
                'vernier': vernier_standardization,
            }
            missing_panels = []
            for key, output_name in (
                ('3a_主尺刻度线', f'{Path(filename).stem}_main_standardization.png'),
                ('4b_游标刻度线', f'{Path(filename).stem}_vernier_standardization.png'),
            ):
                image = pipeline.debug_images.get(key)
                if image is not None:
                    write_image(output_dir / output_name, image)
                elif standardizations['main' if key.startswith('3a_') else 'vernier']:
                    missing_panels.append(output_name)
            if missing_panels:
                sample['error'] = 'missing_standardization_visual_panel'
                sample['missing_panels'] = missing_panels
            sample.update({
                'reading_mm': result.total,
                'main': {
                    'classification': _classification(main_standardization),
                    'curve_width': _curve_width(main_standardization),
                    'tick_count': len(main_standardization.get('ticks', []))
                    if main_standardization else 0,
                },
                'vernier': {
                    'classification': _classification(vernier_standardization),
                    'curve_width': _curve_width(vernier_standardization),
                    'tick_count': len(vernier_standardization.get('ticks', []))
                    if vernier_standardization else 0,
                },
            })
        except Exception as exc:
            sample['error'] = str(exc)
        samples.append(sample)

    report = {'samples': samples}
    (output_dir / 'standardization_summary.json').write_text(
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
    report = export_samples(args.input_dir, args.output_dir, args.filenames)
    print(f"Exported {len(report['samples'])} samples to {args.output_dir}")


if __name__ == '__main__':
    main()
