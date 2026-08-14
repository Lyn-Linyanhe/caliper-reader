from pathlib import Path

import cv2

from caliper.config import config
from caliper.pipeline import CaliperPipeline


def test_roi_progress_uses_current_candidate_source_label():
    image = cv2.imread('tupian/72.52.jpg')
    assert image is not None

    events = []
    pipeline = CaliperPipeline(fast_mode=True)
    pipeline.run(image, progress_callback=lambda key, _image, status: events.append((key, status)))

    roi_statuses = [status for key, status in events if key == '1_ROI定位']
    assert roi_statuses
    assert roi_statuses[-1].endswith(('低分辨率投影框', '低分辨率主体框', '低分辨率紧凑框'))
    assert '螺丝模板匹配' not in roi_statuses[-1]


def test_final_metadata_does_not_report_removed_template_strategy():
    image = cv2.imread('tupian/72.52.jpg')
    assert image is not None

    result = CaliperPipeline(fast_mode=True).run(image)
    strategies = result.extra_info.get('speed_strategies', {})

    assert 'roi_template_matching' not in strategies


def test_config_examples_and_gamma_description_match_current_api():
    source = Path('caliper/config.py').read_text(encoding='utf-8')
    assert 'config.roi.aspect_min' not in source
    assert 'config.roi.x_pad_ratio' in source
    assert '<1 压暗' in source
    assert '>1 提亮' in source
    assert hasattr(config.roi, 'x_pad_ratio')
    assert not hasattr(config.roi, 'aspect_min')
