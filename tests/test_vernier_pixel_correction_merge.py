from pathlib import Path

import cv2
import numpy as np

from tools.merge_vernier_pixel_correction_figures import merge_images


def _write_gray(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode('.png', image)
    assert ok
    encoded.tofile(str(path))


def test_merge_vernier_pixel_correction_writes_three_review_figures(tmp_path):
    raw = np.zeros((8, 24), dtype=np.uint8)
    raw[1:7, 8] = 255
    strict = raw.copy()
    continuous = raw.copy()
    continuous[4, 9] = 255
    synthetic = np.zeros_like(raw)
    synthetic[4, 9] = 255

    _write_gray(tmp_path / '12.34_vernier_raw_binary_roi.png', raw)
    _write_gray(tmp_path / '12.34_vernier_straightened_binary_roi.png', strict)
    _write_gray(tmp_path / '12.34_vernier_continuous_display_roi.png', continuous)
    _write_gray(tmp_path / '12.34_vernier_synthetic_gap_mask.png', synthetic)

    report = merge_images(tmp_path, tmp_path / 'merged', ['12.34'])

    assert report['sample_count'] == 1
    assert report['outputs'] == [
        'vernier_pixel_correction_merged_three_stage.png',
        'vernier_pixel_correction_merged_continuous_overview.png',
        'vernier_pixel_correction_merged_strict_continuous_diff.png',
    ]
    for name in report['outputs']:
        output = tmp_path / 'merged' / name
        assert output.is_file()
        image = cv2.imdecode(
            np.fromfile(str(output), dtype=np.uint8), cv2.IMREAD_COLOR
        )
        assert image is not None
        assert image.shape[0] > 0
        assert image.shape[1] > 0
