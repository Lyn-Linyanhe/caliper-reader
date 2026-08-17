import numpy as np
import pytest
import cv2
from pathlib import Path

from caliper.pipeline import CaliperPipeline
from caliper import vernier_scale
from caliper.vernier_scale import (
    _build_display_binary_evidence,
    _build_per_tick_straightened_band,
    _trace_vernier_tick_centerline,
)


def _opposite_sloped_band() -> np.ndarray:
    band = np.zeros((40, 64), dtype=np.uint8)
    for y in range(band.shape[0]):
        band[y, 8 + round(0.20 * y)] = 255
        band[y, 42 - round(0.15 * y)] = 255
    band[18:36, 23:30] = 255  # A digit-like wide foreground block.
    return band


def test_trace_vernier_tick_centerline_follows_one_thin_sloped_stroke():
    trace = _trace_vernier_tick_centerline(
        _opposite_sloped_band(), approx_x=8, observed_period=20.0
    )

    assert trace is not None
    assert trace['reference_x'] == pytest.approx(8.0, abs=0.5)
    assert len(trace['points']) >= 36
    assert trace['points'][-1][1] > trace['points'][0][1]


def test_per_tick_straightening_independently_verticalizes_each_trace_only():
    corrected, traces = _build_per_tick_straightened_band(
        _opposite_sloped_band(), [8, 42], observed_period=20.0
    )

    assert len(traces) == 2
    assert np.count_nonzero(corrected[:, 8]) >= 36
    assert np.count_nonzero(corrected[:, 42]) >= 36
    assert np.count_nonzero(corrected[18:36, 23:30]) == 0


def test_per_tick_correction_is_binary_and_does_not_store_gray_output():
    band = _opposite_sloped_band()
    corrected, traces = _build_per_tick_straightened_band(
        band, [8, 42], observed_period=20.0
    )

    assert corrected.shape == band.shape
    assert corrected.dtype == band.dtype
    assert set(np.unique(corrected)).issubset({0, 255})
    assert np.count_nonzero(corrected[:, 8]) >= 36
    assert np.count_nonzero(corrected[:, 42]) >= 36
    assert traces


def test_per_tick_binary_trace_can_seed_below_the_top_noise_band():
    band = np.zeros((48, 40), dtype=np.uint8)
    band[24:, 20] = 255

    corrected, traces = _build_per_tick_straightened_band(
        band, [20], observed_period=20.0
    )

    assert len(traces) == 1
    assert np.count_nonzero(corrected[24:, 20]) >= 20


def _synthetic_trace_with_missing_rows(height=24, gap_rows=()):
    band = np.zeros((height, 48), dtype=np.uint8)
    points = []
    missing = set(gap_rows)
    for y in range(height):
        center = 12 + round(0.20 * y)
        if y in missing:
            continue
        band[y, center - 1:center + 2] = 255
        points.append((y, float(center), center - 1, center + 1))
    trace = {
        'approx_x': 12,
        'reference_x': 12.0,
        'y_start': points[0][0],
        'y_end': points[-1][0],
        'points': points,
    }
    return band, trace


def test_continuous_display_fills_only_short_trace_gaps_and_marks_them():
    band, trace = _synthetic_trace_with_missing_rows(gap_rows=(9, 10))
    continuous, synthetic, displays = vernier_scale._build_per_tick_continuous_display_band(
        band, [trace], observed_period=20.0, max_gap_rows=4
    )

    assert np.count_nonzero(continuous[9:11]) > 0
    assert np.count_nonzero(synthetic[9:11]) > 0
    assert displays[0]['filled_gap_rows'] == 2
    assert np.array_equal(band[9:11], np.zeros_like(band[9:11]))


def test_continuous_display_does_not_bridge_long_gaps():
    band, trace = _synthetic_trace_with_missing_rows(
        gap_rows=tuple(range(8, 15))
    )
    continuous, synthetic, displays = vernier_scale._build_per_tick_continuous_display_band(
        band, [trace], observed_period=20.0, max_gap_rows=4
    )

    assert np.count_nonzero(continuous[8:15]) == 0
    assert np.count_nonzero(synthetic[8:15]) == 0
    assert displays[0]['filled_gap_rows'] == 0


def test_continuous_display_recovers_raw_pixels_after_strict_trace_ends():
    band, full_trace = _synthetic_trace_with_missing_rows()
    truncated_trace = dict(full_trace)
    truncated_trace['points'] = full_trace['points'][:9]
    truncated_trace['y_end'] = truncated_trace['points'][-1][0]

    continuous, synthetic, displays = vernier_scale._build_per_tick_continuous_display_band(
        band, [truncated_trace], observed_period=20.0, max_gap_rows=4
    )

    assert np.all(np.count_nonzero(continuous, axis=1) > 0)
    assert displays[0]['extended_rows'] >= 10
    assert np.count_nonzero(synthetic) == 0


