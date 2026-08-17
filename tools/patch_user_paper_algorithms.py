from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET


NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS_M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
NS_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
NS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS_PR = 'http://schemas.openxmlformats.org/package/2006/relationships'
NS_WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
W = '{' + NS_W + '}'
M = '{' + NS_M + '}'
A = '{' + NS_A + '}'
R = '{' + NS_R + '}'
PR = '{' + NS_PR + '}'
ET.register_namespace('w', NS_W)
ET.register_namespace('m', NS_M)


REGION_SPLIT_TEXT = (
    '当前实现采用“端点证据优先、投影谷底回退”的分割线定位策略。具体而言，'
    '先对二值前景做竖直开运算以突出细长刻线结构，并统计连通域在各行的上端、'
    '下端响应；在 ROI 高度的 0.34H 至 0.75H 范围内，将主尺刻线下端峰与游标刻线'
    '上端峰配对，端点间距不超过 max(24,min(36,0.035H)) 像素且配对评分不低于 '
    '0.18 时，以主尺下端峰所在行作为分割线。端点证据不足时，在刻线带投影中寻找'
    '两侧具有结构支撑的谷底；仍无可靠结果才以 0.60H 作为比例回退，并保证游标区'
    '高度不低于 ROI 高度的 0.28。该步骤只确定主尺、游标尺的分割线与各自刻线带，'
    '不重新识别或补全刻线。'
)

LENGTH_CLUSTER_TEXT = (
    '为便于检查最终刻线序列的长短结构，系统还对最终接受的游标刻线长度进行确定性'
    '一维两类聚类。长度样本不少于 6 条时，先以第 5 与第 95 百分位截断异常长度，'
    '再以第 25 与第 75 百分位作为两个初始中心，按最近中心迭代分配和更新，最多迭代 '
    '20 次或在中心变化小于 0.001 像素时停止。仅当两簇均不少于 3 条，且中心差不小于 '
    'max(2.0,0.20 倍长度中位数) 时，才保留短线、长线两类；否则按单类显示。绘制'
    '标准化曲线时，短线簇峰值记为 1.0，长线簇峰值记为 1.5。长度聚类仅用于标准化'
    '可视化和人工复核，不参与谷底选择、零刻度线定位、刻线筛选、对齐或正式读数。'
)

LENGTH_CLUSTER_EXPLANATION = (
    '设有效刻线长度为 L，短线簇与长线簇的样本数分别为 N_1、N_2，聚类中心为 '
    'c_1、c_2，令 Δc=|c_2-c_1|，M=median(L)。只有在两簇均具有足够样本且中心差明显时才显示两类结果；否则以单类'
    '曲线呈现，避免把由反光、断裂或数字粘连引起的长度离群误解为长刻线。'
)

ERROR_ATTRIBUTION_TEXT = (
    '在误差超过 0.10 mm 的 5 张样本中，区域分离 1 例、主尺数字识别 1 例、游标'
    '零刻度定位或对齐 3 例。该分布说明大误差主要来自前置区域结构异常和游标小数'
    '判定，而不是文件名标注或后处理取整；因此后续改进应优先加强分割线稳定性、数字'
    '候选框覆盖与零刻度线的结构验证。'
)


def _text_of(paragraph: ET.Element) -> str:
    return ''.join(node.text or '' for node in paragraph.findall('.//' + W + 't'))


def _new_body_paragraph(template: ET.Element, text: str) -> ET.Element:
    paragraph = ET.Element(W + 'p')
    properties = template.find(W + 'pPr')
    if properties is not None:
        paragraph.append(deepcopy(properties))

    run = ET.SubElement(paragraph, W + 'r')
    source_run = template.find(W + 'r')
    if source_run is not None:
        run_properties = source_run.find(W + 'rPr')
        if run_properties is not None:
            run.append(deepcopy(run_properties))
    node = ET.SubElement(run, W + 't')
    node.text = text
    return paragraph


