from __future__ import annotations

from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET


NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{" + NS_W + "}"


def _text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//" + W + "t"))


def _attrs(node: ET.Element | None) -> dict:
    if node is None:
        return {}
    return {key.split("}")[-1]: value for key, value in node.attrib.items()}


def _paragraph_format(paragraph: ET.Element) -> dict:
    ppr = paragraph.find(W + "pPr")
    result = {"style": "", "jc": "", "ind": {}, "spacing": {}}
    if ppr is None:
        return result
    style = ppr.find(W + "pStyle")
    jc = ppr.find(W + "jc")
    ind = ppr.find(W + "ind")
    spacing = ppr.find(W + "spacing")
    if style is not None:
        result["style"] = style.attrib.get(W + "val", "")
    if jc is not None:
        result["jc"] = jc.attrib.get(W + "val", "")
    result["ind"] = _attrs(ind)
    result["spacing"] = _attrs(spacing)
    return result


def _run_format(paragraph: ET.Element) -> dict:
    run = paragraph.find(".//" + W + "r")
    if run is None:
        return {}
    rpr = run.find(W + "rPr")
    if rpr is None:
        return {}
    result = {}
    fonts = rpr.find(W + "rFonts")
    if fonts is not None:
        result["fonts"] = _attrs(fonts)
    for tag in ("sz", "szCs", "b", "i", "color"):
        node = rpr.find(W + tag)
        if node is not None:
            result[tag] = _attrs(node)
    return result


def _first_paragraph_with_prefix(
    paragraphs: list[ET.Element], prefixes: tuple[str, ...]
) -> ET.Element:
    for paragraph in paragraphs:
        if _text(paragraph).lstrip().startswith(prefixes):
            return paragraph
    raise ValueError(f"paragraph not found: {prefixes}")


def extract_reference_format(reference_docx: Path) -> dict:
    """Extract the XML-level layout contract used by the calibration tests."""
    with zipfile.ZipFile(reference_docx, "r") as archive:
        root = ET.fromstring(archive.read("word/document.xml"))

    paragraphs = root.findall(".//" + W + "body/" + W + "p")
    section_nodes = root.findall(".//" + W + "sectPr")
    sections = []
    for section in section_nodes:
        sections.append(
            {
                child.tag.split("}")[-1]: _attrs(child)
                for child in section
                if child.tag in {W + "pgSz", W + "pgMar", W + "cols", W + "docGrid"}
            }
        )

    title = paragraphs[0]
    author = paragraphs[1]
    abstract = _first_paragraph_with_prefix(paragraphs, ("摘", "Abstract"))
    body_heading = _first_paragraph_with_prefix(paragraphs, ("引",))

    caption = next(
        paragraph
        for paragraph in paragraphs
        if _text(paragraph).lstrip().startswith(("图1", "图 1"))
    )
    table_caption = next(
        paragraph
        for paragraph in paragraphs
        if _text(paragraph).lstrip().startswith(("表1", "表 1"))
    )

    return {
        "page": sections[0],
        "sections": sections,
        "title": {"paragraph": _paragraph_format(title), "run": _run_format(title)},
        "author": {"paragraph": _paragraph_format(author), "run": _run_format(author)},
        "abstract": {
            "paragraph": _paragraph_format(abstract),
            "run": _run_format(abstract),
        },
        "body_heading": {
            "paragraph": _paragraph_format(body_heading),
            "run": _run_format(body_heading),
        },
        "caption": {
            "paragraph": _paragraph_format(caption),
            "run": _run_format(caption),
        },
        "table_caption": {
            "paragraph": _paragraph_format(table_caption),
            "run": _run_format(table_caption),
        },
        "table_count": len(root.findall(".//" + W + "tbl")),
    }


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(extract_reference_format(Path(sys.argv[1])), ensure_ascii=False, indent=2))
