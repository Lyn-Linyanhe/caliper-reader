from pathlib import Path

import numpy as np

from tools.export_standardization_samples import export_samples


def test_standardization_export_writes_panels_and_summary(tmp_path):
    root = Path(__file__).resolve().parents[1]
    report = export_samples(
        input_dir=root / 'tupian',
        output_dir=tmp_path,
        filenames=['30.00.jpg', '120.60.jpg'],
    )

    assert len(report['samples']) == 2
    assert (tmp_path / '30.00_main_standardization.png').is_file()
    assert (tmp_path / '30.00_vernier_standardization.png').is_file()
    assert (tmp_path / '120.60_main_standardization.png').is_file()
    assert (tmp_path / '120.60_vernier_standardization.png').is_file()
    assert (tmp_path / 'standardization_summary.json').is_file()


def test_standardization_export_marks_missing_visual_panel_as_error(tmp_path, monkeypatch):
    from tools import export_standardization_samples as exporter

    class FakePipeline:
        def __init__(self, fast_mode=False):
            self.debug_images = {}
            self.step_results = {
                'main': {'standardization': {'width': 2, 'ticks': [], 'classification': {}}},
                'vernier': {'standardization': {'width': 2, 'ticks': [], 'classification': {}}},
            }

        def run(self, image):
            class Result:
                total = 1.0
            return Result()

    monkeypatch.setattr(exporter, 'CaliperPipeline', FakePipeline)
    monkeypatch.setattr(exporter, 'read_image', lambda path: np.zeros((2, 2, 3), dtype=np.uint8))

    report = export_samples(tmp_path, tmp_path / 'out', ['sample.jpg'])

    assert report['samples'][0]['error'] == 'missing_standardization_visual_panel'
