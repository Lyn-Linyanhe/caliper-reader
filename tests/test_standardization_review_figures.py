from pathlib import Path

import cv2
import numpy as np

from tools.export_standardization_review_figures import (
    export_review_figures,
    render_review_figure,
)


def _standardization(width=80):
    response = np.zeros(width, dtype=float)
    response[[12, 28, 44, 60]] = [1.0, 1.5, 1.0, 1.5]
    return {
        'width': width,
        'x_offset': 0,
        'curves': {
            'raw_projection': response.copy(),
            'support': response.copy(),
            'normalized_response': response,
        },
        'ticks': [
            {'x': 12.0, 'x_local': 12.0, 'x_projection': 12.0},
            {'x': 28.0, 'x_local': 28.0, 'x_projection': 28.0},
            {'x': 44.0, 'x_local': 44.0, 'x_projection': 44.0},
            {'x': 60.0, 'x_local': 60.0, 'x_projection': 60.0},
        ],
        'classification': {'mode': 'two_clusters', 'centers': [1.0, 2.0]},
    }


def _split_result():
    return {
        'split_y': 25,
        'region_main': {
            'tick_band': (7, 20),
            'tick_band_global': (7, 20),
        },
        'region_vernier': {
            'tick_band': (2, 14),
            'tick_band_global': (27, 39),
        },
    }


def test_render_review_figure_uses_rotated_crop_and_curve_domain():
    rotated = np.full((50, 80, 3), 160, dtype=np.uint8)
    split = _split_result()
    result = {
        'standardization': _standardization(),
        'main_ticks': [
            {'x': 12}, {'x': 28}, {'x': 44}, {'x': 60},
        ],
    }

    image, metadata = render_review_figure(
        rotated, split, 'main', result, '30.00.jpg'
    )

    assert image.ndim == 3
    assert image.shape[2] == 3
    assert image.shape[0] > 50
    assert metadata['source'] == 'orient.rotated_color'
    assert metadata['crop_y'] == [7, 20]
    assert metadata['crop_x'] == [0, 80]
    assert metadata['curve_x_local'] == [0, 80]
    assert metadata['content_x'] == [48, 1182]
    assert metadata['curve_content_x'] == metadata['content_x']
    assert metadata['image_content_x'] == metadata['content_x']
    assert metadata['standardization_present'] is True
    assert metadata['tick_count'] == 4
    assert metadata['tick_screen_x_image'] == metadata['tick_screen_x_curve']


def test_vernier_review_marks_zero_line_and_uses_vernier_band():
    rotated = np.full((50, 80, 3), 160, dtype=np.uint8)
    split = _split_result()
    split['vernier_band_detection'] = {
        'x1': 0,
        'x2': 80,
        'band_y1': 2,
        'band_y2': 14,
        'vernier_tick_roi': (8, 68),
    }
    result = {
        'standardization': _standardization(),
        'vernier_ticks': [
            {'x': 12}, {'x': 28}, {'x': 44}, {'x': 60},
        ],
        'zero_x': 28.0,
        'vernier_band_detection': split['vernier_band_detection'],
    }

    image, metadata = render_review_figure(
        rotated, split, 'vernier', result, '72.52.jpg'
    )

    assert image.shape[0] > 50
    assert metadata['crop_y'] == [27, 39]
    assert metadata['crop_x'] == [8, 68]
    assert metadata['curve_x_local'] == [8, 68]
    assert metadata['curve_content_x'] == metadata['image_content_x']
    assert metadata['zero_x'] == 28.0
    assert metadata['zero_in_crop'] is True
    assert metadata['zero_screen_x_image'] == metadata['zero_screen_x_curve']


def test_review_figure_maps_refined_local_positions_to_both_panels():
    rotated = np.full((50, 80, 3), 160, dtype=np.uint8)
    standardization = _standardization()
    standardization['ticks'][0]['x_projection'] = 10.0
    standardization['ticks'][0]['x_local'] = 14.0
    result = {
        'standardization': standardization,
        'main_ticks': [{'x': 14}],
    }

    _image, metadata = render_review_figure(
        rotated, _split_result(), 'main', result, '30.00.jpg'
    )

    assert metadata['tick_screen_x_image'][0] == metadata['tick_screen_x_curve'][0]
    assert metadata['tick_screen_x_image'][0] == 48 + round((14 / 79) * (1182 - 48))


