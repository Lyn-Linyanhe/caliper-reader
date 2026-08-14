import numpy as np

from caliper.main_scale import (
    _recover_main_tick_extents_from_full_binary,
    _select_ocr_anchor_tick_top,
)


def _tick(x, y_start, y_end, is_long=False):
    return {
        'x': x,
        'y_start': y_start,
        'y_end': y_end,
        'y_mid': (y_start + y_end) // 2,
        'length': y_end - y_start,
        'is_long': is_long,
    }


def test_recovers_only_the_connected_upper_extent_of_confirmed_main_ticks():
    binary = np.zeros((48, 36), dtype=np.uint8)
    binary[4:28, 9:12] = 255
    binary[1:12, 24:27] = 255
    ticks = [_tick(10, 14, 27), _tick(20, 14, 27)]

    recovered = _recover_main_tick_extents_from_full_binary(binary, ticks)

    assert recovered[0]['y_start'] == 4
    assert recovered[0]['y_end'] == 27
    assert recovered[1]['y_start'] == 14
    assert recovered[1]['y_end'] == 27


def test_ocr_anchor_keeps_the_existing_default_when_long_ticks_are_available():
    ticks = [
        _tick(10, 340, 430, True),
        _tick(20, 360, 440, True),
        _tick(30, 400, 445, True),
        _tick(40, 425, 445, False),
        _tick(50, 430, 445, False),
    ]

    assert _select_ocr_anchor_tick_top(ticks) == 427


def test_ocr_anchor_can_prefer_the_upper_part_of_recovered_long_ticks():
    ticks = [
        _tick(10, 340, 430, True),
        _tick(20, 360, 440, True),
        _tick(30, 400, 445, True),
        _tick(40, 425, 445, False),
        _tick(50, 430, 445, False),
    ]

    assert _select_ocr_anchor_tick_top(ticks, prefer_long_ticks=True) == 350


def test_ocr_anchor_keeps_the_existing_fallback_when_long_ticks_are_unavailable():
    ticks = [_tick(10, 400, 440), _tick(20, 410, 445), _tick(30, 420, 448)]

    assert _select_ocr_anchor_tick_top(ticks) == 417
