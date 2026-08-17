import unittest
import inspect
from pathlib import Path

import cv2
import numpy as np

from caliper import roi_extract
from caliper.pipeline import CaliperPipeline
from caliper.roi_extract import (
    _build_local_roi_recovery_candidates,
    _guard_x_range_with_full_body,
    _reading_roi_preserves_structure,
    _refined_y_preserves_tick_support,
    _trim_roi_bottom_to_vertical_tick_support,
    _select_reading_roi_candidate,
)
from caliper.vernier_scale import recognize_vernier_scale


class ReadingRoiCandidateSelectionTests(unittest.TestCase):
    def setUp(self):
        self.enhanced = np.zeros((200, 500), dtype=np.uint8)
        self.projection_box = (20, 180, 10, 490)
        self.body_box = (30, 170, 20, 450)
        self.compact_box = (40, 160, 80, 300)
        self.x_diag = {"tick_gap": 10.0}

    def test_rejects_compact_box_that_loses_scale_structure(self):
        selected, info = _select_reading_roi_candidate(
            self.enhanced,
            self.projection_box,
            self.body_box,
            self.x_diag,
            compact_builder=lambda *_: self.compact_box,
            structure_validator=lambda *_: False,
        )

        self.assertEqual(selected, self.body_box)
        self.assertEqual(info["selected_stage"], "body")
        self.assertEqual(info["fallback_reason"], "compact_structure_invalid")

    def test_uses_compact_box_when_scale_structure_is_preserved(self):
        selected, info = _select_reading_roi_candidate(
            self.enhanced,
            self.projection_box,
            self.body_box,
            self.x_diag,
            compact_builder=lambda *_: self.compact_box,
            structure_validator=lambda *_: True,
        )

        self.assertEqual(selected, self.compact_box)
        self.assertEqual(info["selected_stage"], "compact")
        self.assertIsNone(info["fallback_reason"])

    def test_local_recovery_candidates_stay_within_body_and_expand_by_area(self):
        compact = (20, 100, 100, 200)
        body = (20, 100, 40, 260)

        candidates = _build_local_roi_recovery_candidates(compact, body)

        self.assertEqual(
            {candidate["name"] for candidate in candidates},
            {"left_1_3", "left_2_3", "right_1_3", "right_2_3", "both_1_3"},
        )
        self.assertEqual(
            [candidate["added_area"] for candidate in candidates],
            sorted(candidate["added_area"] for candidate in candidates),
        )
        self.assertEqual(len({candidate["box"] for candidate in candidates}), len(candidates))
        for candidate in candidates:
            y1, y2, x1, x2 = candidate["box"]
            self.assertEqual((y1, y2), compact[:2])
            self.assertGreaterEqual(x1, body[2])
            self.assertLessEqual(x2, body[3])
            self.assertLessEqual(x1, compact[2])
            self.assertGreaterEqual(x2, compact[3])

    def test_2200_recovers_only_after_valley_bounded_vernier_failure(self):
        image = cv2.imread(str(Path("tupian") / "22.00.jpg"))
        self.assertIsNotNone(image)

        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(image)

        recovery = result.extra_info.get("roi_recovery")
        self.assertIsNotNone(recovery)
        self.assertTrue(recovery["triggered"])
        self.assertIsNotNone(recovery["selected_candidate"])
        self.assertGreater(result.total, 0.0)
        self.assertLess(abs(result.total - 22.00), 0.15)

    def test_local_recovery_rejects_short_observed_vernier_runs(self):
        self.assertFalse(CaliperPipeline._vernier_result_is_reliable({
            "error": None,
            "vernier_ticks": [{"x": index} for index in range(20)],
            "zero_x": 10.0,
        }))
        self.assertTrue(CaliperPipeline._vernier_result_is_reliable({
            "error": None,
            "vernier_ticks": [{"x": index} for index in range(51)],
            "zero_x": 10.0,
        }))

    def test_3030_skips_short_recovery_and_recovers_full_vernier_range(self):
        image = cv2.imread(str(Path("tupian") / "30.30.jpg"))
        self.assertIsNotNone(image)

        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(image)

        recovery = result.extra_info.get("roi_recovery")
        self.assertIsNotNone(recovery)
        self.assertTrue(recovery["triggered"])
        self.assertGreater(len(recovery["attempts"]), 1)
        self.assertLess(abs(result.total - 30.30), 0.15)

    def test_local_recovery_dataset_and_normal_controls(self):
        cases = {
            "30.00.jpg": (30.00, True),
            "80.90.jpg": (80.90, True),
            "70.00.jpg": (70.00, False),
            "72.52.jpg": (72.52, False),
            "120.60.jpg": (120.60, False),
        }
        for name, (expected, should_recover) in cases.items():
            with self.subTest(image=name):
                image = cv2.imread(str(Path("tupian") / name))
                pipeline = CaliperPipeline(fast_mode=True)
                result = pipeline.run(image)

                self.assertLess(abs(result.total - expected), 0.15)
                self.assertEqual(
                    result.extra_info.get("roi_recovery") is not None,
                    should_recover,
                )

    def test_rejects_10060_compact_box_that_loses_vernier_range(self):
        img = cv2.imread(str(Path("tupian") / "100.60.jpg"))
        self.assertIsNotNone(img)
        h, w = img.shape[:2]
        scale = min(1.0, 1600.0 / float(w))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if scale < 1.0:
            gray = cv2.resize(
                gray, (int(round(w * scale)), int(round(h * scale))),
                interpolation=cv2.INTER_LINEAR,
            )
        enhanced = roi_extract._make_lowres_roi_enhanced(gray)
        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=roi_extract._odd_between(min(gray.shape) // 18, 15, 51),
            C=9,
        )
        y1, y2 = roi_extract._proj_find_y_range(cv2.bitwise_not(binary), gray.shape[0])
        x1, x2, x_diag = roi_extract._proj_find_x_range(
            cv2.bitwise_not(binary), y1, y2, gray.shape[1]
        )
        projection_box = (y1, y2, x1, x2)
        body_box = roi_extract._refine_roi_by_vernier_block(
            enhanced, y1, y2, x1, x2, {}
        )
        self.assertIsNotNone(body_box)
        compact_box = roi_extract._refine_roi_to_reading_window(
            enhanced, *body_box, x_diag
        )
        self.assertIsNotNone(compact_box)

        self.assertTrue(_reading_roi_preserves_structure(enhanced, body_box, x_diag))
        self.assertFalse(_reading_roi_preserves_structure(enhanced, compact_box, x_diag))

    def test_accepts_4020_compact_box_that_keeps_the_vernier_body(self):
        img = cv2.imread(str(Path("tupian") / "40.20.jpg"))
        self.assertIsNotNone(img)
        h, w = img.shape[:2]
        scale = min(1.0, 1600.0 / float(w))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if scale < 1.0:
            gray = cv2.resize(
                gray, (int(round(w * scale)), int(round(h * scale))),
                interpolation=cv2.INTER_LINEAR,
            )
        enhanced = roi_extract._make_lowres_roi_enhanced(gray)
        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=roi_extract._odd_between(min(gray.shape) // 18, 15, 51),
            C=9,
        )
        y1, y2 = roi_extract._proj_find_y_range(cv2.bitwise_not(binary), gray.shape[0])
        x1, x2, x_diag = roi_extract._proj_find_x_range(
            cv2.bitwise_not(binary), y1, y2, gray.shape[1]
        )
        x1, x2, body_info = roi_extract._guard_x_range_with_full_body(
            enhanced, y1, y2, x1, x2, x_diag
        )
        x_diag["full_y_body"] = body_info
        projection_box = (y1, y2, x1, x2)
        refined = roi_extract._refine_roi_by_vernier_block(
            enhanced, *projection_box, {}
        )
        self.assertIsNotNone(refined)
        body_box = (y1, y2, refined[2], refined[3])
        compact_box = roi_extract._refine_roi_to_reading_window(
            enhanced, *body_box, x_diag
        )
        self.assertIsNotNone(compact_box)

        selected, info = _select_reading_roi_candidate(
            enhanced, projection_box, body_box, x_diag
        )
        self.assertTrue(_reading_roi_preserves_structure(enhanced, compact_box, x_diag))
        self.assertEqual(info["selected_stage"], "compact")
        self.assertEqual(selected, compact_box)

    def test_4020_rejects_body_y_refinement_that_cuts_tick_support(self):
        enhanced, projection_box, body_box, _ = self._roi_boxes("40.20.jpg")

        self.assertFalse(
            _refined_y_preserves_tick_support(enhanced, projection_box, body_box)
        )

    def test_4020_vertical_tick_support_trims_only_the_roi_bottom(self):
        enhanced, projection_box, body_box, x_diag = self._roi_boxes("40.20.jpg")
        body_box = (projection_box[0], projection_box[1], body_box[2], body_box[3])

        trimmed = _trim_roi_bottom_to_vertical_tick_support(
            enhanced, body_box, x_diag
        )

        self.assertIsNotNone(trimmed)
        self.assertEqual(trimmed[0], body_box[0])
        self.assertEqual(trimmed[2:], body_box[2:])
        self.assertGreaterEqual(trimmed[1], 650)
        self.assertLessEqual(trimmed[1], 680)

    def test_4030_expands_periodic_tail_to_cover_full_body(self):
        enhanced, projection_box, _, x_diag = self._roi_boxes("40.30.jpg")
        y1, y2, x1, x2 = projection_box

        guarded_x1, guarded_x2, info = _guard_x_range_with_full_body(
            enhanced, y1, y2, x1, x2, x_diag
        )

        self.assertTrue(info["expanded_for_body"])
        self.assertLess(guarded_x1, x1)
        self.assertGreater(guarded_x2, guarded_x1)

    def test_13070_body_roi_recovery_candidate_restores_left_body_and_trims_tail(self):
        image = cv2.imread(str(Path("tupian") / "130.70.jpg"))
        self.assertIsNotNone(image)

        result = roi_extract.locate_roi_lowres(image)
        selection = result["roi_selection"]
        selected = selection["candidate_boxes"]["body"]
        full_body = selection.get("full_y_body")

        self.assertEqual(selection["selected_stage"], "body")
        self.assertIsNotNone(full_body)
        body_range = full_body["body_range"]
        self.assertLess(body_range[0], selected[2])
        self.assertLess(selected[3], body_range[1] + 140)

        candidates = result.get("roi_recovery_candidates", [])
        self.assertTrue(candidates)
        candidate = candidates[0]["box"]
        self.assertLess(candidate[2], selected[2])
        self.assertLess(candidate[3], selected[3])
        self.assertLessEqual(candidate[2], body_range[0] + 20)
        self.assertGreaterEqual(candidate[3], body_range[1])

    def test_13070_short_vernier_run_triggers_body_roi_recovery(self):
        image = cv2.imread(str(Path("tupian") / "130.70.jpg"))
        self.assertIsNotNone(image)

        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(image)

        recovery = result.extra_info.get("roi_recovery")
        self.assertIsNotNone(recovery)
        self.assertTrue(recovery["triggered"])
        self.assertGreaterEqual(len(recovery["attempts"]), 1)
        self.assertEqual(recovery["selected_candidate"], None)
        self.assertEqual(
            pipeline.step_results["roi"].get("roi_recovery"), recovery
        )

    def test_4020_rejects_compact_roi_and_reports_body_fallback(self):
        image = cv2.imread(str(Path("tupian") / "40.20.jpg"))
        self.assertIsNotNone(image)

        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(image)

        roi = pipeline.step_results["roi"]
        self.assertEqual(roi["roi_source"], "lowres_body")
        self.assertEqual(
            roi["roi_selection"]["fallback_reason"],
            "compact_structure_invalid",
        )
        self.assertEqual(roi["roi_selection"]["y_refinement_fallback"],
                         "body_y_lost_tick_support")
        self.assertEqual(
            pipeline.step_results["split"]["seam_source"],
            "projection_valley",
        )
        self.assertEqual(
            pipeline.step_results["vernier"]["error"],
            "no_reliable_valley_bounded_tick_range",
        )
        self.assertEqual(result.total, 0.0)

    def test_4030_period_consistent_window_keeps_a_valid_reading(self):
        image = cv2.imread(str(Path("tupian") / "40.30.jpg"))
        self.assertIsNotNone(image)

        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(image)

        self.assertGreater(result.main_scale, 0.0)
        self.assertLess(abs(result.total - 40.30), 0.25)

    def test_10074_window_does_not_extend_into_the_ruler_tail(self):
        image = cv2.imread(str(Path("tupian") / "100.74.jpg"))
        self.assertIsNotNone(image)

        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(image)

        self.assertNotEqual(
            pipeline.step_results["roi"]["roi_source"], "lowres_vernier_window"
        )

    def test_roi_selection_does_not_run_vernier_geometry(self):
        selected, info = _select_reading_roi_candidate(
            self.enhanced,
            self.projection_box,
            self.body_box,
            self.x_diag,
            compact_builder=lambda *_: self.compact_box,
            structure_validator=lambda *_: True,
        )

        self.assertEqual(selected, self.compact_box)
        self.assertEqual(info["selected_stage"], "compact")
        self.assertEqual(
            set(info["candidate_boxes"]), {"projection", "body", "compact"}
        )

    def test_lowres_roi_has_no_cross_stage_geometry_refinement(self):
        image = cv2.imread(str(Path("tupian") / "30.00.jpg"))
        self.assertIsNotNone(image)

        result = roi_extract.locate_roi_lowres(image)
        selection = result["roi_selection"]

        self.assertNotIn("vernier_window", selection["candidate_boxes"])
        self.assertNotEqual(selection["selected_stage"], "geometry_refined")
        self.assertIsNone(result.get("roi_refinement"))

    def test_pipeline_and_vernier_interfaces_do_not_accept_roi_geometry_hints(self):
        self.assertNotIn(
            "geometry_hint", inspect.signature(CaliperPipeline._run_remainder).parameters
        )
        self.assertNotIn(
            "geometry_hint", inspect.signature(recognize_vernier_scale).parameters
        )

    @staticmethod
    def _roi_boxes(name):
        img = cv2.imread(str(Path("tupian") / name))
        h, w = img.shape[:2]
        scale = min(1.0, 1600.0 / float(w))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if scale < 1.0:
            gray = cv2.resize(
                gray, (int(round(w * scale)), int(round(h * scale))),
                interpolation=cv2.INTER_LINEAR,
            )
        enhanced = roi_extract._make_lowres_roi_enhanced(gray)
        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=roi_extract._odd_between(min(gray.shape) // 18, 15, 51),
            C=9,
        )
        y1, y2 = roi_extract._proj_find_y_range(cv2.bitwise_not(binary), gray.shape[0])
        x1, x2, x_diag = roi_extract._proj_find_x_range(
            cv2.bitwise_not(binary), y1, y2, gray.shape[1]
        )
        projection_box = (y1, y2, x1, x2)
        body_box = roi_extract._refine_roi_by_vernier_block(
            enhanced, y1, y2, x1, x2, {}
        )
        return enhanced, projection_box, body_box, x_diag


if __name__ == "__main__":
    unittest.main()
