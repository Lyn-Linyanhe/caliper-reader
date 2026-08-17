from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from tools.patch_user_paper_algorithms import patch_document


SOURCE_DOCX = Path(r'E:\朱\基于机器视觉的游标卡尺自动读数识别系统设计2.docx')
NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS_WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
NS_M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'


def _document_root(path: Path) -> ET.Element:
    with zipfile.ZipFile(path, 'r') as archive:
        return ET.fromstring(archive.read('word/document.xml'))


def _visible_text(path: Path) -> str:
    root = _document_root(path)
    return '\n'.join(
        ''.join(node.text or '' for node in paragraph.findall('.//{%s}t' % NS_W))
        for paragraph in root.findall('.//{%s}p' % NS_W)
    )


def _math_text(path: Path) -> str:
    root = _document_root(path)
    return ''.join(node.text or '' for node in root.findall('.//{%s}t' % NS_M))


def test_patch_preserves_user_document_and_adds_algorithm_clarifications(tmp_path: Path):
    assert SOURCE_DOCX.exists(), '需要用户修改后的论文 DOCX 作为输入'
    output = tmp_path / 'paper_algorithm_patch.docx'

    patch_document(SOURCE_DOCX, output)

    source_root = _document_root(SOURCE_DOCX)
    output_root = _document_root(output)
    text = _visible_text(output)
    assert '端点证据优先、投影谷底回退' in text
    assert '长度聚类仅用于标准化可视化' in text
    assert '不以纵向重叠作为硬过滤条件' in text
    labels = [
        paragraph.strip()
        for paragraph in text.splitlines()
        if paragraph.strip().startswith('(')
        and paragraph.strip().endswith(')')
        and paragraph.strip()[1:-1].isdigit()
    ]
    assert labels == [f'({index})' for index in range(1, 16)]
    assert '区域分离 1 例、主尺数字识别 1 例、游标零刻度定位或对齐 3 例' in text
    assert '图 8 游标连通域与长度聚类可视化结果' in text
    assert 'Δc' in _math_text(output)
    assert '0.2M' in _math_text(output)
    descriptions = [
        node.attrib.get('descr', '')
        for node in output_root.findall('.//{%s}docPr' % NS_WP)
    ]
    assert '图 8 游标连通域与长度聚类可视化结果' in descriptions
    figure8 = next(
        inline
        for inline in output_root.findall('.//{%s}inline' % NS_WP)
        if inline.find('{%s}docPr' % NS_WP).attrib.get('descr')
        == '图 8 游标连通域与长度聚类可视化结果'
    )
    extent = figure8.find('{%s}extent' % NS_WP)
    assert int(extent.attrib['cy']) / int(extent.attrib['cx']) > 0.4

    third_table = output_root.findall('.//{%s}tbl' % NS_W)[2]
    rows = third_table.findall('{%s}tr' % NS_W)
    table_text = [
        [''.join(node.text or '' for node in cell.findall('.//{%s}t' % NS_W))
         for cell in row.findall('{%s}tc' % NS_W)]
        for row in rows
    ]
    assert len(table_text) == 6
    assert table_text[0] == ['图片', '标注/系统/误差（mm）', '主要错误归因']
    assert [row[0] for row in table_text[1:]] == [
        '130.70', '140.00', '40.20', '50.50', '60.96',
    ]
    assert all(len(row) == 3 for row in table_text)
    assert len(output_root.findall('.//{%s}tbl' % NS_W)) == len(source_root.findall('.//{%s}tbl' % NS_W))
    assert len(output_root.findall('.//{%s}inline' % NS_WP)) == len(source_root.findall('.//{%s}inline' % NS_WP))
