import xml.etree.ElementTree as ET
import tempfile
import zipfile
from pathlib import Path

from tools import embed_flowchart_vector_in_paper as embedder


CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"


def test_patch_content_types_declares_raster_parts_and_svg():
    source = (
        f'<Types xmlns="{CONTENT_TYPES}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml" />'
        '</Types>'
    ).encode("utf-8")

    root = ET.fromstring(embedder.patch_content_types(source))
    defaults = {
        element.attrib["Extension"]: element.attrib["ContentType"]
        for element in root
        if element.tag.endswith("Default")
    }

    assert defaults["png"] == "image/png"
    assert defaults["emf"] == "image/x-emf"
    assert defaults["svg"] == "image/svg+xml"
    assert not any(
        element.attrib.get("ContentType") == "image/svg+xml"
        for element in root
        if element.tag.endswith("Override")
    )


def test_patch_document_xml_uses_word_native_svg_extension_shape():
    source = (
        b'<w:document xmlns:w="urn:test">'
        b'<ns1:extent cx="3048000" cy="1524000" />'
        b'<ns2:ext cx="3048000" cy="1524000" />'
        + '论文图表素材/论文插图/图01_系统流程图.png'.encode("utf-8")
        + b'<ns2:blip ns4:embed="rId40" />'
        + b'</w:document>'
    )

    patched = embedder.patch_document_xml(source)

    assert b'<w:document xmlns:asvg=' not in patched
    assert b'<ns2:blip ns4:embed="rId40" cstate="print">' in patched
    assert b'<a14:useLocalDpi xmlns:a14=' in patched
    assert b'<asvg:svgBlip xmlns:asvg=' in patched


def test_repair_docx_content_types_preserves_all_other_package_parts():
    with tempfile.TemporaryDirectory(prefix=".tmp_docx_test_", dir=Path.cwd()) as folder:
        folder = Path(folder)
        source = folder / "source.docx"
        repaired = folder / "repaired.docx"
        content_types = (
            f'<Types xmlns="{CONTENT_TYPES}">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />'
            '</Types>'
        ).encode("utf-8")
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("word/document.xml", b"document")
            archive.writestr("word/media/image1.emf", b"emf")
            archive.writestr("word/media/image2.png", b"png")

        embedder.repair_docx_content_types(source, repaired)

        with zipfile.ZipFile(repaired) as archive:
            assert archive.read("word/document.xml") == b"document"
            root = ET.fromstring(archive.read("[Content_Types].xml"))
            defaults = {
                element.attrib["Extension"]: element.attrib["ContentType"]
                for element in root
                if element.tag.endswith("Default")
            }
            assert defaults["png"] == "image/png"
            assert defaults["emf"] == "image/x-emf"
