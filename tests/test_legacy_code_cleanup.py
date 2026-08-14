import caliper.main_scale as main_scale
import caliper.region_split as region_split
import caliper.roi_extract as roi_extract
import caliper.utils as utils
import caliper.vernier_scale as vernier_scale


def test_removed_private_legacy_paths_are_not_exposed():
    removed = {
        main_scale: (
            "_estimate_gap_from_xs",
            "_main_split_near_projection",
            "_build_standard_tick_response",
            "_draw_standardized_projection",
        ),
        region_split: (
            "_split_by_candidate_scan",
            "_snap_to_brightest_gap",
            "_equispaced_coverage",
        ),
        roi_extract: (
            "_locate_roi_by_screw_template",
            "_find_vernier_reading_window",
        ),
        utils: (
            "detect_tick_xs_in_band",
            "extract_ticks_from_anchor_band",
            "draw_legend",
        ),
        vernier_scale: (),
    }

    for module, names in removed.items():
        for name in names:
            assert not hasattr(module, name), f"{module.__name__}.{name} remains"
