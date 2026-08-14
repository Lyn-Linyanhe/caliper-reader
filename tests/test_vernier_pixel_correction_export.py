from pathlib import Path

import numpy as np

from tools.export_vernier_pixel_correction_images import export_images


def test_export_vernier_pixel_correction_writes_binary_images_and_coordinates(
    tmp_path, monkeypatch
):
    from tools import export_vernier_pixel_correction_images as exporter

    raw_binary = np.zeros((12, 40), dtype=np.uint8)
    raw_binary[:, 10] = 255
    corrected = raw_binary.copy()
    continuous = raw_binary.copy()
    synthetic = np.zeros_like(raw_binary)

    class FakePipeline:
        def __init__(self, fast_mode=False):
            self.step_results = {
                'vernier': {
                    'vernier_band_detection': {
                        'band_y1': 4,
                        'band_y2': 16,
                        'per_tick_correction': {
                            'raw_band': raw_binary,
                            'straightened_band': corrected,
                            'continuous_band': continuous,
                            'synthetic_gap_mask': synthetic,
                            'x_start': 8,
                            'x_end': 32,
                            'band_y1': 4,
                            'band_y2': 16,
                            'band_height': 12,
                            'trace_count': 1,
                            'untraced_count': 0,
                            'candidate_count': 1,
                            'candidate_states': [
                                {'status': 'traced', 'reference_x': 10}
                            ],
                        },
                    }
                }
            }

        def run(self, image):
            return type('Result', (), {'total': 1.0})()

    monkeypatch.setattr(exporter, 'CaliperPipeline', FakePipeline)
    monkeypatch.setattr(
        exporter, 'read_image', lambda path: np.zeros((20, 40, 3), dtype=np.uint8)
    )

    report = export_images(tmp_path, tmp_path / 'out', ['sample.jpg'])
    figures = report['samples'][0]['figures']
    assert report['samples'][0]['error'] is None
    assert figures['height'] == 12
    assert figures['x_start'] == 8
    assert figures['x_end'] == 32
    assert figures['raw_binary'].endswith('_raw_binary_roi.png')
    assert figures['corrected_binary'].endswith('_straightened_binary_roi.png')
    assert figures['continuous_binary'].endswith('_continuous_display_roi.png')
    assert figures['synthetic_gap_mask'].endswith('_synthetic_gap_mask.png')
    assert (tmp_path / 'out' / figures['raw_binary']).is_file()
    assert (tmp_path / 'out' / figures['corrected_binary']).is_file()
    assert (tmp_path / 'out' / figures['continuous_binary']).is_file()
    assert (tmp_path / 'out' / figures['synthetic_gap_mask']).is_file()
    assert (tmp_path / 'out' / figures['compare']).is_file()
    assert (tmp_path / 'out' / 'vernier_pixel_correction_summary.json').is_file()


def test_export_vernier_pixel_correction_clamps_raw_roi_like_corrected_roi(
    tmp_path, monkeypatch
):
    from tools import export_vernier_pixel_correction_images as exporter

    raw_binary = np.zeros((12, 40), dtype=np.uint8)
    raw_binary[:, 10] = 255
    corrected = raw_binary.copy()
    continuous = raw_binary.copy()
    synthetic = np.zeros_like(raw_binary)

    class FakePipeline:
        def __init__(self, fast_mode=False):
            self.step_results = {
                'vernier': {
                    'vernier_band_detection': {
                        'per_tick_correction': {
                            'raw_band': raw_binary,
                            'straightened_band': corrected,
                            'continuous_band': continuous,
                            'synthetic_gap_mask': synthetic,
                            'x_start': -5,
                            'x_end': 80,
                            'band_y1': 4,
                            'band_y2': 16,
                            'band_height': 12,
                            'trace_count': 1,
                            'untraced_count': 0,
                            'candidate_count': 1,
                            'candidate_states': [],
                        },
                    }
                }
            }

        def run(self, image):
            return type('Result', (), {'total': 1.0})()

    monkeypatch.setattr(exporter, 'CaliperPipeline', FakePipeline)
    monkeypatch.setattr(
        exporter,
        'read_image',
        lambda path: np.zeros((20, 40, 3), dtype=np.uint8),
    )

    report = exporter.export_images(tmp_path, tmp_path / 'out', ['sample.jpg'])

    assert report['samples'][0]['error'] is None
    assert report['samples'][0]['figures']['width'] == 40
