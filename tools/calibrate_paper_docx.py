from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET


NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W = "{" + NS_W + "}"
M = "{" + NS_M + "}"

ET.register_namespace("w", NS_W)
ET.register_namespace("m", NS_M)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "paper" / "02_Word版本" / "游标卡尺识别论文主体_参考格式_含插图.docx"
DEFAULT_REFERENCE = Path(r"E:/朱/论文编号为 9952644的论文正文脱敏版本.docx")
DEFAULT_OUTPUT = ROOT / "paper" / "02_Word版本" / "游标卡尺识别论文主体_最终排版.docx"


def q(name: str) -> str:
    return W + name


def text_of(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//" + q("t")))


def ppr(paragraph: ET.Element) -> ET.Element:
    node = paragraph.find(q("pPr"))
    if node is None:
        node = ET.Element(q("pPr"))
        paragraph.insert(0, node)
    return node


def clear_children(node: ET.Element) -> None:
    for child in list(node):
        node.remove(child)


def set_attrs(node: ET.Element, attrs: dict[str, str]) -> None:
    node.attrib.clear()
    node.attrib.update({q(key): value for key, value in attrs.items()})


def add_ppr_format(
    paragraph: ET.Element,
    *,
    style: str | None = None,
    jc: str | None = None,
    spacing: dict[str, str] | None = None,
    ind: dict[str, str] | None = None,
    font: str | None = None,
    size: str | None = None,
    bold: bool = False,
) -> None:
    """Replace direct paragraph formatting with schema-ordered properties."""
    node = ppr(paragraph)
    clear_children(node)
    if style:
        ET.SubElement(node, q("pStyle"), {q("val"): style})
    if spacing:
        ET.SubElement(node, q("spacing"), {q(k): v for k, v in spacing.items()})
    if ind:
        ET.SubElement(node, q("ind"), {q(k): v for k, v in ind.items()})
    if jc:
        ET.SubElement(node, q("jc"), {q("val"): jc})
    if font or size or bold:
        rpr = ET.SubElement(node, q("rPr"))
        if font:
            ET.SubElement(
                rpr,
                q("rFonts"),
                {
                    q("ascii"): font,
                    q("eastAsia"): font,
                    q("hAnsi"): font,
                    q("cs"): font,
                    q("hint"): "eastAsia",
                },
            )
        if size:
            ET.SubElement(rpr, q("sz"), {q("val"): size})
            ET.SubElement(rpr, q("szCs"), {q("val"): size})
        if bold:
            ET.SubElement(rpr, q("b"))


def set_run_format(run: ET.Element, font: str, size: str, *, bold: bool = False) -> None:
    rpr = run.find(q("rPr"))
    if rpr is None:
        rpr = ET.Element(q("rPr"))
        run.insert(0, rpr)
    clear_children(rpr)
    ET.SubElement(
        rpr,
        q("rFonts"),
        {
            q("ascii"): font,
            q("eastAsia"): font,
            q("hAnsi"): font,
            q("cs"): font,
            q("hint"): "eastAsia",
        },
    )
    ET.SubElement(rpr, q("sz"), {q("val"): size})
    ET.SubElement(rpr, q("szCs"), {q("val"): size})
    if bold:
        ET.SubElement(rpr, q("b"))


def make_run(value: str, font: str, size: str, *, bold: bool = False) -> ET.Element:
    run = ET.Element(q("r"))
    set_run_format(run, font, size, bold=bold)
    text = ET.SubElement(run, q("t"))
    if value.startswith(" ") or value.endswith(" "):
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = value
    return run


def merge_labeled_paragraph(
    label_paragraph: ET.Element,
    body_paragraph: ET.Element,
    body: ET.Element,
    label: str,
    *,
    body_font: str,
) -> None:
    label_text = label_paragraph.find(q("pPr"))
    clear_children(label_paragraph)
    if label_text is not None:
        label_paragraph.append(label_text)
    label_paragraph.append(make_run(label, "黑体" if body_font == "宋体" else "Times New Roman", "21", bold=True))
    body_text = text_of(body_paragraph)
    if body_text:
        label_paragraph.append(make_run(body_text, body_font, "21"))
    body.remove(body_paragraph)


def is_heading(value: str) -> bool:
    return bool(re.match(r"^\s*(?:引\s*言|结束语|参考文献|\d+(?:\.\d+)*)", value))


def is_caption(value: str) -> bool:
    return bool(re.match(r"^\s*图\s*\d+\b", value))


def is_table_caption(value: str) -> bool:
    return bool(re.match(r"^\s*表\s*\d+\b", value))


def format_front_matter(paragraphs: list[ET.Element], body: ET.Element) -> None:
    if not paragraphs:
        return
    add_ppr_format(
        paragraphs[0],
        jc="center",
        spacing={"after": "0", "line": "240", "lineRule": "auto"},
        ind={"left": "662", "firstLine": "178"},
    )
    for run in paragraphs[0].findall(q("r")):
        set_run_format(run, "宋体", "44")

    if len(paragraphs) > 1:
        add_ppr_format(
            paragraphs[1],
            jc="center",
            spacing={"line": "240", "lineRule": "auto"},
        )
        for run in paragraphs[1].findall(q("r")):
            set_run_format(run, "仿宋", "21")

    # Pandoc creates a heading paragraph followed by the abstract body.
    abstract_label = next((p for p in list(body) if text_of(p).strip().startswith("摘")), None)
    abstract_body = None
    if abstract_label is not None:
        children = list(body)
        index = children.index(abstract_label)
        if index + 1 < len(children) and children[index + 1].tag == q("p"):
            abstract_body = children[index + 1]
    if abstract_label is not None and abstract_body is not None:
        merge_labeled_paragraph(abstract_label, abstract_body, body, "摘  要: ", body_font="宋体")
        add_ppr_format(
            abstract_label,
            style="1",
            jc="left",
            spacing={"line": "240", "lineRule": "auto"},
        )
        for run in abstract_label.findall(q("r")):
            if text_of(run).startswith("摘"):
                set_run_format(run, "黑体", "21", bold=True)
            else:
                set_run_format(run, "宋体", "21")

    paragraphs = body.findall(q("p"))
    for p in paragraphs:
        value = text_of(p).strip()
        if value.startswith("关键词"):
            add_ppr_format(
                p,
                spacing={"after": "271", "line": "255", "lineRule": "auto"},
                ind={"left": "18", "right": "257", "hanging": "10"},
            )
            for run in p.findall(q("r")):
                set_run_format(run, "宋体", "21", bold=value.startswith("关键词"))
        elif value.startswith("中图分类号"):
            add_ppr_format(
                p,
                spacing={"after": "271", "line": "255", "lineRule": "auto"},
                ind={"left": "18", "right": "257", "hanging": "10"},
            )
            for run in p.findall(q("r")):
                set_run_format(run, "黑体", "21")

    for p in body.findall(q("p")):
        value = text_of(p).strip()
        if value.startswith(("Design", "Automatic")):
            add_ppr_format(
                p,
                style="1",
                jc="center",
                spacing={"after": "122", "line": "259", "lineRule": "auto"},
            )
            for run in p.findall(q("r")):
                set_run_format(run, "Times New Roman", "26", bold=True)
        elif value.startswith("Author"):
            add_ppr_format(p, jc="center", spacing={"line": "240", "lineRule": "auto"})
            for run in p.findall(q("r")):
                set_run_format(run, "Times New Roman", "21")

    english_label = next((p for p in body.findall(q("p")) if text_of(p).strip() == "Abstract"), None)
    english_body = None
    if english_label is not None:
        children = list(body)
        index = children.index(english_label)
        if index + 1 < len(children) and children[index + 1].tag == q("p"):
            english_body = children[index + 1]
    if english_label is not None and english_body is not None:
        merge_labeled_paragraph(english_label, english_body, body, "Abstract: ", body_font="Times New Roman")
        add_ppr_format(
            english_label,
            jc="left",
            spacing={"after": "10", "line": "240", "lineRule": "auto"},
            ind={"left": "8"},
        )
        for run in english_label.findall(q("r")):
            set_run_format(run, "Times New Roman", "21", bold=run is english_label.find(q("r")))

    for p in body.findall(q("p")):
        value = text_of(p).strip()
        if value.startswith("Key words"):
            add_ppr_format(p, spacing={"after": "161", "line": "240", "lineRule": "auto"})
            for run in p.findall(q("r")):
                set_run_format(run, "Times New Roman", "21")


def format_body_paragraphs(body: ET.Element) -> None:
    body_started = False
    for p in body.findall(q("p")):
        if p.find(".//" + M + "oMathPara") is not None:
            add_ppr_format(
                p,
                spacing={"after": "10", "line": "240", "lineRule": "auto"},
                ind={"left": "8", "firstLine": "410"},
            )
            continue
        style_node = p.find(q("pPr") + "/" + q("pStyle"))
        if style_node is not None and style_node.get(q("val")) == "CaptionedFigure":
            add_ppr_format(
                p,
                jc="center",
                spacing={"after": "0", "line": "240", "lineRule": "auto"},
            )
            ppr = p.find(q("pPr"))
            keep = ET.Element(q("keepNext"))
            pstyle = ppr.find(q("pStyle"))
            if pstyle is not None:
                ppr.insert(list(ppr).index(pstyle) + 1, keep)
            else:
                ppr.insert(0, keep)
            continue
        value = text_of(p).strip()
        if not value:
            continue
        if not body_started:
            if value.startswith("引"):
                body_started = True
            else:
                continue
        if is_caption(value):
            add_ppr_format(
                p,
                style="ImageCaption",
                jc="center",
                spacing={"after": "120", "line": "240", "lineRule": "exact"},
                font="楷体",
                size="18",
            )
            for run in p.findall(q("r")):
                set_run_format(run, "楷体", "18")
            continue
        if is_table_caption(value):
            add_ppr_format(
                p,
                jc="center",
                spacing={"before": "120", "after": "0", "line": "240", "lineRule": "exact"},
                font="黑体",
                size="18",
            )
            for run in p.findall(q("r")):
                set_run_format(run, "黑体", "18")
            continue
        if is_heading(value):
            add_ppr_format(
                p,
                jc="left",
                spacing={"after": "145", "line": "255", "lineRule": "auto"},
                font="黑体",
                size="21",
            )
            for run in p.findall(q("r")):
                set_run_format(run, "黑体", "21")
            continue
        add_ppr_format(
            p,
            spacing={"after": "10", "line": "240", "lineRule": "auto"},
            ind={"left": "6", "firstLine": "408"},
            font="宋体",
            size="21",
        )
        for run in p.findall(q("r")):
            set_run_format(run, "宋体", "21")


def number_equations(body: ET.Element) -> None:
    counter = 0
    for p in body.findall(q("p")):
        if p.find(".//" + M + "oMathPara") is None:
            continue
        counter += 1
        ppr = p.find(q("pPr"))
        if ppr is None:
            ppr = ET.Element(q("pPr"))
            p.insert(0, ppr)
        tabs = ppr.find(q("tabs"))
        if tabs is not None:
            ppr.remove(tabs)
        tabs = ET.Element(q("tabs"))
        ET.SubElement(tabs, q("tab"), {q("val"): "right", q("pos"): "4800"})
        ppr.insert(0, tabs)
        run = ET.SubElement(p, q("r"))
        set_run_format(run, "Times New Roman", "21")
        ET.SubElement(run, q("tab"))
        text = ET.SubElement(run, q("t"))
        text.text = f"({counter})"


def border(parent: ET.Element, name: str, value: str, size: str) -> None:
    node = parent.find(q(name))
    if node is None:
        node = ET.SubElement(parent, q(name))
    set_attrs(node, {"val": value, "sz": size, "space": "0", "color": "auto"})


def format_tables(body: ET.Element) -> None:
    for table in body.findall(q("tbl")):
        tblpr = table.find(q("tblPr"))
        if tblpr is None:
            tblpr = ET.Element(q("tblPr"))
            table.insert(0, tblpr)
        style = tblpr.find(q("tblStyle"))
        if style is None:
            style = ET.SubElement(tblpr, q("tblStyle"))
        style.set(q("val"), "a3")
        borders = tblpr.find(q("tblBorders"))
        if borders is None:
            borders = ET.SubElement(tblpr, q("tblBorders"))
        border(borders, "top", "single", "12")
        border(borders, "bottom", "single", "12")
        border(borders, "left", "none", "0")
        border(borders, "right", "none", "0")
        border(borders, "insideH", "none", "0")
        border(borders, "insideV", "none", "0")
        layout = tblpr.find(q("tblLayout"))
        if layout is None:
            ET.SubElement(tblpr, q("tblLayout"), {q("type"): "fixed"})
        rows = table.findall(q("tr"))
        for row_index, row in enumerate(rows):
            cells = row.findall(q("tc"))
            for cell in cells:
                tcpr = cell.find(q("tcPr"))
                if tcpr is None:
                    tcpr = ET.Element(q("tcPr"))
                    cell.insert(0, tcpr)
                valign = tcpr.find(q("vAlign"))
                if valign is None:
                    ET.SubElement(tcpr, q("vAlign"), {q("val"): "center"})
                cell_borders = tcpr.find(q("tcBorders"))
                if cell_borders is None:
                    cell_borders = ET.SubElement(tcpr, q("tcBorders"))
                if row_index == 0:
                    border(cell_borders, "top", "single", "8")
                    border(cell_borders, "bottom", "single", "4")
                if row_index == len(rows) - 1:
                    border(cell_borders, "bottom", "single", "8")
                for p in cell.findall(q("p")):
                    add_ppr_format(p, jc="center", spacing={"after": "0", "line": "240", "lineRule": "auto"})
                    for run in p.findall(q("r")):
                        set_run_format(run, "宋体", "18")


def remove_duplicate_captions(body: ET.Element) -> None:
    children = list(body)
    for index, current in enumerate(children[:-1]):
        if current.tag != q("p"):
            continue
        style = current.find(q("pPr") + "/" + q("pStyle"))
        if style is None or style.get(q("val")) != "ImageCaption":
            continue
        following = children[index + 1]
        if following.tag != q("p") or text_of(following) != text_of(current):
            continue
        body.remove(following)


def clean_section(section: ET.Element) -> ET.Element:
    result = deepcopy(section)
    for child in list(result):
        if child.tag in {q("headerReference"), q("footerReference")}:
            result.remove(child)
    return result


def insert_section_break(paragraph: ET.Element, section: ET.Element) -> None:
    node = ppr(paragraph)
    for child in list(node):
        if child.tag == q("sectPr"):
            node.remove(child)
    node.append(clean_section(section))


def format_sections(root: ET.Element, reference_root: ET.Element) -> None:
    body = root.find(q("body"))
    reference_body = reference_root.find(q("body"))
    if body is None or reference_body is None:
        return
    for paragraph in body.findall(q("p")):
        node = paragraph.find(q("pPr"))
        if node is not None:
            for child in list(node):
                if child.tag == q("sectPr"):
                    node.remove(child)
    ref_p_sections = [
        paragraph.find(q("pPr") + "/" + q("sectPr"))
        for paragraph in reference_body.findall(q("p"))
        if paragraph.find(q("pPr") + "/" + q("sectPr")) is not None
    ]
    ref_final = reference_body.find(q("sectPr"))
    if len(ref_p_sections) < 2 or ref_final is None:
        return
    paragraphs = body.findall(q("p"))
    front_break = next((p for p in paragraphs if text_of(p).strip().startswith("Key words")), None)
    if front_break is None:
        front_break = next((p for p in paragraphs if text_of(p).strip().startswith("关键词")), None)
    if front_break is not None:
        insert_section_break(front_break, ref_p_sections[0])

    references = [p for p in paragraphs if text_of(p).strip().startswith("参考文献")]
    last = paragraphs[-1] if paragraphs else None
    if references and last is not None:
        insert_section_break(last, ref_p_sections[1])
    current_final = body.find(q("sectPr"))
    if current_final is not None:
        body.remove(current_final)
    body.append(clean_section(ref_final))


def calibrate_docx(input_docx: Path, reference_docx: Path, output_docx: Path) -> None:
    with zipfile.ZipFile(input_docx, "r") as source:
        entries = {name: source.read(name) for name in source.namelist()}
    with zipfile.ZipFile(reference_docx, "r") as reference:
        reference_root = ET.fromstring(reference.read("word/document.xml"))
    root = ET.fromstring(entries["word/document.xml"])
    body = root.find(q("body"))
    if body is None:
        raise ValueError("input document has no w:body")

    paragraphs = body.findall(q("p"))
    format_front_matter(paragraphs, body)
    remove_duplicate_captions(body)
    format_body_paragraphs(body)
    number_equations(body)
    format_tables(body)
    format_sections(root, reference_root)

    entries["word/document.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_docx, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(name, data)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    calibrate_docx(args.input, args.reference, args.output)
    print(args.output)
