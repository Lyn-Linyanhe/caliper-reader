from pathlib import Path

import cv2
import numpy as np

from caliper.pipeline import CaliperPipeline
from caliper.vernier_scale import (
    _bridge_short_vertical_gaps,
    _pair_has_no_large_internal_valley,
    _select_best_valley_pair,
    _suppress_duplicate_candidates,
    _valley_has_two_sided_peak_support,
)


def _run(filename: str):
    image = cv2.imread(str(Path('tupian') / filename))
    assert image is not None
    pipeline = CaliperPipeline(fast_mode=True)
    pipeline.run(image)
    return pipeline.step_results['vernier']


def test_duplicate_suppression_does_not_chain_across_separate_ticks():
    candidates = [
        {'x_projection': 1556, 'projection_strength': 0.30, 'component': None},
        {'x_projection': 1574, 'projection_strength': 0.70, 'component': None},
        {'x_projection': 1590, 'projection_strength': 0.29, 'component': None},
        {'x_projection': 1617, 'projection_strength': 0.48, 'component': {'area': 100}},
    ]

    accepted, _ = _suppress_duplicate_candidates(candidates, observed_period=44.0)

    assert [item['x_projection'] for item in accepted] == [1574, 1617]


def test_2420_keeps_the_leftmost_observed_vernier_tick_as_zero():
    vernier = _run('24.20.jpg')

    assert len(vernier['vernier_ticks']) > 0
    assert vernier['zero_x'] < 1600


def test_30_and_30_30_keep_observed_valley_bounded_vernier_evidence():
    for filename in ('30.00.jpg', '30.30.jpg'):
        vernier = _run(filename)
        assert len(vernier['vernier_ticks']) > 0, filename


def test_11050_and_14000_fall_back_to_a_structurally_valid_valley_pair():
    for filename in ('110.50.jpg', '140.00.jpg'):
        vernier = _run(filename)
        assert len(vernier['vernier_ticks']) > 0, filename


def test_edge_valley_without_outer_peak_is_rejected():
    projection = np.zeros(80, dtype=float)
    projection[12:20] = 0.9
    projection[25:33] = 0.9

    assert not _valley_has_two_sided_peak_support(
        projection, (0, 6), 8.0, 0.5, 1.0, 2.0
    )


def test_valley_between_two_peak_bands_is_supported():
    projection = np.zeros(96, dtype=float)
    projection[8:16] = 0.9
    projection[32:40] = 0.9

    assert _valley_has_two_sided_peak_support(
        projection, (20, 24), 8.0, 0.5, 1.0, 2.0
    )


def test_large_internal_low_response_break_is_rejected():
    smooth = np.ones(120, dtype=float) * 0.8
    smooth[48:64] = 0.05

    assert not _pair_has_no_large_internal_valley(
        smooth, (8, 16), (104, 112), 0.2, 8.0, 1.3
    )


def test_short_intertick_low_response_does_not_break_pair():
    smooth = np.ones(120, dtype=float) * 0.8
    smooth[52:58] = 0.05

    assert _pair_has_no_large_internal_valley(
        smooth, (8, 16), (104, 112), 0.2, 8.0, 1.3
    )


def test_zero_error_samples_do_not_select_the_left_edge_as_vernier_band():
    minimum_left_starts = {
        '40.00.jpg': 2000,
        '90.14.jpg': 2000,
        '71.50.jpg': 1500,
        '100.74.jpg': 500,
        '70.96.jpg': 900,
    }
    for filename, minimum_left_start in minimum_left_starts.items():
        vernier = _run(filename)
        detection = vernier['vernier_band_detection']
        left, _right, _middle = detection['selected_valley_pair']

        assert left[0] >= minimum_left_start, filename
        assert vernier['zero_x'] >= minimum_left_start, filename
        assert len(vernier['vernier_ticks']) > 0, filename


def test_close_valley_scores_prefer_observed_tick_count_near_fifty_one():
    short_band = {'total_score': 0.718, 'accepted_candidates': [{}] * 27}
    full_band = {'total_score': 0.705, 'accepted_candidates': [{}] * 53}

    selected = _select_best_valley_pair(
        [short_band, full_band], tie_margin=0.02, preferred_tick_count=51
    )

    assert selected is full_band


def test_vertical_bridge_connects_short_fragment_gap_in_same_column():
    foreground = np.zeros((48, 5), dtype=np.uint8)
    foreground[0:1, 2] = 1
    foreground[9:40, 2] = 1

    bridged = _bridge_short_vertical_gaps(foreground, max_gap=10)

    assert np.all(bridged[0:40, 2] == 1)


def test_vertical_bridge_keeps_long_fragment_gap_separate():
    foreground = np.zeros((48, 5), dtype=np.uint8)
    foreground[0:2, 2] = 1
    foreground[13:40, 2] = 1

    bridged = _bridge_short_vertical_gaps(foreground, max_gap=10)

    assert np.all(bridged[2:13, 2] == 0)


def test_short_fragment_recovery_keeps_the_first_ticks_of_remaining_zero_errors():
    expected = {
        '70.00.jpg': 70.00,
        '73.54.jpg': 73.54,
        '110.00.jpg': 110.00,
    }
    for filename, target in expected.items():
        image = cv2.imread(str(Path('tupian') / filename))
        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(image)

        assert abs(result.total - target) <= 0.10, filename
