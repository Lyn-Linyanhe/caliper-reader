import unittest

from caliper.merger import (
    _count_main_ticks_between_label_and_zero,
    _group_main_ocr_labels,
    _select_main_label_for_zero,
)
from caliper.result import DigitInfo


def candidate(value: int, x1: int, x2: int) -> dict:
    digit = DigitInfo(
        x=(x1 + x2) // 2,
        y=20,
        value=value,
        text=str(value),
        confidence=0.9,
        bbox=(x1, 0, x2, 40),
    )
    return {
        "digit": digit,
        "value": value,
        "text": str(value),
        "confidence": 0.9,
        "bbox": digit.bbox,
        "cc_confidence": 0.9,
        "center_x": digit.x,
        "source": "single_char",
    }


def label(value: int, ref_tick_x: float) -> dict:
    return {
        "value": value,
        "text": str(value),
        "ref_tick_x": ref_tick_x,
        "confidence": 0.9,
        "cc_confidence": 0.9,
    }


class MainOcrGroupingTests(unittest.TestCase):
    def test_uses_previous_integer_for_adjacent_right_label(self):
        selected, strategy = _select_main_label_for_zero(
            [label(8, 108.0)], zero_x=98.0, main_gap=12.0
        )

        self.assertEqual(selected["value"], 7)
        self.assertEqual(strategy, "right_of_zero_minus_one")

    def test_rejects_right_label_beyond_one_main_gap(self):
        selected, strategy = _select_main_label_for_zero(
            [label(8, 125.0)], zero_x=98.0, main_gap=12.0
        )

        self.assertIsNone(selected)
        self.assertIsNone(strategy)

    def test_prefers_actual_left_label_over_right_fallback(self):
        selected, strategy = _select_main_label_for_zero(
            [label(7, 84.0), label(8, 108.0)], zero_x=98.0, main_gap=12.0
        )

        self.assertEqual(selected["value"], 7)
        self.assertEqual(strategy, "left_of_zero")

    def test_groups_11_at_33px_gap(self):
        labels = _group_main_ocr_labels(
            [candidate(1, 1871, 1891), candidate(1, 1924, 1944)],
            [{"x": 1908}],
            main_gap=48.0,
        )

        self.assertEqual(
            [(label["text"], label["source"]) for label in labels],
            [("11", "grouped_2digit")],
        )

    def test_does_not_group_11_beyond_075_main_gap(self):
        labels = _group_main_ocr_labels(
            [candidate(1, 1871, 1891), candidate(1, 1928, 1948)],
            [{"x": 1881}, {"x": 1938}],
            main_gap=48.0,
        )

        self.assertTrue(all(label["source"] == "single_char" for label in labels))

    def test_counts_main_tick_at_subpixel_matched_zero_line(self):
        count = _count_main_ticks_between_label_and_zero(
            [433.0, 480.0, 524.0, 570.0, 617.0, 662.0],
            ref_x=524.0,
            zero_x=616.5,
            main_gap=46.0,
        )

        self.assertEqual(count, 2)