def _new_equation_paragraph(template: ET.Element, tokens: list[tuple[str, str]], label: str) -> ET.Element:
    paragraph = ET.Element(W + 'p')
    properties = template.find(W + 'pPr')
    if properties is not None:
        paragraph.append(deepcopy(properties))

    equation = ET.SubElement(paragraph, M + 'oMath')
    for kind, value in tokens:
        run = ET.SubElement(equation, M + 'r')
        if kind == 'sub':
            subscript = ET.SubElement(equation, M + 'sSub')
            base = ET.SubElement(subscript, M + 'e')
            base_run = ET.SubElement(base, M + 'r')
            ET.SubElement(base_run, M + 't').text = value[0]
            lower = ET.SubElement(subscript, M + 'sub')
            lower_run = ET.SubElement(lower, M + 'r')
            ET.SubElement(lower_run, M + 't').text = value[1]
            equation.remove(run)
            continue
        ET.SubElement(run, M + 't').text = value

    tab = ET.SubElement(paragraph, W + 'r')
    ET.SubElement(tab, W + 'tab')
    number_run = ET.SubElement(paragraph, W + 'r')
    source_run = template.find(W + 'r')
    if source_run is not None:
        run_properties = source_run.find(W + 'rPr')
        if run_properties is not None:
            number_run.append(deepcopy(run_properties))
    ET.SubElement(number_run, W + 't').text = label
    return paragraph


def _make_table_cell(template: ET.Element, value: str) -> ET.Element:
    cell = ET.Element(W + 'tc')
    source_properties = template.find(W + 'tcPr')
    if source_properties is not None:
        cell.append(deepcopy(source_properties))
    paragraph = template.find(W + 'p')
    if paragraph is None:
        paragraph = ET.Element(W + 'p')
    new_paragraph = _new_body_paragraph(paragraph, value)
    cell.append(new_paragraph)
    return cell


def _replace_error_table(body: ET.Element) -> None:
    tables = body.findall(W + 'tbl')
    if len(tables) < 3:
        raise ValueError('未找到表 3')
    old = tables[2]
    rows = old.findall(W + 'tr')
    if not rows or len(rows[0].findall(W + 'tc')) < 3:
        raise ValueError('表 3 格式异常')
    templates = rows[0].findall(W + 'tc')
    table = ET.Element(W + 'tbl')
    properties = old.find(W + 'tblPr')
    if properties is not None:
        table.append(deepcopy(properties))

    grid = ET.SubElement(table, W + 'tblGrid')
    for width in ('1450', '2400', '3100'):
        ET.SubElement(grid, W + 'gridCol', {W + 'w': width})

    values = [
        ('图片', '标注/系统/误差（mm）', '主要错误归因'),
        ('130.70', '130.70 / 0.14 / 130.56', '主尺数字识别失败，整数部分缺失'),
        ('140.00', '140.00 / 140.48 / 0.48', '游标零线或小数对齐偏差'),
        ('40.20', '40.20 / 0.00 / 40.20', '区域分离压缩有效刻线带'),
        ('50.50', '50.50 / 50.32 / 0.18', '游标小数对齐刻线选择偏差'),
        ('60.96', '60.96 / 60.72 / 0.24', '游标小数对齐刻线选择偏差'),
    ]
    for values_row in values:
        row = ET.SubElement(table, W + 'tr')
        for index, value in enumerate(values_row):
            row.append(_make_table_cell(templates[min(index, len(templates) - 1)], value))

    body.insert(list(body).index(old), table)
    body.remove(old)


def _resize_figure8(root: ET.Element) -> None:
    for inline in root.findall('.//' + '{' + NS_WP + '}' + 'inline'):
        doc_pr = inline.find('{' + NS_WP + '}docPr')
        if doc_pr is None or doc_pr.attrib.get('descr') != '图 8 游标连通域与长度聚类可视化结果':
            continue
        extent = inline.find('{' + NS_WP + '}extent')
        if extent is None:
            raise ValueError('图 8 缺少尺寸信息')
        width = int(extent.attrib['cx'])
        height = int(round(width * 1302 / 2750))
        extent.set('cy', str(height))
        transform = inline.find('.//' + A + 'xfrm')
        if transform is not None:
            ext = transform.find(A + 'ext')
            if ext is not None:
                ext.set('cy', str(height))
        return
    raise ValueError('未找到图 8 尺寸')


