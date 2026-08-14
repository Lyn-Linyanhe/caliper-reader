"""Export every detailed pipeline visualization for accurate reference samples."""

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


INPUT_DIR = ROOT / 'tupian'
OUTPUT_DIR = ROOT / 'debug_tupian_successful_pipeline_stages_20260724'
SAMPLES = ['30.00.jpg', '40.40.jpg', '90.46.jpg']
TRUTHS = {
    '30.00.jpg': 30.00,
    '40.40.jpg': 40.40,
    '90.46.jpg': 90.46,
}


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


def make_roi_visualization(original: np.ndarray, roi: dict) -> np.ndarray:
    """Show the final ROI when local recovery did not retain its original debug view."""
    visual = original.copy()
    x1, y1, x2, y2 = roi['roi_box_original']
    cv2.rectangle(visual, (x1, y1), (x2, y2), (0, 220, 0), 5)
    label = f"ROI: {roi.get('roi_source', 'unknown')}"
    cv2.putText(visual, label, (max(8, x1), max(30, y1 - 12)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 220, 0), 3, cv2.LINE_AA)
    return visual


def export_samples(input_dir: Path,
                   output_dir: Path,
                   filenames: list[str],
                   truths: dict[str, float]) -> dict:
    """Run exact-reference samples in detailed mode and write all stage images."""
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    for index, filename in enumerate(filenames, start=1):
        pipeline = CaliperPipeline(fast_mode=False)
        original = read_image(input_dir / filename)
        result = pipeline.run(original)
        sample_dir = output_dir / f'{index:02d}_{Path(filename).stem}'
        sample_dir.mkdir(exist_ok=True)

        stage_files = []
        for key, image in result.debug_images.items():
            if image is None:
                continue
            path = sample_dir / f'{key}.png'
            write_image(path, image)
            stage_files.append(path.name)

        if '1_ROI定位.png' not in stage_files:
            path = sample_dir / '1_ROI定位.png'
            write_image(path, make_roi_visualization(
                original, pipeline.step_results['roi']
            ))
            stage_files.append(path.name)

        main = pipeline.step_results.get('main', {})
        vernier = pipeline.step_results.get('vernier', {})
        truth = truths.get(filename)
        samples.append({
            'image': filename,
            'truth_mm': truth,
            'reading_mm': result.total,
            'matches_truth': truth is not None and abs(result.total - truth) < 1e-9,
            'main_scale_mm': result.main_scale,
            'vernier_scale_mm': result.vernier_scale,
            'main_tick_count': len(main.get('main_ticks', [])),
            'vernier_tick_count': len(vernier.get('vernier_ticks', [])),
            'zero_x': vernier.get('zero_x'),
            'alignment_confidence': vernier.get('alignment_confidence'),
            'alignment_ambiguity': result.extra_info.get('alignment_ambiguity'),
            'stage_files': stage_files,
        })

    report = {'samples': samples}
    (output_dir / 'report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    return report


def main() -> None:
    report = export_samples(INPUT_DIR, OUTPUT_DIR, SAMPLES, TRUTHS)
    for sample in report['samples']:
        print(
            f"{sample['image']}: truth={sample['truth_mm']:.2f}, "
            f"reading={sample['reading_mm']:.2f}, "
            f"stages={len(sample['stage_files'])}"
        )
    print(f'Output: {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
