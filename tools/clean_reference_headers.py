from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET


NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_DCTERMS = "http://purl.org/dc/terms/"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("w", NS_W)
ET.register_namespace("", NS_REL)
ET.register_namespace("cp", NS_CP)
ET.register_namespace("dc", NS_DC)
ET.register_namespace("dcterms", NS_DCTERMS)
ET.register_namespace("xsi", NS_XSI)


def blank_part(kind: str) -> bytes:
    tag = "hdr" if kind == "header" else "ftr"
    root = ET.Element(f"{{{NS_W}}}{tag}")
    # Keep the header/footer part valid for Word even when it has no visible
    # content. An empty part is tolerated by LibreOffice but triggers repair.
    ET.SubElement(root, f"{{{NS_W}}}p")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def clean(input_docx: Path, output_docx: Path) -> None:
    with zipfile.ZipFile(input_docx, "r") as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}

    # Pandoc can emit both an ImageCaption paragraph (generated from the
    # implicit figure) and a second ordinary paragraph when the source also
    # contains an explicit caption line. Keep the styled ImageCaption only.
    document_name = "word/document.xml"
    if document_name in entries:
        root = ET.fromstring(entries[document_name])
        body = root.find(f"{{{NS_W}}}body")
        if body is not None:
            children = list(body)
            remove = set()
            for index, child in enumerate(children[:-1]):
                if child.tag != f"{{{NS_W}}}p":
                    continue
                style = child.find(f"./{{{NS_W}}}pPr/{{{NS_W}}}pStyle")
                if style is None or style.attrib.get(f"{{{NS_W}}}val") != "ImageCaption":
                    continue
                caption = "".join(t.text or "" for t in child.findall(f".//{{{NS_W}}}t"))
                nxt = children[index + 1]
                if nxt.tag != f"{{{NS_W}}}p":
                    continue
                next_style = nxt.find(f"./{{{NS_W}}}pPr/{{{NS_W}}}pStyle")
                next_text = "".join(t.text or "" for t in nxt.findall(f".//{{{NS_W}}}t"))
                if (
                    next_style is not None
                    and next_style.attrib.get(f"{{{NS_W}}}val") == "BodyText"
                    and next_text == caption
                ):
                    remove.add(nxt)
            for child in remove:
                body.remove(child)
        entries[document_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    # The reference file contains running headers/footers from a different
    # article. Keep the page geometry and styles, but remove those contents.
    for name in list(entries):
        if name.startswith("word/header") and name.endswith(".xml"):
            entries[name] = blank_part("header")
        elif name.startswith("word/footer") and name.endswith(".xml"):
            entries[name] = blank_part("footer")

    # Remove stale EMF relationships inherited from the reference document.
    for name in list(entries):
        if not name.endswith(".rels"):
            continue
        try:
            root = ET.fromstring(entries[name])
        except ET.ParseError:
            continue
        changed = False
        for rel in list(root):
            target = rel.attrib.get("Target", "")
            if target.lower().endswith(".emf"):
                root.remove(rel)
                changed = True
        if changed:
            entries[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    for name in list(entries):
        if name.startswith("word/media/") and name.lower().endswith(".emf"):
            del entries[name]

    # Drop an unused EMF content-type declaration if present.
    ct_name = "[Content_Types].xml"
    if ct_name in entries:
        root = ET.fromstring(entries[ct_name])
        changed = False
        for child in list(root):
            ext = child.attrib.get("Extension", "").lower()
            part = child.attrib.get("PartName", "").lower()
            if ext == "emf" or part.endswith(".emf"):
                root.remove(child)
                changed = True
        if changed:
            entries[ct_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    core_name = "docProps/core.xml"
    if core_name in entries:
        root = ET.fromstring(entries[core_name])
        title = root.find(f"{{{NS_DC}}}title")
        creator = root.find(f"{{{NS_DC}}}creator")
        if title is None:
            title = ET.SubElement(root, f"{{{NS_DC}}}title")
        if creator is None:
            creator = ET.SubElement(root, f"{{{NS_DC}}}creator")
        title.text = "基于机器视觉的游标卡尺自动读数识别系统设计"
        creator.text = "待补"
        entries[core_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_docx, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in entries.items():
            zout.writestr(name, data)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    src = root / "paper" / "02_Word版本" / "游标卡尺识别论文主体_最终排版.docx"
    dst = root / "paper" / "02_Word版本" / "游标卡尺识别论文主体_最终排版.docx"
    clean(src, dst)
    print(dst)