def test_missing_standardization_renders_labeled_placeholder():
    rotated = np.full((50, 80, 3), 160, dtype=np.uint8)
    result = {'standardization': None, 'main_ticks': []}

    image, metadata = render_review_figure(
        rotated, _split_result(), 'main', result, '40.20.jpg'
    )

    assert image.size > 0
    assert metadata['standardization_present'] is False
    assert metadata['error'] == 'standardization_unavailable'


def test_export_review_figures_writes_two_files_per_sample(tmp_path, monkeypatch):
    from tools import export_standardization_review_figures as exporter

    class FakePipeline:
        def __init__(self, fast_mode=False):
            self.step_results = {
                'orient': {'rotated_color': np.zeros((50, 80, 3), dtype=np.uint8)},
                'split': _split_result(),
                'main': {
                    'standardization': _standardization(),
                    'main_ticks': [{'x': 12}],
                },
                'vernier': {
                    'standardization': _standardization(),
                    'vernier_ticks': [{'x': 28}],
                    'zero_x': 28.0,
                    'vernier_band_detection': {
                        'x1': 0, 'x2': 80, 'band_y1': 2, 'band_y2': 14,
                        'vernier_tick_roi': (8, 68),
                    },
                },
            }

        def run(self, image):
            return type('Result', (), {'total': 1.0})()

    monkeypatch.setattr(exporter, 'CaliperPipeline', FakePipeline)
    monkeypatch.setattr(
        exporter, 'read_image',
        lambda path: np.zeros((50, 80, 3), dtype=np.uint8),
    )

    report = export_review_figures(
        tmp_path, tmp_path / 'out', ['sample.jpg']
    )

    assert (tmp_path / 'out' / '01_sample_main_review.png').is_file()
    assert (tmp_path / 'out' / '01_sample_vernier_review.png').is_file()
    assert (tmp_path / 'out' / 'standardization_review_summary.json').is_file()
    assert report['samples'][0]['reading_mm'] == 1.0


def test_review_metadata_exposes_one_half_open_image_curve_domain():
    rotated = np.full((50, 80, 3), 160, dtype=np.uint8)
    result = {
        'standardization': _standardization(),
        'main_ticks': [{'x': 12}, {'x': 28}, {'x': 44}, {'x': 60}],
    }

    _image, metadata = render_review_figure(
        rotated, _split_result(), 'main', result, '30.00.jpg'
    )

    assert metadata['display_domain'] == {'start': 0, 'end': 80}
    assert metadata['image_source_x'] == [0, 80]
    assert metadata['curve_source_x'] == [0, 80]
    assert metadata['source_span'] == metadata['curve_span'] == 80


def test_review_metadata_keeps_partial_crop_spans_equal():
    rotated = np.full((50, 100, 3), 160, dtype=np.uint8)
    split = _split_result()
    standardization = _standardization(width=100)
    standardization['ticks'] = [
        {'x': 20.0, 'x_local': 20.0, 'x_projection': 20.0},
        {'x': 80.0, 'x_local': 80.0, 'x_projection': 80.0},
    ]
    result = {'standardization': standardization, 'main_ticks': []}

    _image, metadata = render_review_figure(
        rotated, split, 'main', result, '30.00.jpg'
    )

    assert metadata['source_span'] == metadata['curve_span']
    assert metadata['image_source_x'][1] - metadata['image_source_x'][0] == 100
    assert metadata['curve_source_x'][1] - metadata['curve_source_x'][0] == 100


def test_review_exposes_one_shared_marker_geometry():
    rotated = np.full((50, 100, 3), 160, dtype=np.uint8)
    standardization = _standardization(width=100)
    standardization['ticks'] = [
        {'x': 12.0, 'x_local': 12.0, 'x_projection': 12.0},
        {'x': 28.0, 'x_local': 28.0, 'x_projection': 28.0},
        {'x': 44.0, 'x_local': 44.0, 'x_projection': 44.0},
        {'x': 60.0, 'x_local': 60.0, 'x_projection': 60.0},
    ]
    _image, metadata = render_review_figure(
        rotated, _split_result(), 'main',
        {'standardization': standardization}, '30.00.jpg'
    )

    assert metadata['image_content_x'] == metadata['curve_content_x']
    assert metadata['shared_content_x'] == metadata['image_content_x']
    assert metadata['shared_tick_screen_x'] == metadata['tick_screen_x_image']
    assert metadata['shared_tick_screen_x'] == metadata['tick_screen_x_curve']
    assert metadata['shared_zero_screen_x'] == metadata['zero_screen_x_image']
    assert metadata['shared_zero_screen_x'] == metadata['zero_screen_x_curve']