def test_binary_evidence_allows_one_bounded_relaxed_trace_without_component():
    band = np.zeros((60, 80), dtype=np.uint8)
    for y in range(45):
        center = 30 + round(0.20 * y)
        band[y, center - 5:center + 6] = 255

    corrected, traces, states = _build_per_tick_straightened_band(
        band,
        [30],
        observed_period=20.0,
        include_candidate_states=True,
        relaxed_candidate_xs={30},
    )

    assert len(traces) == 1
    assert states[0]['status'] == 'traced'
    assert states[0]['relaxed_retry'] is True
    assert np.count_nonzero(corrected) > 0


def test_display_binary_evidence_does_not_mutate_binary_or_gray_inputs():
    band = _opposite_sloped_band()
    gray_band = np.full_like(band, 180)
    detection = {
        'band': band,
        'gray_band': gray_band,
        'expected_gap': 20.0,
        'vernier_tick_roi': (8, 43),
    }
    band_before = band.copy()
    gray_before = gray_band.copy()

    evidence = _build_display_binary_evidence(
        detection,
        [
            {'x': 8, 'x_projection': 8},
            {'x': 42, 'x_projection': 42},
        ],
        0,
        band.shape[1],
    )

    assert evidence['output_kind'] == 'binary_tick_mask'
    assert np.array_equal(band, band_before)
    assert np.array_equal(gray_band, gray_before)


def test_recovery_keeps_formal_candidate_without_top_evidence():
    band = np.zeros((40, 120), dtype=np.uint8)
    band[:30, 20] = 255
    band[:30, 40] = 255
    band[:30, 60] = 255
    formal = [
        {'x': 20, 'x_projection': 20},
        {'x': 40, 'x_projection': 40},
        {'x': 60, 'x_projection': 60},
        {'x': 100, 'x_projection': 100},
    ]
    detection = {
        'band': band,
        'expected_gap': 20.0,
        'vernier_tick_roi': (20, 101),
    }

    records = vernier_scale._recover_binary_top_evidence_ticks(
        detection, formal, 0, band.shape[1]
    )

    assert {round(record['formal_x_projection']) for record in records
            if record.get('source') == 'formal_tick_binary_evidence'} == {
                20, 40, 60
            }
    assert any(round(record['x_projection']) == 100 and
               record['source'] == 'formal_projection_unmatched'
               for record in records)


def test_formal_recovery_promotes_only_periodic_leading_binary_evidence():
    band = np.zeros((48, 180), dtype=np.uint8)
    for x in (20, 40, 60, 80, 100, 120, 140):
        band[:36, x] = 255
    detection = {
        'band': band,
        'expected_gap': 20.0,
        'vernier_tick_roi': (18, 142),
        'tick_candidates': [
            {'x_projection': x, 'component': None}
            for x in (80, 100, 120, 140)
        ],
    }

    candidates, recovery = vernier_scale._promote_leading_binary_evidence_candidates(
        detection
    )

    assert recovery['applied'] is True
    assert recovery['promoted_count'] == 3
    assert [candidate['x_projection'] for candidate in candidates] == pytest.approx(
        [20, 40, 60, 80, 100, 120, 140], abs=2
    )
    assert all(
        candidate.get('source') == 'observed_binary_leading_recovery'
        for candidate in candidates[:3]
    )


def test_formal_recovery_rejects_leading_evidence_far_from_left_valley():
    band = np.zeros((48, 180), dtype=np.uint8)
    for x in (40, 60, 80, 100, 120, 140):
        band[:36, x] = 255
    detection = {
        'band': band,
        'expected_gap': 20.0,
        'vernier_tick_roi': (10, 142),
        'tick_candidates': [
            {'x_projection': x, 'component': None}
            for x in (80, 100, 120, 140)
        ],
    }

    candidates, recovery = vernier_scale._promote_leading_binary_evidence_candidates(
        detection
    )

    assert recovery['applied'] is False
    assert [candidate['x_projection'] for candidate in candidates] == [
        80, 100, 120, 140
    ]


def test_per_tick_diagnostics_keep_an_entry_for_every_formal_candidate():
    band = np.zeros((40, 40), dtype=np.uint8)
    band[:, 8] = 255

    _corrected, traces, states = _build_per_tick_straightened_band(
        band, [8, 28], observed_period=12.0, include_candidate_states=True
    )

    assert len(states) == 2
    assert len(traces) == 1
    assert [state['status'] for state in states] == ['traced', 'untraced']
    assert states[1]['reason'] is not None


