import numpy as np

from caliper.main_scale import recognize_main_scale


def _main_region():
    gray = np.full((40, 80), 220, dtype=np.uint8)
    binary = np.zeros_like(gray)
    for x in (10, 20, 30, 40, 50, 60):
        binary[5:35, x] = 255
    return {
        'image': gray,
        'binary': binary,
        'tick_band': (5, 35),
        'y_offset': 0,
        'height': 40,
    }


def test_detailed_main_result_contains_width_aligned_standardization():
    result = recognize_main_scale(_main_region(), make_debug=True)

    standard = result['standardization']
    assert standard['width'] == 80
    assert standard['x_offset'] == 0
    assert standard['curves']['raw_projection'].shape == (80,)
    assert standard['curves']['support'].shape == (80,)
    assert standard['curves']['normalized_response'].shape == (80,)
    assert len(standard['ticks']) == len(result['main_ticks'])


def test_main_standardization_uses_center_stems_and_reports_quality():
    result = recognize_main_scale(_main_region(), make_debug=True)
    standard = result['standardization']
    classification = standard['classification']

    assert classification['response_kernel'] == 'center_stem'
    assert classification['formal_tick_count'] == len(result['main_ticks'])
    assert classification['display_tick_count'] == len(result['main_ticks'])
    assert classification['spacing_consistency'] > 0.95
    assert classification['acceptance_status'] == 'complete'


def test_fast_main_result_does_not_compute_standardization():
    result = recognize_main_scale(_main_region(), make_debug=False)
    assert result['standardization'] is None
