import cv2
import numpy as np
import pytest

from caliper.utils import refine_tick_x_subpixel


def test_subpixel_refinement_keeps_half_strength_continuous_edge_correction():
    """The blended refiner should retain a fractional edge correction."""
    x = np.arange(30, dtype=float)
    left_edge = 10.2
    right_edge = 14.6
    softness = 0.25
    sigmoid = lambda values: 1.0 / (1.0 + np.exp(-values / softness))
    profile = 255.0 - 215.0 * (
        sigmoid(x - left_edge) - sigmoid(x - right_edge)
    )
    gray = np.tile(np.round(profile), (20, 1)).astype(np.uint8)

    refined = refine_tick_x_subpixel(gray, 12, 0, 20)

    assert refined == pytest.approx(12.45, abs=0.01)
    assert refined != pytest.approx(12.5, abs=1e-6)