def test_tick_subpixel_refinement_uses_local_refined_center(monkeypatch):
    band = np.zeros((20, 30), dtype=np.uint8)
    band[:, 12] = 255
    gray_band = np.full((20, 30), 255, dtype=np.uint8)
    detection = {
        'band': band,
        'gray_band': gray_band,
        'band_y1': 0,
        'x1': 0,
        'expected_gap': 10.0,
        'tick_candidates': [{
            'x_projection': 10,
            'projection_strength': 1.0,
            'component_id': None,
            'component': None,
            'spacing_error': 0.0,
        }],
    }
    called_with = []

    monkeypatch.setattr(
        vernier_scale,
        '_refine_vernier_tick_from_band',
        lambda *_: {
            'x': 12.0,
            'x_top': 12.0,
            'x_bottom': 12.0,
            'y_start': 0,
            'y_end': 19,
            'slope': 0.0,
        },
    )
    monkeypatch.setattr(
        vernier_scale,
        'refine_tick_x_subpixel',
        lambda _gray, center, _y1, _y2: called_with.append(center) or center + 0.25,
    )

    ticks = vernier_scale._build_ticks_from_band_detection(detection)

    assert called_with == [12]
    assert ticks[0]['x_projection'] == 10
    assert ticks[0]['x_refined'] == pytest.approx(12.0)
    assert ticks[0]['x_precise'] == pytest.approx(12.25)


def test_detailed_per_tick_correction_does_not_change_reading_or_zero_line():
    image = cv2.imread(str(Path('tupian') / '72.52.jpg'))
    assert image is not None

    detailed = CaliperPipeline(fast_mode=False)
    detailed_result = detailed.run(image)
    fast = CaliperPipeline(fast_mode=True)
    fast_result = fast.run(image)

    detailed_detection = detailed.step_results['vernier']['vernier_band_detection']
    fast_detection = fast.step_results['vernier']['vernier_band_detection']
    correction = detailed_detection['per_tick_correction']
    assert correction is not None
    assert correction['trace_count'] > 0
    assert correction['continuous_band'].shape == correction['straightened_band'].shape
    assert correction['synthetic_gap_mask'].shape == correction['straightened_band'].shape
    assert np.count_nonzero(correction['continuous_band']) >= np.count_nonzero(
        correction['straightened_band']
    )
    assert correction['display_trace_count'] == correction['trace_count']
    assert fast_detection['per_tick_correction'] is None
    assert detailed_result.total == fast_result.total
    assert detailed_result.main_scale == fast_result.main_scale
    assert detailed_result.vernier_scale == fast_result.vernier_scale
    assert detailed_result.precision == fast_result.precision
    assert detailed_result.confidence == fast_result.confidence
    assert detailed.step_results['vernier']['zero_x'] == pytest.approx(
        fast.step_results['vernier']['zero_x']
    )

    def tick_signature(ticks):
        return [
            (
                int(tick['x_projection']),
                round(float(tick.get('x_refined', tick['x_projection'])), 6),
                round(float(tick.get('x_precise', tick['x_projection'])), 6),
                int(tick.get('length', 0)),
            )
            for tick in ticks
        ]

    assert tick_signature(detailed.step_results['main']['main_ticks']) == \
        tick_signature(fast.step_results['main']['main_ticks'])
    assert tick_signature(detailed.step_results['vernier']['vernier_ticks']) == \
        tick_signature(fast.step_results['vernier']['vernier_ticks'])
    detailed_alignment = detailed.step_results['vernier']['alignment_info']
    fast_alignment = fast.step_results['vernier']['alignment_info']
    assert detailed_alignment['best_index'] == fast_alignment['best_index']
    assert detailed_alignment['continuous_index'] == pytest.approx(
        fast_alignment['continuous_index']
    )
    assert detailed_alignment['best_error_px'] == pytest.approx(
        fast_alignment['best_error_px']
    )
    assert detailed.step_results['main']['main_reading'] == \
        fast.step_results['main']['main_reading']
    assert detailed.step_results['vernier']['vernier_reading'] == \
        fast.step_results['vernier']['vernier_reading']


def test_detailed_correction_recovers_periodic_binary_candidates_for_140():
    image = cv2.imread(str(Path('tupian') / '140.00.jpg'))
    assert image is not None

    pipeline = CaliperPipeline(fast_mode=False)
    pipeline.run(image)
    vernier = pipeline.step_results['vernier']
    detection = vernier['vernier_band_detection']
    correction = detection['per_tick_correction']

    formal_count = len(vernier.get('vernier_ticks', []))
    assert correction['formal_candidate_count'] == formal_count
    assert correction['candidate_count'] > formal_count
    assert correction['recovered_candidate_count'] > 0
    assert correction['trace_count'] >= correction['candidate_count'] - 3
    assert correction['untraced_count'] <= 3
    assert len(correction['candidate_states']) == correction['candidate_count']
    assert correction['trace_count'] + correction['untraced_count'] == \
        correction['candidate_count']
    assert any(
        state.get('source') == 'formal_projection_unmatched'
        for state in correction['candidate_states']
    )
