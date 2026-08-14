from caliper.config import config


def test_summary_lists_class_level_runtime_configuration():
    summary = config.summary()

    assert "preprocess" in summary
    assert "gamma =" in summary
    assert "vernier_scale" in summary
    assert "tick_band_bottom_pad =" in summary
