import numpy as np

from caliper.vernier_scale import _build_length_clustered_standard_response


def _ticks(lengths):
    return [
        {'x_projection': 10 + index * 10, 'length': length}
        for index, length in enumerate(lengths)
    ]


def test_length_clustered_response_marks_separated_lengths_as_two_clusters():
    response, info = _build_length_clustered_standard_response(
        100, _ticks([10, 11, 10, 11, 20, 21, 20, 21]), 0
    )

    assert info['mode'] == 'two_length_clusters'
    assert info['cluster_counts'] == [4, 4]
    assert info['classification_mode'] == 'two_clusters'
    assert info['centers'] == info['cluster_centers']
    assert info['counts'] == info['cluster_counts']
    assert info['separation'] > 0.0
    assert info['threshold'] is None
    assert response[10] == 1.0
    assert response[50] == 1.5


def test_length_clustered_response_rejects_nearly_uniform_lengths():
    response, info = _build_length_clustered_standard_response(
        100, _ticks([10, 10, 11, 10, 11, 10]), 0
    )

    assert info['mode'] == 'single_length_cluster'
    assert set(response[10 + index * 10] for index in range(6)) == {1.0}


def test_length_clustered_response_rejects_too_few_ticks():
    _response, info = _build_length_clustered_standard_response(
        100, _ticks([10, 20, 10, 20, 10]), 0
    )

    assert info['mode'] == 'single_length_cluster'


def test_length_clustered_response_uses_refined_tick_position():
    ticks = [
        {
            'x_projection': 10 + index * 10,
            'x_precise': 12.0 + index * 10,
            'length': 10,
        }
        for index in range(6)
    ]
    response, _info = _build_length_clustered_standard_response(100, ticks, 0)

    assert response[12] > response[10]


def test_length_clustered_response_uses_center_stems_for_pixel_alignment():
    """The normalized curve encodes length by amplitude, not fake x-width."""
    ticks = _ticks([10, 10, 10, 20, 20, 20])
    response, info = _build_length_clustered_standard_response(100, ticks, 0)

    assert info['response_kernel'] == 'center_stem'
    for tick in ticks:
        center = int(tick['x_projection'])
        assert response[center] > 0.0
        assert response[max(0, center - 2)] == 0.0
        assert response[min(response.size - 1, center + 2)] == 0.0


def test_vernier_standardization_builds_width_aligned_observed_curves():
    from caliper.vernier_scale import _build_vernier_standardization

    ticks = [
        {
            'x': 10 + index * 10,
            'x_projection': 10 + index * 10,
            'length': length,
            'component_id': index,
            'component_bottom_y': length,
        }
        for index, length in enumerate([10, 11, 10, 11, 20, 21, 20, 21])
    ]
    detection = {
        'x1': 0,
        'x2': 100,
        'proj_norm': __import__('numpy').zeros(100, dtype=float),
    }

    result = _build_vernier_standardization(detection, ticks)

    assert result['width'] == 100
    assert result['x_offset'] == 0
    assert result['curves']['raw_projection'].shape == (100,)
    assert result['curves']['support'].shape == (100,)
    assert result['curves']['normalized_response'].shape == (100,)
    assert len(result['ticks']) == len(ticks)
    assert result['classification']['mode'] == 'two_clusters'
    assert result['classification']['threshold'] == 15.5


def test_vernier_standardization_records_refined_local_position():
    from caliper.vernier_scale import _build_vernier_standardization

    ticks = [
        {
            'x': 12.0,
            'x_projection': 10.0,
            'x_precise': 12.0,
            'length': 10,
            'component_id': index,
            'component_bottom_y': 10,
        }
        for index in range(6)
    ]
    result = _build_vernier_standardization(
        {'x1': 0, 'x2': 100, 'proj_norm': np.zeros(100, dtype=float)},
        ticks,
    )

    assert result['ticks'][0]['x_local'] == 12.0
    assert result['curves']['normalized_response'][12] > result['curves']['normalized_response'][10]


def test_empty_vernier_result_exposes_standardization_placeholder():
    from caliper.vernier_scale import _empty_vernier_result

    result = _empty_vernier_result('test')

    assert result['standardization'] is None


