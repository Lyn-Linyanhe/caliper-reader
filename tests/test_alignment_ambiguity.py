import numpy as np
import pytest

import caliper.vernier_scale as vernier_scale
from caliper.merger import _with_alignment_totals
from caliper.reading_display import format_alignment_ambiguity
from caliper.vernier_scale import (
    _make_alignment_ambiguity,
    find_best_alignment,
)


def test_ambiguity_uses_only_the_best_adjacent_tick():
    info = _make_alignment_ambiguity(
        np.array([0.65, 0.20, 0.10, 0.10]),
        best_idx=3,
        precision=0.02,
        main_gap=46.0,
    )

    assert info['primary_index'] == 3
    assert info['reference_index'] == 2
    assert info['primary_reading'] == 0.06
    assert info['reference_reading'] == 0.04
    assert info['margin_px'] == pytest.approx(0.0)
    assert info['margin_px'] <= info['threshold_px']


def test_ambiguity_rejects_a_quarter_pixel_advantage():
    info = _make_alignment_ambiguity(
        np.array([0.65, 0.20, 0.35, 0.10]),
        best_idx=3,
        precision=0.02,
        main_gap=46.0,
    )

    assert info is None


def test_parabolic_interpolation_cannot_emit_a_non_002_reading(monkeypatch):
    errors = iter([0.70, 0.10, 0.30])
    monkeypatch.setattr(
        vernier_scale,
        '_compute_alignment_error',
        lambda *_args, **_kwargs: next(errors),
    )
    ticks = [{'x': 0.0}, {'x': 2.0}, {'x': 4.0}]

    reading, aligned, _confidence, info = find_best_alignment(
        ticks,
        precision=0.02,
        main_ticks=[{'x': 0.0}],
        main_gap=46.0,
    )

    assert reading == 0.02
    assert aligned is ticks[1]
    assert (reading / 0.02).is_integer()
    assert info['continuous_index'] == pytest.approx(1.25)


def test_reference_total_never_replaces_primary_total():
    info = _with_alignment_totals(
        60.0,
        {
            'primary_reading': 0.04,
            'reference_reading': 0.02,
            'primary_error_px': 0.31,
            'reference_error_px': 0.36,
        },
    )

    assert info['primary_total'] == 60.04
    assert info['reference_total'] == 60.02


def test_alignment_ambiguity_formatter_contains_both_totals_and_errors():
    text = format_alignment_ambiguity({
        'primary_total': 60.04,
        'reference_total': 60.02,
        'primary_error_px': 0.31,
        'reference_error_px': 0.36,
    })

    assert '60.04 mm' in text
    assert '60.02 mm' in text
    assert '0.31 / 0.36 px' in text
    assert format_alignment_ambiguity(None) is None
