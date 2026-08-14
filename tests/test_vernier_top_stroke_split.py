from pathlib import Path

import cv2
import numpy as np

from caliper.pipeline import CaliperPipeline
from caliper.vernier_scale import _split_top_stroke_from_candidate


def _band(filename: str):
    image = cv2.imread(str(Path('tupian') / filename))
    assert image is not None
    pipeline = CaliperPipeline(fast_mode=True)
    pipeline.run(image)
    detection = pipeline.step_results['vernier']['vernier_band_detection']
    return detection['band'], detection['expected_gap']


def test_7252_digit_only_peak_has_no_top_stroke():
    band, gap = _band('72.52.jpg')

    assert _split_top_stroke_from_candidate(band, 1576, gap) is None


def test_7252_zero_tick_is_split_above_the_attached_digit():
    band, gap = _band('72.52.jpg')

    stroke = _split_top_stroke_from_candidate(band, 1608, gap)

    assert stroke is not None
    assert stroke['top_connected']
    assert stroke['thin_run_height'] >= 100
    assert stroke['cut_y'] < 130


def test_4030_zero_tick_is_split_above_its_attached_digit():
    band, gap = _band('40.30.jpg')

    stroke = _split_top_stroke_from_candidate(band, 1532, gap)

    assert stroke is not None
    assert stroke['thin_run_height'] >= 100


def test_top_stroke_skips_short_noise_and_uses_later_continuous_stroke():
    band = np.zeros((80, 32), dtype=np.uint8)
    band[0, 16] = 255
    band[4:68, 15:18] = 255

    stroke = _split_top_stroke_from_candidate(band, 16, observed_period=40.0)

    assert stroke is not None
    assert stroke['thin_run_height'] >= 64
    assert stroke['cut_y'] >= 67


def test_7252_zero_selection_skips_the_digit_only_projection_peak():
    image = cv2.imread(str(Path('tupian') / '72.52.jpg'))
    assert image is not None
    pipeline = CaliperPipeline(fast_mode=True)
    pipeline.run(image)

    zero_x = pipeline.step_results['vernier']['zero_x']
    assert 1600 <= zero_x <= 1620


def test_8070_keeps_its_existing_fraction_after_leading_digit_filtering():
    image = cv2.imread(str(Path('tupian') / '80.70.jpg'))
    assert image is not None
    pipeline = CaliperPipeline(fast_mode=True)
    result = pipeline.run(image)

    assert abs(result.total - 80.70) <= 0.10


def test_10060_keeps_its_existing_fraction_after_leading_digit_filtering():
    image = cv2.imread(str(Path('tupian') / '100.60.jpg'))
    assert image is not None
    pipeline = CaliperPipeline(fast_mode=True)
    result = pipeline.run(image)

    assert abs(result.total - 100.60) <= 0.10


def test_bridged_top_stroke_without_component_support_does_not_shift_4010_zero():
    image = cv2.imread(str(Path('tupian') / '40.10.jpg'))
    assert image is not None
    pipeline = CaliperPipeline(fast_mode=True)
    result = pipeline.run(image)

    assert abs(result.total - 40.10) <= 0.10


def test_leading_zero_ticks_without_component_support_are_recovered():
    expected = {
        '60.50.jpg': 60.50,
        '75.58.jpg': 75.58,
    }
    for filename, target in expected.items():
        image = cv2.imread(str(Path('tupian') / filename))
        assert image is not None

        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(image)

        assert abs(result.total - target) <= 0.10, filename
