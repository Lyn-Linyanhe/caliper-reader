from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "paper" / "02_Word版本" / "\u6e38\u6807\u5361\u5c3a\u8bc6\u522b\u8bba\u6587\u4e3b\u4f53_\u6700\u7ec8\u6392\u7248.docx"
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS_CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"


def _root() -> ET.Element:
    with zipfile.ZipFile(DOCX, "r") as archive:
        return ET.fromstring(archive.read("word/document.xml"))


def test_word_package_metadata_and_blank_headers_are_word_compatible():
    with zipfile.ZipFile(DOCX, "r") as archive:
        core_bytes = archive.read("docProps/core.xml")
        core = ET.fromstring(core_bytes)
        assert core.tag == "{%s}coreProperties" % NS_CP
        assert b"xmlns:dcterms=" in core_bytes
        created = core.find("{http://purl.org/dc/terms/}created")
        assert created is not None
        assert created.attrib.get("{%s}type" % NS_XSI) == "dcterms:W3CDTF"
        for name in archive.namelist():
            if not (name.startswith("word/header") or name.startswith("word/footer")):
                continue
            part = ET.fromstring(archive.read(name))
            assert part.find(_w("p")) is not None, f"{name} has no block-level paragraph"


def _w(name: str) -> str:
    return "{%s}%s" % (NS_W, name)


def test_three_sections_with_double_column_body():
    root = _root()
    sections = root.findall(".//" + _w("sectPr"))
    assert len(sections) >= 3
    columns = [
        section.find(_w("cols"))
        for section in sections
        if section.find(_w("cols")) is not None
    ]
    assert any(
        column.attrib.get(_w("num")) == "2"
        for column in columns
    )


def test_title_uses_reference_direct_format():
    root = _root()
    body = root.find(_w("body"))
    first = body.find(_w("p"))
    jc = first.find(_w("pPr") + "/" + _w("jc"))
    run = first.find(_w("r"))
    fonts = run.find(_w("rPr") + "/" + _w("rFonts"))
    size = run.find(_w("rPr") + "/" + _w("sz"))
    assert jc.attrib.get(_w("val")) == "center"
    assert fonts.attrib.get(_w("eastAsia")) == "\u5b8b\u4f53"
    assert size.attrib.get(_w("val")) == "44"


def test_figures_have_visible_captions_and_fit_column():
    root = _root()
    figures = root.findall(".//{%s}docPr" % NS_WP)
    paragraphs = root.findall(".//" + _w("body") + "/" + _w("p"))
    image_captions = []
    for paragraph in paragraphs:
        style = paragraph.find(_w("pPr") + "/" + _w("pStyle"))
        if style is not None and style.attrib.get(_w("val")) == "ImageCaption":
            text = "".join(t.text or "" for t in paragraph.findall(".//" + _w("t")))
            image_captions.append(text)
    assert len(figures) == 12
    assert len(image_captions) == 12
    assert all(text.startswith("\u56fe ") for text in image_captions)
    extents = root.findall(".//{%s}extent" % NS_WP)
    assert len(extents) == len(figures)
    for extent in extents:
        width_points = int(extent.get("cx")) / 12700
        assert width_points <= 260, "figure wider than double column"
    for paragraph in paragraphs:
        if paragraph.find(".//{%s}docPr" % NS_WP) is None:
            continue
        ppr = paragraph.find(_w("pPr"))
        assert ppr is not None, "figure paragraph has no pPr"
        assert ppr.find(_w("keepNext")) is not None, "figure paragraph missing keepNext"
        jc = ppr.find(_w("jc"))
        assert jc is not None and jc.attrib.get(_w("val")) == "center", "figure paragraph not centered"
    for paragraph in paragraphs:
        style = paragraph.find(_w("pPr") + "/" + _w("pStyle"))
        if style is None or style.attrib.get(_w("val")) != "ImageCaption":
            continue
        fonts = paragraph.find(_w("pPr") + "/" + _w("rPr") + "/" + _w("rFonts"))
        if fonts is None:
            fonts = paragraph.find(_w("r") + "/" + _w("rPr") + "/" + _w("rFonts"))
        assert fonts is not None, "caption missing rFonts"
        assert fonts.attrib.get(_w("eastAsia")) == "\u6977\u4f53", "caption font not kaiti"
        sz = paragraph.find(_w("pPr") + "/" + _w("rPr") + "/" + _w("sz"))
        if sz is None:
            sz = paragraph.find(_w("r") + "/" + _w("rPr") + "/" + _w("sz"))
        assert sz is not None and sz.attrib.get(_w("val")) == "18", "caption size not 18"



def test_display_equations_are_numbered():
    root = _root()
    paragraphs = root.findall(".//" + _w("body") + "/" + _w("p"))
    numbered = []
    for paragraph in paragraphs:
        if paragraph.find(".//{%s}oMathPara" % NS_M) is None:
            continue
        text = "".join(t.text or "" for t in paragraph.findall(".//" + _w("t")))
        tabs = paragraph.findall(".//" + _w("tabs") + "/" + _w("tab"))
        if text and tabs:
            numbered.append(text)
    assert len(numbered) >= 6


def test_tables_use_three_line_reference_style():
    root = _root()
    tables = root.findall(".//" + _w("tbl"))
    # 正文保留表 1、表 3、表 4；实现参数表 2 已按方法层级原则删除
    assert len(tables) >= 3
    for table in tables:
        tblpr = table.find(_w("tblPr"))
        style = tblpr.find(_w("tblStyle"))
        borders = tblpr.find(_w("tblBorders"))
        assert style.attrib.get(_w("val")) == "a3"
        top = borders.find(_w("top"))
        bottom = borders.find(_w("bottom"))
        assert top.attrib.get(_w("val")) == "single"
        assert bottom.attrib.get(_w("val")) == "single"
