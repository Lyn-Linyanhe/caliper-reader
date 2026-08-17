from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from tools.audit_paper_algorithm_consistency import patch_document


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DOCX = ROOT / 'paper' / '02_Word版本' / '基于机器视觉的游标卡尺自动读数识别系统设计2_算法补充版.docx'
NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS_M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
NS_WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'


def _root(path: Path) -> ET.Element:
    with zipfile.ZipFile(path, 'r') as archive:
        return ET.fromstring(archive.read('word/document.xml'))


def _visible_text(path: Path) -> str:
    root = _root(path)
    return '\n'.join(
        ''.join(node.text or '' for node in paragraph.findall('.//{%s}t' % NS_W))
        for paragraph in root.findall('.//{%s}p' % NS_W)
    )


def _math_text(path: Path) -> str:
    root = _root(path)
    return ''.join(node.text or '' for node in root.findall('.//{%s}t' % NS_M))


def _equation_labels(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith('(')
        and line.strip().endswith(')')
        and line.strip()[1:-1].isdigit()
    ]


def test_consistency_audit_corrects_only_verified_algorithm_claims(tmp_path: Path):
    assert SOURCE_DOCX.exists(), '缺少当前论文算法补充版 DOCX'
    output = tmp_path / 'paper_consistency_audit.docx'

    patch_document(SOURCE_DOCX, output)

    source_root = _root(SOURCE_DOCX)
    output_root = _root(output)
    text = _visible_text(output)
    math = _math_text(output)

    assert 'RANSAC 拟合接缝候选点' in text
    assert '峰段的几何中心' in text
    assert '连通域并非投影候选的硬性准入条件' in text
    assert '不以纵向重叠作为硬过滤条件' in text
    assert '纵向重叠约束保证' not in text
    assert 'y overlap' not in math
    assert 'min' in math
    assert '|x*' in math
    assert _equation_labels(text) == [f'({index})' for index in range(1, 16)]

    assert len(output_root.findall('.//{%s}tbl' % NS_W)) == len(
        source_root.findall('.//{%s}tbl' % NS_W)
    )
    assert len(output_root.findall('.//{%s}inline' % NS_WP)) == len(
        source_root.findall('.//{%s}inline' % NS_WP)
    )
    assert len(output_root.findall('.//{%s}oMath' % NS_M)) >= len(
        source_root.findall('.//{%s}oMath' % NS_M)
    )

    equation_6 = next(
        paragraph
        for paragraph in output_root.findall('.//{%s}p' % NS_W)
        if ''.join(node.text or '' for node in paragraph.findall('.//{%s}t' % NS_W)).strip()
        == '(6)'
    )
    equation_11 = next(
        paragraph
        for paragraph in output_root.findall('.//{%s}p' % NS_W)
        if ''.join(node.text or '' for node in paragraph.findall('.//{%s}t' % NS_W)).strip()
        == '(11)'
    )
    assert equation_6.find('.//{%s}sSub' % NS_M) is not None
    assert equation_6.find('.//{%s}f' % NS_M) is not None
    assert equation_11.find('.//{%s}sSub' % NS_M) is not None
    assert equation_11.find('.//{%s}sSup' % NS_M) is not None
