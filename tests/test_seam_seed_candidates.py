import unittest
from unittest.mock import patch

import numpy as np

from caliper import roi_extract


class SeamSeedCandidateTests(unittest.TestCase):
    def test_uses_tick_band_valley_as_dynamic_seed(self):
        gray = np.zeros((200, 400), dtype=np.uint8)
        fg = np.zeros_like(gray)
        band_info = {"tick_band_valley": (91, 109)}

        with patch(
            "caliper.region_split._analyze_horizontal_tick_bands",
            return_value=band_info,
        ), patch(
            "caliper.region_split._split_from_tick_band_valley",
            return_value=100,
        ) as split_from_valley:
            seeds = roi_extract._seam_seed_candidates(gray, fg)

        split_from_valley.assert_called_once()
        self.assertEqual(len(split_from_valley.call_args.args), 1)
        self.assertIs(split_from_valley.call_args.args[0], band_info)
        self.assertEqual(seeds[0], 100)
        self.assertIn(128, seeds)

    def test_keeps_fixed_seeds_when_tick_band_analysis_has_invalid_values(self):
        gray = np.zeros((200, 400), dtype=np.uint8)
        fg = np.zeros_like(gray)

        with patch(
            "caliper.region_split._analyze_horizontal_tick_bands",
            side_effect=ValueError("invalid projection"),
        ):
            seeds = roi_extract._seam_seed_candidates(gray, fg)

        self.assertEqual(seeds, [115, 140])

    def test_surfaces_interface_errors_instead_of_silently_using_fixed_seeds(self):
        gray = np.zeros((200, 400), dtype=np.uint8)
        fg = np.zeros_like(gray)

        with patch(
            "caliper.region_split._analyze_horizontal_tick_bands",
            side_effect=TypeError("unexpected interface"),
        ), self.assertRaises(TypeError):
            roi_extract._seam_seed_candidates(gray, fg)


if __name__ == "__main__":
    unittest.main()