def _insert_after_matching_paragraph(body: ET.Element,
                                     marker: str,
                                     content: str) -> None:
    paragraphs = list(body.findall(W + 'p'))
    for paragraph in paragraphs:
        if marker in _text_of(paragraph):
            inserted = _new_body_paragraph(paragraph, content)
            body.insert(list(body).index(paragraph) + 1, inserted)
            return
    raise ValueError(f'未找到段落锚点: {marker}')


def _replace_alignment_claim(body: ET.Element) -> None:
    old = '系统寻找距离最近且纵向范围存在重叠的主尺刻线，并以亚像素坐标计算横向距离：'
    new = (
        '系统以亚像素横坐标计算其到全部主尺刻线的最近横向距离，'
        '不以纵向重叠作为硬过滤条件：'
    )
    for paragraph in body.findall(W + 'p'):
        visible = _text_of(paragraph)
        if old not in visible:
            continue

        replacement = visible.replace(old, new)
        properties = paragraph.find(W + 'pPr')
        source_run = paragraph.find(W + 'r')
        for child in list(paragraph):
            if child is not properties:
                paragraph.remove(child)
        run = ET.SubElement(paragraph, W + 'r')
        if source_run is not None:
            run_properties = source_run.find(W + 'rPr')
            if run_properties is not None:
                run.append(deepcopy(run_properties))
        node = ET.SubElement(run, W + 't')
        node.text = replacement
        return
    raise ValueError('未找到游标对齐表述锚点')


def _replace_text(body: ET.Element, old: str, new: str) -> None:
    for paragraph in body.findall(W + 'p'):
        visible = _text_of(paragraph)
        if old not in visible:
            continue
        replacement = visible.replace(old, new)
        properties = paragraph.find(W + 'pPr')
        source_run = paragraph.find(W + 'r')
        for child in list(paragraph):
            if child is not properties:
                paragraph.remove(child)
        run = ET.SubElement(paragraph, W + 'r')
        if source_run is not None:
            run_properties = source_run.find(W + 'rPr')
            if run_properties is not None:
                run.append(deepcopy(run_properties))
        ET.SubElement(run, W + 't').text = replacement
        return
    raise ValueError(f'未找到文本替换锚点: {old}')


def _replace_math_text(root: ET.Element, old: str, new: str) -> None:
    for node in root.findall('.//' + M + 't'):
        if node.text == old:
            node.text = new
            return
    raise ValueError(f'未找到公式文本: {old}')


def _repair_arctan_formula(root: ET.Element) -> None:
    for equation in root.findall('.//' + M + 'oMath'):
        nodes = equation.findall('.//' + M + 't')
        for index, node in enumerate(nodes):
            if node.text != '=arctan':
                continue
            node.text = '=arctan('
            for candidate in nodes[index + 1:]:
                if candidate.text == 'k':
                    candidate.text = 'k)'
                    return
            raise ValueError('方向校正公式缺少 arctan 的自变量')
    raise ValueError('未找到方向校正 arctan 公式')


def _update_figure_description(root: ET.Element, description: str) -> None:
    for node in root.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr'):
        if node.attrib.get('descr') == '图 8 游标刻线连通域筛选示意图':
            node.set('descr', description)
            return
    raise ValueError('未找到图 8 描述')


