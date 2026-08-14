from pathlib import Path

import cv2
import numpy as np
import pytest

from caliper.pipeline import CaliperPipeline


def _image(filename: str) -> np.ndarray:
    raw = np.fromfile(str(Path('tupian') / filename), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    assert image is not None
    return image


def test_detailed_vernier_tab_stacks_tick_valley_and_component_evidence():
    pipeline = CaliperPipeline(fast_mode=False)
    pipeline.run(_image('60.50.jpg'))

    visual = pipeline.debug_images['4b_游标刻度线']

    # The existing tick view is about 850 px high.  A detailed tab must also
    # contain the valley and component sections beneath it.
    assert visual.shape[0] >= 1600
    assert '4a_游标谷底' not in pipeline.debug_images


def test_fast_mode_does_not_generate_vernier_debug_tab():
    pipeline = CaliperPipeline(fast_mode=True)
    pipeline.run(_image('60.50.jpg'))

    assert '4b_游标刻度线' not in pipeline.debug_images
    assert pipeline.step_results['vernier']['vis_ticks'] is None


def test_vernier_detail_panel_has_length_standard_response_without_reading_change():
    detailed = CaliperPipeline(fast_mode=False)
    detailed_result = detailed.run(_image('30.00.jpg'))
    fast = CaliperPipeline(fast_mode=True)
    fast_result = fast.run(_image('30.00.jpg'))

    panel = detailed.debug_images['4b_游标刻度线']
    assert panel.shape[0] > 1579
    assert detailed_result.total == fast_result.total
    assert detailed.step_results['vernier']['zero_x'] == pytest.approx(
        fast.step_results['vernier']['zero_x']
    )
