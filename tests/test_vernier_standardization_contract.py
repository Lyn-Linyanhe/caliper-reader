from pathlib import Path

import cv2
import numpy as np

from caliper.pipeline import CaliperPipeline


def _image(filename: str) -> np.ndarray:
    raw = np.fromfile(str(Path('tupian') / filename), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    assert image is not None
    return image


def test_detailed_vernier_result_attaches_one_standardization_object():
    pipeline = CaliperPipeline(fast_mode=False)
    result = pipeline.run(_image('30.00.jpg'))

    vernier = pipeline.step_results['vernier']
    standard = vernier['standardization']
    detection_standard = vernier['vernier_band_detection']['standardization']

    assert standard is detection_standard
    assert standard['curves']['raw_projection'].shape == (standard['width'],)
    assert standard['curves']['support'].shape == (standard['width'],)
    assert standard['curves']['normalized_response'].shape == (standard['width'],)
    assert len(standard['ticks']) == len(vernier['vernier_ticks'])
    assert result.total is not None


def test_fast_vernier_result_does_not_compute_standardization():
    pipeline = CaliperPipeline(fast_mode=True)
    pipeline.run(_image('30.00.jpg'))

    assert pipeline.step_results['vernier']['standardization'] is None