def _replace_figure8_media(root: ET.Element, entries: dict[str, bytes]) -> None:
    embed_id = None
    for inline in root.findall('.//' + '{' + NS_WP + '}' + 'inline'):
        doc_pr = inline.find('{' + NS_WP + '}docPr')
        if doc_pr is None or doc_pr.attrib.get('descr') != '图 8 游标连通域与长度聚类可视化结果':
            continue
        blip = inline.find('.//' + A + 'blip')
        if blip is not None:
            embed_id = blip.attrib.get(R + 'embed')
            break
    if not embed_id:
        raise ValueError('未找到图 8 的嵌入图片关系')

    relations = ET.fromstring(entries['word/_rels/document.xml.rels'])
    target = None
    for relation in relations.findall(PR + 'Relationship'):
        if relation.attrib.get('Id') == embed_id:
            target = relation.attrib.get('Target')
            break
    if not target:
        raise ValueError('未找到图 8 的图片文件')

    figure = (
        Path(__file__).resolve().parents[1]
        / 'paper'
        / '03_排版与审校'
        / '论文图表素材'
        / '图08_游标连通域与长度聚类_30.00.png'
    )
    if not figure.exists():
        raise FileNotFoundError(figure)
    entries['word/' + target.replace('\\', '/')] = figure.read_bytes()


def _renumber_equation_labels(body: ET.Element) -> None:
    labels = []
    for paragraph in body.findall(W + 'p'):
        visible = _text_of(paragraph).strip()
        if re.fullmatch(r'\(\d+\)', visible):
            labels.append(paragraph)
    for index, paragraph in enumerate(labels, start=1):
        nodes = paragraph.findall('.//' + W + 't')
        if not nodes:
            continue
        nodes[0].text = f'({index})'
        for node in nodes[1:]:
            node.text = ''


def _first_equation_template(body: ET.Element) -> ET.Element:
    for paragraph in body.findall(W + 'p'):
        if paragraph.find(M + 'oMath') is not None and re.fullmatch(r'\(\d+\)', _text_of(paragraph).strip()):
            return paragraph
    raise ValueError('未找到公式段落模板')


def patch_document(input_docx: Path, output_docx: Path) -> None:
    input_docx = Path(input_docx)
    output_docx = Path(output_docx)
    with zipfile.ZipFile(input_docx, 'r') as source:
        entries = {name: source.read(name) for name in source.namelist()}

    root = ET.fromstring(entries['word/document.xml'])
    body = root.find(W + 'body')
    if body is None:
        raise ValueError('输入 DOCX 缺少正文')

    _insert_after_matching_paragraph(body, '干扰游标谷底和零线判断。', REGION_SPLIT_TEXT)
    _insert_after_matching_paragraph(body, '下端纵坐标聚类为长、短两类刻线。', LENGTH_CLUSTER_TEXT)
    equation_template = _first_equation_template(body)
    _insert_after_matching_paragraph(body, LENGTH_CLUSTER_TEXT, LENGTH_CLUSTER_EXPLANATION)
    paragraphs = list(body.findall(W + 'p'))
    for paragraph in paragraphs:
        if LENGTH_CLUSTER_EXPLANATION in _text_of(paragraph):
            equation = _new_equation_paragraph(
                equation_template,
                [('sub', ('N', '1')), ('text', ', '), ('sub', ('N', '2')),
                 ('text', ' >= 3,   Δc >= max(2.0, 0.2M)')],
                '(13)',
            )
            body.insert(list(body).index(paragraph) + 1, equation)
            break
    else:
        raise ValueError('未找到长度聚类说明段落')
    _insert_after_matching_paragraph(body, '误差分布表明，系统的大误差集中在区域分离、数字识别和游标小数对齐三个环节。', ERROR_ATTRIBUTION_TEXT)
    _replace_alignment_claim(body)
    _repair_arctan_formula(root)
    _replace_text(body, '图 8 游标刻线连通域筛选示意图', '图 8 游标连通域与长度聚类可视化结果')
    _update_figure_description(root, '图 8 游标连通域与长度聚类可视化结果')
    _replace_figure8_media(root, entries)
    _resize_figure8(root)
    _replace_error_table(body)
    _renumber_equation_labels(body)

    entries['word/document.xml'] = ET.tostring(
        root, encoding='utf-8', xml_declaration=True
    )
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_docx, 'w', compression=zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(name, data)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    patch_document(args.input, args.output)
    print(args.output)
