from __future__ import annotations

from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET


NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_DCTERMS = "http://purl.org/dc/terms/"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
W = "{" + NS_W + "}"
DC = "{" + NS_DC + "}"

ET.register_namespace("w", NS_W)
ET.register_namespace("cp", NS_CP)
ET.register_namespace("dc", NS_DC)
ET.register_namespace("dcterms", NS_DCTERMS)
ET.register_namespace("xsi", NS_XSI)


def _blank_part(kind: str) -> bytes:
    root = ET.Element(W + kind)
    # Word's CT_HdrFtr content model requires at least one block-level
    # element. LibreOffice accepts an empty header/footer, but Word opens it
    # with a repair warning, so retain a legal empty paragraph.
    ET.SubElement(root, W + "p")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def blank_headers_footers(input_docx: Path, output_docx: Path) -> None:
    with zipfile.ZipFile(input_docx, "r") as source:
        entries = {name: source.read(name) for name in source.namelist()}

    for name in list(entries):
        if name.startswith("word/header") and name.endswith(".xml"):
            entries[name] = _blank_part("hdr")
        elif name.startswith("word/footer") and name.endswith(".xml"):
            entries[name] = _blank_part("ftr")

    core_name = "docProps/core.xml"
    if core_name in entries:
        root = ET.fromstring(entries[core_name])
        title = root.find(DC + "title")
        creator = root.find(DC + "creator")
        if title is None:
            title = ET.SubElement(root, DC + "title")
        if creator is None:
            creator = ET.SubElement(root, DC + "creator")
        title.text = "基于机器视觉的游标卡尺自动读数识别系统设计"
        creator.text = "待补"
        entries[core_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_docx, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(name, data)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    blank_headers_footers(args.input, args.output)
    print(args.output)
