"""Replace Figure 1 with the editable SVG flowchart and a compatible fallback.

The SVG is registered through the Office 2016 SVG extension while the existing
Figure 1 PNG relationship is retained as the fallback image.  This keeps the
document usable in older Word/LibreOffice versions without discarding the
vector asset.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


SVG_REL_ID = "rId101"
SVG_TARGET = "media/图01_系统流程图_visio.svg"
SVG_PACKAGE_PATH = "word/" + SVG_TARGET
SVG_CONTENT_TYPE = '<Override PartName="/word/media/图01_系统流程图_visio.svg" ContentType="image/svg+xml" />'
SVG_NAMESPACE = ' xmlns:asvg="http://schemas.microsoft.com/office/drawing/2016/SVG/main"'
SVG_EXT = (
    '<ns2:extLst><ns2:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}">'
    f'<asvg:svgBlip ns4:embed="{SVG_REL_ID}" />'
    "</ns2:ext></ns2:extLst>"
)


def replace_once(data: bytes, old: bytes, new: bytes, label: str) -> bytes:
    count = data.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label}, found {count}")
    return data.replace(old, new, 1)


def patch_document_xml(data: bytes) -> bytes:
    data = replace_once(
        data,
        b'<w:document ',
        b'<w:document' + SVG_NAMESPACE.encode("utf-8") + b' ',
        "document root",
    )
    data = replace_once(
        data,
        b'<ns1:extent cx="3048000" cy="1524000" />',
        b'<ns1:extent cx="3048000" cy="4308479" />',
        "Figure 1 inline extent",
    )
    data = replace_once(
        data,
        b'<ns2:ext cx="3048000" cy="1524000" />',
        b'<ns2:ext cx="3048000" cy="4308479" />',
        "Figure 1 picture extent",
    )
    data = replace_once(
        data,
        '论文图表素材/论文插图/图01_系统流程图.png'.encode("utf-8"),
        '论文图表素材/论文插图/图01_系统流程图_visio.svg'.encode("utf-8"),
        "Figure 1 description",
    )
    data = replace_once(
        data,
        b'<ns2:blip ns4:embed="rId40" />',
        f'<ns2:blip ns4:embed="rId40">{SVG_EXT}</ns2:blip>'.encode("utf-8"),
        "Figure 1 blip",
    )
    return data


def patch_relationships(data: bytes) -> bytes:
    relationship = (
        f'<Relationship Id="{SVG_REL_ID}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="{SVG_TARGET}" />'
    ).encode("utf-8")
    return replace_once(data, b"</Relationships>", relationship + b"</Relationships>", "document relationships")


def patch_content_types(data: bytes) -> bytes:
    return replace_once(data, b"</Types>", SVG_CONTENT_TYPE.encode("utf-8") + b"</Types>", "content types")


def build(input_docx: Path, output_docx: Path, svg_path: Path, fallback_png: Path) -> None:
    if not input_docx.is_file():
        raise FileNotFoundError(input_docx)
    if not svg_path.is_file():
        raise FileNotFoundError(svg_path)
    if not fallback_png.is_file():
        raise FileNotFoundError(fallback_png)

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_docx, "r") as source, zipfile.ZipFile(
        output_docx, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        names = set(source.namelist())
        required = {"word/document.xml", "word/_rels/document.xml.rels", "[Content_Types].xml", "word/media/rId40.png"}
        missing = required - names
        if missing:
            raise RuntimeError(f"Missing required DOCX parts: {sorted(missing)}")

        for item in source.infolist():
            name = item.filename
            if name == "word/document.xml":
                payload = patch_document_xml(source.read(name))
            elif name == "word/_rels/document.xml.rels":
                payload = patch_relationships(source.read(name))
            elif name == "[Content_Types].xml":
                payload = patch_content_types(source.read(name))
            elif name == "word/media/rId40.png":
                payload = fallback_png.read_bytes()
            else:
                payload = source.read(name)
            target.writestr(item, payload)

        target.writestr(SVG_PACKAGE_PATH, svg_path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--fallback-png", type=Path, required=True)
    args = parser.parse_args()
    build(args.input, args.output, args.svg, args.fallback_png)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
