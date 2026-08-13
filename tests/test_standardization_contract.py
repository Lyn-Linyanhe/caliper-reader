import numpy as np

from caliper.standardization import (
    build_standardization_result,
    empty_standardization,
)


def test_empty_standardization_has_three_width_aligned_curves():
    result = empty_standardization(12, x_offset=37)

    assert result['version'] == 1
    assert result['width'] == 12
    assert result['x_offset'] == 37
    assert set(result['curves']) == {
        'raw_projection', 'support', 'normalized_response'
    }
    assert all(value.shape == (12,) for value in result['curves'].values())
    assert result['ticks'] == []
    assert result['classification']['mode'] == 'unknown'


def test_builder_sanitizes_curves_and_keeps_tick_evidence():
    result = build_standardization_result(
        width=5,
        x_offset=10,
        raw_projection=[0, 1, 2, 3, 4, 99],
        support=[1, 2, 3],
        normalized_response=[0, 1, 0, 0, 0],
        tick_records=[{
            'x': 2,
            'x_projection': 2,
            'measured_length': 14,
            'support_value': 3,
            'normalized_value': 1.0,
            'class': 'short',
            'quality': 0.8,
        }],
        classification={'mode': 'single', 'centers': [14], 'counts': [1]},
    )

    assert result['curves']['raw_projection'].shape == (5,)
    assert result['curves']['support'].shape == (5,)
    assert result['curves']['normalized_response'].shape == (5,)
    assert result['ticks'][0]['x'] == 2.0
    assert result['classification']['mode'] == 'single'


def test_builder_replaces_nonfinite_curve_values_with_zero():
    result = build_standardization_result(
        width=3,
        x_offset=0,
        raw_projection=[np.nan, np.inf, 1],
        support=None,
        normalized_response=None,
        tick_records=[],
        classification=None,
    )

    assert np.array_equal(result['curves']['raw_projection'], [0.0, 0.0, 1.0])
    assert np.array_equal(result['curves']['support'], [0.0, 0.0, 0.0])
    assert result['classification']['mode'] == 'unknown'
