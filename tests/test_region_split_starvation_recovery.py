from pathlib import Path

import cv2

from caliper.pipeline import CaliperPipeline


def test_4020_recovers_later_tick_bands_only_after_vernier_starvation():
    image = cv2.imread(str(Path("tupian") / "40.20.jpg"))
    assert image is not None

    pipeline = CaliperPipeline(fast_mode=True)
    result = pipeline.run(image)

    split = pipeline.step_results["split"]
    main = pipeline.step_results["main"]
    vernier = pipeline.step_results["vernier"]
    recovery = split["split_recovery"]

    assert split["seam_source"] == "projection_valley"
    assert recovery["triggered"] is True
    assert recovery["original_split_y"] == 573
    assert recovery["selected_candidate"] is not None
    assert split["split_y"] > recovery["original_split_y"]
    assert len(main["main_ticks"]) >= 40
    assert 40.0 <= main["main_gap"] <= 55.0
    assert len(vernier["vernier_ticks"]) >= 20
    assert vernier["zero_x"] < 2600
    assert abs(result.total - 40.20) <= 0.10


def test_endpoint_seam_controls_do_not_enter_starvation_recovery():
    for filename in ("40.00.jpg", "40.30.jpg", "100.00.jpg", "120.60.jpg"):
        image = cv2.imread(str(Path("tupian") / filename))
        assert image is not None

        pipeline = CaliperPipeline(fast_mode=True)
        pipeline.run(image)

        split = pipeline.step_results["split"]
        assert split["seam_source"] == "component_endpoints", filename
        assert split.get("split_recovery") is None, filename
