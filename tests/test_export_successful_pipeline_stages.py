from pathlib import Path

from tools.export_successful_pipeline_stages import export_samples


def test_export_samples_writes_all_detailed_stage_images_for_exact_sample(tmp_path):
    root = Path(__file__).resolve().parents[1]
    report = export_samples(
        input_dir=root / 'tupian',
        output_dir=tmp_path,
        filenames=['30.00.jpg'],
        truths={'30.00.jpg': 30.00},
    )

    assert report['samples'][0]['reading_mm'] == 30.00
    assert report['samples'][0]['truth_mm'] == 30.00
    assert report['samples'][0]['matches_truth'] is True
    assert (tmp_path / '01_30.00' / '1_ROI定位.png').is_file()
    assert (tmp_path / '01_30.00' / '2_区域分离.png').is_file()
    assert (tmp_path / '01_30.00' / '3a_主尺刻度线.png').is_file()
    assert (tmp_path / '01_30.00' / '3b_主尺数字OCR.png').is_file()
    assert (tmp_path / '01_30.00' / '4b_游标刻度线.png').is_file()
    assert (tmp_path / '01_30.00' / '4c_游标对齐.png').is_file()
    assert (tmp_path / '01_30.00' / '5_最终标注.png').is_file()
    assert (tmp_path / '01_30.00' / '5b_读数推导.png').is_file()
    assert (tmp_path / 'report.json').is_file()
