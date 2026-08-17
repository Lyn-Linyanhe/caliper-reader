"""Create a DOCX whose algorithm narrative matches the current implementation.

The input document is preserved byte-for-byte except for ``word/document.xml``.
This keeps the user's column layout, media, styles, tables, and hand edits while
replacing only the paragraphs and formulas identified by content anchors.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET


NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS_M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
W = '{' + NS_W + '}'
M = '{' + NS_M + '}'

ET.register_namespace('w', NS_W)
ET.register_namespace('m', NS_M)


DIRECTION_TEXT = (
    '实际拍摄中，卡尺与图像坐标轴之间可能存在轻微夹角，若不校正，主尺和游标尺刻线在投影方向上会发生偏移，'
    '影响后续刻线长度测量和横向峰段定位。当前实现以接缝为整体方向证据：先在 0.75 倍尺度的增强灰度图和二值图中，'
    '由刻线带谷底及 ROI 高度的 0.58H、0.64H、0.70H 等位置生成接缝种子；再在各种子邻域计算 Scharr 垂直梯度，'
    '逐列提取局部响应峰，形成接缝候选点。对候选点执行 RANSAC 拟合接缝候选点，得到直线模型 y=ax+b，'
    '并以 θ=arctan(a) 估计旋转角。有效模型还需同时满足内点数、横向覆盖、拟合残差和中心位置的约束，且 |θ| 不超过 2°；'
    '若没有有效模型，则令角度为 0°。随后对彩色图、增强灰度图和二值图统一按该角度变换，使后续模块使用同一校正坐标系。'
)

MAIN_PEAK_TEXT = (
    '其中 μ_P、σ_P 分别为平滑投影的均值和标准差。超过阈值 T_p 的连续前景段记为 '
    'S_k=[a_k,b_k]，每个峰段直接取峰段的几何中心作为粗候选刻线位置。'
)

MAIN_MEASURE_TEXT = (
    '随后在每个粗候选的 ±3 像素邻域内沿列累加前景像素，得到列强度曲线 c(y)，'
    '以 τ_c=max(30,min(0.4max(c),204)) 提取连续前景段，保留长度不小于 '
    'L_min=max(6,0.25H_band) 的段作为常规刻线。对于较短但周期位置一致、连续长度和前景量均满足条件的候选，'
    '系统执行短刻线恢复。刻线横坐标再在增强灰度图上进行亚像素精化：对左右边缘梯度极值中点取中位数，'
    '以减小二值化和线宽变化造成的位置误差。'
)

VALLEY_CONSTRAINT_TEXT = (
    '每个候选谷段都要求在其左右 1 至 2 个预估周期的范围内观察到高于刻线阈值的投影峰，'
    '因此两侧谷段均具有内外侧峰值支撑，而非把一段平坦背景误作刻线区域。两个谷段之间若出现宽度达到 '
    '1.3p 的内部低响应断裂，则该谷底对被剔除。通过结构约束的候选对按谷深、周期清晰度、刻线间距一致性和'
    '连通域结构质量评分，权重依次为 0.30、0.30、0.25 和 0.15。只有两个总评分之差不超过 0.02 时，'
    '才以候选刻线数接近 51 作为次级平局规则；该规则不生成、补全或强制拟合 51 条刻线。'
)

VERNIER_COMPONENT_TEXT = (
    '确定游标横向范围后，系统先将高于动态阈值 T_t=μ+0.8σ 的连续投影峰段中心作为初始刻线候选。'
    '随后提取局部连通域，借助其细长形态、纵向延伸、靠近刻线带上缘的关系和局部连续性抑制数字笔画与噪声。'
    '连通域提取前，先桥接同列内间隔不超过 10 像素的短竖直空隙，再以高度为 7 像素的竖直开运算抑制横向噪声。'
    '候选连通域需靠近刻线带上缘，高度不低于刻线带高度的 0.35 倍，宽度不超过 0.75p；'
    '其与投影候选在 max(4,min(12,0.42p)) 的搜索半径内按距离优先、投影强度次优完成匹配。'
)

VERNIER_COMPONENT_ROLE_TEXT = (
    '连通域并非投影候选的硬性准入条件，而是提供结构支持、候选匹配、质量排序和重复响应去重的证据。'
    '间距小于 0.65p 的重复候选优先保留具有连通域支持、投影更强且面积更大的候选。顶部细线验证只用于剔除'
    '第一个具有顶部细线证据的刻线之前的前缀候选，后续刻线不要求逐条通过该条件。真实零线与数字“0”粘连时，'
    '若竖直桥接后的较高连通域证明其从刻线带上缘向下贯通，仍可作为保留该候选的结构证据。'
)

ZERO_LINE_TEXT = (
    '在由左右谷底限定的有效范围内，系统先完成前缀干扰抑制和重复候选去重，得到最终游标刻线序列。'
    '该序列的第一条刻线，即 tick_xs[0]，定义为游标零刻度线；在最终输出的刻线对象中，再选择横向位置'
    '最接近该位置的一条作为零线。零线是主尺整数读数和游标小数读数的共同基准，其位置错误会同时影响两部分读数。'
)

ZERO_LINE_EVIDENCE_TEXT = (
    '零线不直接取投影范围内最左侧峰。连通域和顶部细线用于形成可靠的候选序列、抑制数字笔画造成的前缀干扰，'
    '但不构成零线的独立硬门槛。该处理既避免把数字“0”的下方笔画当作零线，也避免在真实零线与数字粘连时，'
    '仅因连通域整体宽度较大而误删真实刻线。'
)

ALIGNMENT_TEXT = (
    '其中，e_i 为第 i 条游标刻线与全部已检测主尺刻线之间的最小横向对齐误差，x* 为 4.1 节得到的'
    '亚像素刻线横坐标；计算时不以纵向重叠作为硬过滤条件。正式读数仅在自零线起的前 min(N,50) 条游标刻线中'
    '选择误差最小者，其中 50 来自当前 0.02 mm 分度对应的 1/0.02 个最大有效索引范围，并非强制拟合 51 条刻线。'
    '亚像素坐标仅用于误差比较；在误差极小刻线附近进行的抛物线插值只用于歧义分析，不改变 0.02 mm 的离散输出。'
)


def _visible_text(paragraph: ET.Element) -> str:
    return ''.join(node.text or '' for node in paragraph.findall('.//' + W + 't'))


def _paragraphs(root: ET.Element) -> list[ET.Element]:
    return list(root.findall('.//' + W + 'p'))


def _find_paragraph(root: ET.Element, marker: str) -> ET.Element:
    for paragraph in _paragraphs(root):
        if marker in _visible_text(paragraph):
            return paragraph
    raise ValueError(f'Could not find paragraph anchor: {marker!r}')


def _run_properties(paragraph: ET.Element) -> ET.Element | None:
    run = paragraph.find(W + 'r')
    if run is None:
        return None
    properties = run.find(W + 'rPr')
    return deepcopy(properties) if properties is not None else None


def _clear_paragraph_content(paragraph: ET.Element) -> None:
    properties = paragraph.find(W + 'pPr')
    for child in list(paragraph):
        if child is not properties:
            paragraph.remove(child)


def _append_text_run(paragraph: ET.Element, text: str, run_properties: ET.Element | None) -> None:
    run = ET.SubElement(paragraph, W + 'r')
    if run_properties is not None:
        run.append(deepcopy(run_properties))
    node = ET.SubElement(run, W + 't')
    if text[:1].isspace() or text[-1:].isspace():
        node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    node.text = text


def _replace_text_paragraph(paragraph: ET.Element, text: str) -> None:
    run_properties = _run_properties(paragraph)
    _clear_paragraph_content(paragraph)
    _append_text_run(paragraph, text, run_properties)


def _math_run(text: str) -> ET.Element:
    run = ET.Element(M + 'r')
    node = ET.SubElement(run, M + 't')
    node.text = text
    return run


def _linear_math(text: str) -> ET.Element:
    equation = ET.Element(M + 'oMath')
    equation.append(_math_run(text))
    return equation


def _inline_math(*parts: object) -> tuple[str, tuple[object, ...]]:
    return ('math', parts)


def _append_math_parts(parent: ET.Element, parts: tuple[object, ...] | list[object]) -> None:
    for part in parts:
        if isinstance(part, str):
            parent.append(_math_run(part))
            continue
        if not isinstance(part, tuple) or not part:
            raise ValueError(f'Unsupported math part: {part!r}')
        kind = part[0]
        if kind == 'sub':
            node = ET.SubElement(parent, M + 'sSub')
            base = ET.SubElement(node, M + 'e')
            lower = ET.SubElement(node, M + 'sub')
            _append_math_parts(base, (part[1],))
            _append_math_parts(lower, (part[2],))
        elif kind == 'sup':
            node = ET.SubElement(parent, M + 'sSup')
            base = ET.SubElement(node, M + 'e')
            upper = ET.SubElement(node, M + 'sup')
            _append_math_parts(base, (part[1],))
            _append_math_parts(upper, (part[2],))
        elif kind == 'frac':
            node = ET.SubElement(parent, M + 'f')
            numerator = ET.SubElement(node, M + 'num')
            denominator = ET.SubElement(node, M + 'den')
            _append_math_parts(numerator, part[1])
            _append_math_parts(denominator, part[2])
        else:
            raise ValueError(f'Unsupported math part kind: {kind!r}')


def _structured_math(*parts: object) -> ET.Element:
    equation = ET.Element(M + 'oMath')
    _append_math_parts(equation, parts)
    return equation


def _replace_mixed_paragraph(paragraph: ET.Element,
                             segments: list[str | tuple[str, tuple[object, ...]]]) -> None:
    run_properties = _run_properties(paragraph)
    _clear_paragraph_content(paragraph)
    for segment in segments:
        if isinstance(segment, str):
            _append_text_run(paragraph, segment, run_properties)
        elif segment[0] == 'math':
            paragraph.append(_structured_math(*segment[1]))
        else:
            raise ValueError(f'Unsupported paragraph segment: {segment!r}')


def _find_equation_paragraph(root: ET.Element, label: str) -> ET.Element:
    for paragraph in _paragraphs(root):
        if _visible_text(paragraph).strip() == label and paragraph.find('.//' + M + 'oMath') is not None:
            return paragraph
    raise ValueError(f'Could not find equation {label}')


def _replace_equation_math(paragraph: ET.Element, *formula: object) -> None:
    runs = [deepcopy(child) for child in paragraph if child.tag == W + 'r']
    _clear_paragraph_content(paragraph)
    paragraph.append(_structured_math(*formula))
    for run in runs:
        paragraph.append(run)


def _insert_after(root: ET.Element, reference: ET.Element, text: str) -> ET.Element:
    parent_map = {child: parent for parent in root.iter() for child in parent}
    parent = parent_map.get(reference)
    if parent is None:
        raise ValueError('Paragraph parent was not found')
    paragraph = ET.Element(W + 'p')
    properties = reference.find(W + 'pPr')
    if properties is not None:
        paragraph.append(deepcopy(properties))
    _append_text_run(paragraph, text, _run_properties(reference))
    parent.insert(list(parent).index(reference) + 1, paragraph)
    return paragraph


def _replace_or_insert_valley_constraints(root: ET.Element) -> None:
    first_condition = _find_paragraph(root, '第一，双侧峰值支撑')
    _replace_text_paragraph(first_condition, VALLEY_CONSTRAINT_TEXT)


def _patch_algorithm_claims(root: ET.Element) -> None:
    direction = _find_paragraph(root, '实际拍摄中卡尺可能')
    _replace_mixed_paragraph(direction, [
        '实际拍摄中，卡尺与图像坐标轴之间可能存在轻微夹角，若不校正，主尺和游标尺刻线在投影方向上会发生偏移，'
        '影响后续刻线长度测量和横向峰段定位。当前实现以接缝为整体方向证据：先在 0.75 倍尺度的增强灰度图和二值图中，'
        '由刻线带谷底及 ROI 高度的 0.58H、0.64H、0.70H 等位置生成接缝种子；再在各种子邻域计算 Scharr 垂直梯度，'
        '逐列提取局部响应峰，形成接缝候选点。对候选点执行 RANSAC 拟合接缝候选点，得到直线模型 ',
        _inline_math('y=ax+b'), '，并以 ', _inline_math('θ=arctan(a)'), ' 估计旋转角。有效模型还需同时满足内点数、'
        '横向覆盖、拟合残差和中心位置的约束，且 ', _inline_math('|θ|'), ' 不超过 ', _inline_math('2°'),
        '；若没有有效模型，则令角度为 ', _inline_math('0°'), '。随后对彩色图、增强灰度图和二值图统一按该角度变换，'
        '使后续模块使用同一校正坐标系。',
    ])

    peak = _find_paragraph(root, '以投影强度为权重计算加权质心')
    _replace_mixed_paragraph(peak, [
        '其中 ', _inline_math(('sub', 'μ', 'P')), '、', _inline_math(('sub', 'σ', 'P')),
        ' 分别为平滑投影的均值和标准差。超过阈值 ', _inline_math(('sub', 'T', 'p')),
        ' 的连续前景段记为 ', _inline_math(('sub', 'S', 'k'), '=[', ('sub', 'a', 'k'), ',', ('sub', 'b', 'k'), ']'),
        '，每个峰段直接取峰段的几何中心作为粗候选刻线位置。',
    ])
    _replace_equation_math(
        _find_equation_paragraph(root, '(6)'),
        ('sub', 'x', 'k'), '=', 'floor(',
        ('frac', [('sub', 'a', 'k'), '+', ('sub', 'b', 'k')], ['2']), ')',
    )
    measure = _find_paragraph(root, '作为粗候选刻线位置，相比直接取峰值')
    _replace_mixed_paragraph(measure, [
        '随后在每个粗候选的 ', _inline_math('±3'), ' 像素邻域内沿列累加前景像素，得到列强度曲线 ',
        _inline_math('c(y)'), '，以 ',
        _inline_math(('sub', 'τ', 'c'), '=max(30,min(0.4max(c),204))'), ' 提取连续前景段，保留长度不小于 ',
        _inline_math(('sub', 'L', 'min'), '=max(6,0.25', ('sub', 'H', 'band'), ')'),
        ' 的段作为常规刻线。对于较短但周期位置一致、连续长度和前景量均满足条件的候选，系统执行短刻线恢复。'
        '刻线横坐标再在增强灰度图上进行亚像素精化：对左右边缘梯度极值中点取中位数，以减小二值化和线宽变化造成的位置误差。',
    ])

    _replace_or_insert_valley_constraints(root)

    component = _find_paragraph(root, '确定游标横向范围后，系统提取高于动态阈值')
    _replace_mixed_paragraph(component, [
        '确定游标横向范围后，系统先将高于动态阈值 ', _inline_math(('sub', 'T', 't'), '=μ+0.8σ'),
        ' 的连续投影峰段中心作为初始刻线候选。随后提取局部连通域，借助其细长形态、纵向延伸、靠近刻线带上缘的关系和'
        '局部连续性抑制数字笔画与噪声。连通域提取前，先桥接同列内间隔不超过 ', _inline_math('10'),
        ' 像素的短竖直空隙，再以高度为 ', _inline_math('7'), ' 像素的竖直开运算抑制横向噪声。候选连通域需靠近刻线带上缘，'
        '高度不低于刻线带高度的 ', _inline_math('0.35'), ' 倍，宽度不超过 ', _inline_math('0.75p'),
        '；其与投影候选在 ', _inline_math('max(4,min(12,0.42p))'), ' 的搜索半径内按距离优先、投影强度次优完成匹配。',
    ])
    component_role = _find_paragraph(root, '游标尺上的数字“0”等字符可能')
    _replace_mixed_paragraph(component_role, [
        '连通域并非投影候选的硬性准入条件，而是提供结构支持、候选匹配、质量排序和重复响应去重的证据。间距小于 ',
        _inline_math('0.65p'), ' 的重复候选优先保留具有连通域支持、投影更强且面积更大的候选。顶部细线验证只用于剔除'
        '第一个具有顶部细线证据的刻线之前的前缀候选，后续刻线不要求逐条通过该条件。顶部细线追踪的最大宽度、'
        '允许短空隙和最小高度依次受 ', _inline_math('max(4,min(8,0.17p))'), '、',
        _inline_math('max(1,min(4,0.08p))'), ' 和 ', _inline_math('max(12,0.28H)'),
        ' 约束。真实零线与数字“0”粘连时，若竖直桥接后的较高连通域证明其从刻线带上缘向下贯通，仍可作为保留该候选的结构证据。',
    ])

    zero = _find_paragraph(root, '在完整游标刻线范围内，第一条通过结构验证')
    _replace_mixed_paragraph(zero, [
        '在由左右谷底限定的有效范围内，系统先完成前缀干扰抑制和重复候选去重，得到最终游标刻线序列。该序列的第一条刻线，'
        '即 ', _inline_math(('sub', 'tick', 'xs'), '[0]'), '，定义为游标零刻度线；在最终输出的刻线对象中，再选择横向位置'
        '最接近该位置的一条作为零线。零线是主尺整数读数和游标小数读数的共同基准，其位置错误会同时影响两部分读数。',
    ])
    zero_evidence = _find_paragraph(root, '零刻度线不直接取投影范围内最左侧的峰')
    _replace_text_paragraph(zero_evidence, ZERO_LINE_EVIDENCE_TEXT)

    _replace_equation_math(
        _find_equation_paragraph(root, '(11)'),
        ('sub', 'e', 'i'), '=', ('sub', 'min', 'j'), '|', ('sup', 'x', '*'), '(', ('sub', 'v', 'i'),
        ')-', ('sup', 'x', '*'), '(', ('sub', 'm', 'j'), ')|',
    )
    alignment = _find_paragraph(root, '纵向重叠约束保证只有物理上可能对齐')
    _replace_mixed_paragraph(alignment, [
        '其中，', _inline_math(('sub', 'e', 'i')), ' 为第 ', _inline_math('i'),
        ' 条游标刻线与全部已检测主尺刻线之间的最小横向对齐误差，', _inline_math(('sup', 'x', '*')),
        ' 为 4.1 节得到的亚像素刻线横坐标；计算时不以纵向重叠作为硬过滤条件。正式读数仅在自零线起的前 ',
        _inline_math('min(N,50)'), ' 条游标刻线中选择误差最小者，其中 ', _inline_math('50=1/0.02'),
        ' 对应当前 0.02 mm 分度卡尺的最大有效索引范围，并非强制拟合 51 条刻线。亚像素坐标仅用于误差比较；'
        '在误差极小刻线附近进行的抛物线插值只用于歧义分析，不改变 ', _inline_math('0.02 mm'), ' 的离散输出。',
    ])


def patch_document(input_docx: Path, output_docx: Path) -> None:
    """Write an audited copy of *input_docx* to *output_docx*."""
    input_docx = Path(input_docx)
    output_docx = Path(output_docx)
    with zipfile.ZipFile(input_docx, 'r') as source:
        entries = {name: source.read(name) for name in source.namelist()}

    root = ET.fromstring(entries['word/document.xml'])
    _patch_algorithm_claims(root)
    entries['word/document.xml'] = ET.tostring(
        root, encoding='utf-8', xml_declaration=True
    )

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_docx, 'w', compression=zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(name, data)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate an algorithm-consistency-audited paper DOCX.'
    )
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    patch_document(args.input, args.output)
    print(args.output)
