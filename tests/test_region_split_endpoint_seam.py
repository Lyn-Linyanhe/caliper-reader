from pathlib import Path

import cv2

from caliper.pipeline import CaliperPipeline


def _run(filename: str):
    image = cv2.imread(str(Path('tupian') / filename))
    assert image is not None
    pipeline = CaliperPipeline(fast_mode=True)
    result = pipeline.run(image)
    return pipeline, result


def test_4020_reports_projection_valley_fallback_when_endpoint_evidence_is_weak():
    pipeline, _ = _run('40.20.jpg')

    split = pipeline.step_results['split']
    vernier = pipeline.step_results['vernier']

    assert split['seam_source'] == 'projection_valley'
    assert split['split_recovery']['original_split_y'] == 573
    assert split['split_y'] == 776
    assert split['split_recovery']['selected_candidate'] is not None
    assert len(vernier['vernier_ticks']) >= 20


def test_normal_endpoint_samples_keep_vernier_evidence():
    for filename in ('40.00.jpg', '40.30.jpg', '100.00.jpg', '100.60.jpg', '120.60.jpg'):
        pipeline, _ = _run(filename)
        vernier = pipeline.step_results['vernier']
        assert len(vernier['vernier_ticks']) > 0, filename