def test_review_metadata_reports_observed_standardization_quality():
    rotated = np.full((50, 80, 3), 160, dtype=np.uint8)
    standardization = _standardization(width=80)
    standardization['classification'].update({
        'formal_tick_count': 4,
        'display_tick_count': 4,
        'display_spacing_median': 16.0,
        'display_min_gap': 16.0,
        'display_max_gap': 16.0,
    })
    result = {
        'standardization': standardization,
        'main_ticks': [{'x': 12}, {'x': 28}, {'x': 44}, {'x': 60}],
    }

    _image, metadata = render_review_figure(
        rotated, _split_result(), 'main', result, '30.00.jpg'
    )

    assert metadata['formal_tick_count'] == 4
    assert metadata['display_tick_count'] == 4
    assert 0.0 < metadata['display_coverage'] <= 1.0
    assert metadata['standardization_status'] in {
        'observed_complete',
        'partial',
    }


def test_review_metadata_exposes_binary_acceptance_and_stem_rendering():
    rotated = np.full((50, 80, 3), 160, dtype=np.uint8)
    standardization = _standardization(width=80)
    standardization['classification'].update({
        'formal_tick_count': 4,
        'display_tick_count': 4,
        'binary_evidence_available': True,
        'direction_trace_coverage': 1.0,
        'trace_support_coverage': 1.0,
        'binary_support_coverage': 1.0,
        'spacing_consistency': 1.0,
        'spacing_max_ratio': 1.0,
        'cluster_balance': 1.0,
        'acceptance_status': 'complete',
        'response_kernel': 'center_stem',
    })
    _image, metadata = render_review_figure(
        rotated,
        _split_result(),
        'main',
        {'standardization': standardization},
        '30.00.jpg',
    )

    assert metadata['acceptance_status'] == 'complete'
    assert metadata['binary_evidence_available'] is True
    assert metadata['direction_trace_coverage'] == 1.0
    assert metadata['spacing_consistency'] == 1.0
    assert metadata['cluster_balance'] == 1.0
    assert metadata['response_kernel'] == 'center_stem'
    assert metadata['curve_line_thickness'] == 1


def test_review_domain_ignores_isolated_outlier_tick():
    width = 220
    response = np.zeros(width, dtype=float)
    regular_xs = [10.0, 26.0, 42.0, 58.0, 74.0, 90.0]
    for index, value in enumerate(regular_xs):
        response[int(value)] = 1.0 + (index % 2) * 0.5
    standardization = {
        'width': width,
        'x_offset': 0,
        'curves': {
            'raw_projection': response.copy(),
            'support': response.copy(),
            'normalized_response': response,
        },
        'ticks': [
            {'x': value, 'x_local': value, 'x_projection': value}
            for value in regular_xs + [180.0]
        ],
        'classification': {},
    }
    rotated = np.full((50, width, 3), 160, dtype=np.uint8)
    _image, metadata = render_review_figure(
        rotated,
        _split_result(),
        'main',
        {'standardization': standardization},
        'outlier.jpg',
    )

    # The isolated x=180 candidate must not stretch the review crop across
    # the blank/hardware region.  Both panels still use the same span.
    assert metadata['tick_run']['excluded_count'] == 1
    assert metadata['tick_run']['count'] == len(regular_xs)
    assert metadata['source_span'] == metadata['curve_span']
    assert metadata['curve_x_local'][1] < 180


def test_review_acceptance_uses_visible_tick_run_and_preserves_raw_warning():
    width = 220
    response = np.zeros(width, dtype=float)
    regular_xs = [10.0, 26.0, 42.0, 58.0, 74.0, 90.0]
    standardization = {
        'width': width,
        'x_offset': 0,
        'curves': {
            'raw_projection': response.copy(),
            'support': response.copy(),
            'normalized_response': response,
        },
        'ticks': [
            {'x': value, 'x_local': value, 'x_projection': value}
            for value in regular_xs + [180.0]
        ],
        'classification': {
            'formal_tick_count': 7,
            'display_tick_count': 7,
            'acceptance_status': 'irregular_spacing',
            'display_spacing_median': 16.0,
            'display_min_gap': 16.0,
            'display_max_gap': 122.0,
        },
    }
    rotated = np.full((50, width, 3), 160, dtype=np.uint8)
    _image, metadata = render_review_figure(
        rotated,
        _split_result(),
        'main',
        {'standardization': standardization},
        'outlier.jpg',
    )

    assert metadata['raw_acceptance_status'] == 'irregular_spacing'
    assert metadata['acceptance_status'] == 'complete'
    assert metadata['domain_tick_count'] == len(regular_xs)
    assert metadata['domain_spacing_max_ratio'] < 1.1