def test_vernier_standardization_uses_binary_top_evidence_for_sparse_formal_ticks():
    """Display standardization may recover observed strokes without reading."""
    from caliper.vernier_scale import _build_vernier_standardization

    band = np.zeros((100, 240), dtype=np.uint8)
    for index, x in enumerate([20, 60, 100, 140, 180, 220]):
        band[: 70 if index % 3 else 95, x] = 255
    formal_ticks = [
        {
            'x': 20,
            'x_projection': 20,
            'x_precise': 20,
            'length': 95,
        },
        {
            'x': 100,
            'x_projection': 100,
            'x_precise': 100,
            'length': 95,
        },
        {
            'x': 180,
            'x_projection': 180,
            'x_precise': 180,
            'length': 95,
        },
    ]
    result = _build_vernier_standardization(
        {
            'x1': 0,
            'x2': 240,
            'band': band,
            'proj_norm': np.zeros(240, dtype=float),
            'expected_gap': 40.0,
            'vernier_tick_roi': (20, 221),
        },
        formal_ticks,
    )

    assert result['classification']['evidence_source'] == 'binary_top_projection'
    assert result['classification']['display_tick_count'] == 6
    assert result['classification']['display_spacing_median'] == 40.0
    assert result['classification']['display_max_gap'] == 41.0
    assert np.allclose(
        [tick['x_local'] for tick in result['ticks']],
        [20, 60, 100, 140, 180, 220],
        atol=1.0,
    )
    assert sum(tick['source'] == 'binary_top_evidence' for tick in result['ticks']) == 3


def test_vernier_standardization_reports_acceptance_metrics_for_binary_evidence():
    from caliper.vernier_scale import _build_vernier_standardization

    band = np.zeros((100, 240), dtype=np.uint8)
    for index, x in enumerate([20, 60, 100, 140, 180, 220]):
        band[: 70 if index % 2 else 95, x] = 255
    ticks = [
        {
            'x': x,
            'x_projection': x,
            'x_precise': x,
            'length': 95 if index % 2 == 0 else 70,
        }
        for index, x in enumerate([20, 60, 100, 140, 180, 220])
    ]
    result = _build_vernier_standardization(
        {
            'x1': 0,
            'x2': 240,
            'band': band,
            'gray_band': np.full_like(band, 180),
            'proj_norm': np.zeros(240, dtype=float),
            'expected_gap': 40.0,
            'vernier_tick_roi': (20, 221),
        },
        ticks,
    )
    classification = result['classification']

    assert classification['binary_evidence_available'] is True
    assert classification['direction_trace_coverage'] == 1.0
    assert classification['binary_support_coverage'] == 1.0
    assert classification['spacing_consistency'] > 0.95
    assert classification['cluster_balance'] == 1.0
    assert classification['acceptance_status'] == 'complete'


def test_vernier_standardization_uses_component_bottom_to_recover_truncated_long_strokes():
    from caliper.vernier_scale import _build_vernier_standardization

    band = np.zeros((120, 240), dtype=np.uint8)
    ticks = []
    candidates = []
    for index, x in enumerate([20, 60, 100, 140, 180, 220]):
        band[:60, x] = 255
        component_bottom = 100 if index % 2 == 0 else 60
        component = {
            'x_near_seam': float(x),
            'x_left': x,
            'x_right': x,
            'y_start': 0,
            'y_end': component_bottom - 1,
            'area': component_bottom,
        }
        candidates.append({
            'x_projection': x,
            'component': component,
        })
        ticks.append({
            'x': x,
            'x_projection': x,
            'x_precise': x,
            'length': 60,
        })
    result = _build_vernier_standardization(
        {
            'x1': 0,
            'x2': 240,
            'band': band,
            'proj_norm': np.zeros(240, dtype=float),
            'expected_gap': 40.0,
            'vernier_tick_roi': (20, 221),
            'tick_candidates': candidates,
        },
        ticks,
    )

    classification = result['classification']
    assert classification['mode'] == 'two_clusters'
    assert classification['counts'] == [3, 3]
    assert classification['cluster_balance'] == 1.0


def test_sparse_formal_vernier_result_is_not_expanded_without_continuous_coverage():
    from caliper.vernier_scale import _build_vernier_standardization

    band = np.zeros((100, 400), dtype=np.uint8)
    for x in [40, 240]:
        band[:70, x] = 255
    formal_ticks = [
        {'x': 40, 'x_projection': 40, 'x_precise': 40, 'length': 70},
        {'x': 240, 'x_projection': 240, 'x_precise': 240, 'length': 70},
    ]
    result = _build_vernier_standardization(
        {
            'x1': 0,
            'x2': 400,
            'band': band,
            'proj_norm': np.zeros(400, dtype=float),
            'expected_gap': 50.0,
            'vernier_tick_roi': (40, 291),
        },
        formal_ticks,
    )

    assert result['classification']['display_tick_count'] == 2
    assert [round(tick['x_local']) for tick in result['ticks']] == [40, 240]


def test_binary_evidence_accepts_numpy_roi_coordinates():
    from caliper.vernier_scale import _build_vernier_standardization

    band = np.zeros((40, 120), dtype=np.uint8)
    band[:30, 20] = 255
    band[:30, 60] = 255
    band[:30, 100] = 255
    result = _build_vernier_standardization(
        {
            'x1': 0,
            'x2': 120,
            'band': band,
            'proj_norm': np.zeros(120, dtype=float),
            'expected_gap': 40.0,
            'vernier_tick_roi': np.asarray([20, 101]),
        },
        [{'x': 20, 'x_projection': 20, 'x_precise': 20, 'length': 30}],
    )

    assert result['classification']['display_tick_count'] == 3
