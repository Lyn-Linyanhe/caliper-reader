import cv2
import numpy as np

from caliper.main_scale import _standardize_tick_response
from caliper.utils import refine_ticks_by_spacing
from caliper.vernier_rectify import rectify_vernier_region


def test_main_standard_response_remains_available_for_diagnostics():
    response = _standardize_tick_response(
        80,
        [
            {'x_projection': 10, 'length': 8},
            {'x_projection': 30, 'length': 12},
        ],
        np.ones(80, dtype=float) * 10.0,
    )

    assert response.shape == (80,)
    assert float(response[10]) > 0.0
    assert float(response[30]) > 0.0


def test_main_standard_response_uses_refined_tick_position():
    support = np.zeros(80, dtype=float)
    support[12] = 10.0
    response = _standardize_tick_response(
        80,
        [{'x_projection': 10, 'x_precise': 12.0, 'length': 8}],
        support,
    )

    assert response[12] > response[10]


def test_spacing_refinement_is_available_as_an_opt_in_research_helper():
    binary = np.zeros((24, 80), dtype=np.uint8)
    for x in (10, 30, 50, 70):
        binary[2:22, x] = 255

    refined = refine_ticks_by_spacing(
        np.asarray([10.0, 30.0, 50.0, 90.0]),
        binary,
        gap_factor=1.5,
    )

    assert refined.ndim == 1
    assert np.any(np.isclose(refined, 70.0, atol=1.0))


def test_spacing_refinement_does_not_invent_unsupported_ticks():
    binary = np.zeros((24, 80), dtype=np.uint8)
    for x in (10, 30, 50):
        binary[2:22, x] = 255

    refined = refine_ticks_by_spacing(
        np.asarray([10.0, 30.0, 50.0, 90.0]),
        binary,
        gap_factor=1.5,
    )

    assert not np.any(np.isclose(refined, 70.0, atol=1.0))


def test_whole_vernier_rectification_helper_remains_available():
    gray = np.full((32, 96), 220, dtype=np.uint8)
    gray[4:12, 24:72] = 245
    binary = np.zeros_like(gray)
    binary[4:12, 24:72] = 255
    result = rectify_vernier_region(
        {'image': gray, 'binary': binary, 'x_offset': 0},
    )

    assert set(('region', 'color', 'angle', 'matrix', 'inverse_matrix')) <= set(result)
    assert result['region']['image'].ndim == 2


def test_research_artifacts_are_not_formal_reading_outputs():
    from caliper.pipeline import CaliperPipeline

    image = cv2.imread('tupian/72.52.jpg')
    assert image is not None
    pipeline = CaliperPipeline(fast_mode=False)
    result = pipeline.run(image)
    vernier = pipeline.step_results.get('vernier', {})
    detection = vernier.get('vernier_band_detection') or {}

    assert 'total' not in detection
    assert result.total is not None
    assert detection.get('per_tick_correction') is not None


def test_vernier_tick_geometry_contract_for_future_standardization():
    """Keep the observed geometry consumed by future curve/correction work."""
    from caliper.pipeline import CaliperPipeline

    image = cv2.imread('tupian/72.52.jpg')
    assert image is not None

    pipeline = CaliperPipeline(fast_mode=False)
    result = pipeline.run(image)
    ticks = pipeline.step_results['vernier'].get('vernier_ticks', [])

    assert result.total is not None
    assert len(ticks) >= 3
    required = {
        'x_projection', 'x_refined', 'x_precise',
        'length', 'component_id', 'component_height',
        'component_bottom_y', 'x_top', 'x_bottom', 'fit_slope',
    }
    assert required <= set(ticks[0])

    correction = pipeline.step_results['vernier']['vernier_band_detection'][
        'per_tick_correction'
    ]
    assert {
        'traces', 'candidate_states', 'straightened_band',
        'continuous_band', 'synthetic_gap_mask', 'display_traces',
    } <= set(correction)
    assert correction['output_kind'] == 'binary_tick_mask'
    assert 'straightened_gray_band' not in correction
