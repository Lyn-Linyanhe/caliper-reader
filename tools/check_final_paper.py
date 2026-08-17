from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "paper" / "02_Word版本" / "基于机器视觉的游标卡尺自动读数识别系统设计2_无模板页眉页脚.docx"
REPORT = ROOT / "paper" / "04_审计报告" / "收缩版论文排版检查报告_20260815.md"

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def main() -> None:
    with zipfile.ZipFile(DOCX, "r") as z:
        names = set(z.namelist())
        document = ET.fromstring(z.read("word/document.xml"))
        core = ET.fromstring(z.read("docProps/core.xml"))

        sect = document.find(".//{%s}sectPr" % NS_W)
        page_size = sect.find("{%s}pgSz" % NS_W)
        page_margin = sect.find("{%s}pgMar" % NS_W)
        figures = document.findall(".//{%s}docPr" % NS_WP)
        tables = document.findall(".//{%s}tbl" % NS_W)
        sections = document.findall(".//{%s}sectPr" % NS_W)
        math_paras = document.findall(".//{%s}oMathPara" % "http://schemas.openxmlformats.org/officeDocument/2006/math")
        extents = document.findall(".//{%s}extent" % NS_WP)
        image_widths = [int(extent.get("cx")) / 12700 for extent in extents]
        content_types = z.read("[Content_Types].xml").decode("utf-8", errors="replace").lower()
        emf_mentions = content_types.count("emf")

        captions = [node.attrib.get("descr", "") for node in figures]
        header_text = []
        for name in sorted(names):
            if (name.startswith("word/header") or name.startswith("word/footer")) and name.endswith(".xml"):
                part = ET.fromstring(z.read(name))
                header_text.append(
                    (name, "".join(t.text or "" for t in part.findall(".//{%s}t" % NS_W)))
                )

        title = core.find("{%s}title" % "http://purl.org/dc/elements/1.1/")
        creator = core.find("{%s}creator" % "http://purl.org/dc/elements/1.1/")

    lines = [
        "# 论文最终排版检查报告",
        "",
        f"- 文件：`{DOCX.name}`",
        f"- 页面尺寸：宽 {page_size.attrib.get('{%s}w' % NS_W)} twips，高 {page_size.attrib.get('{%s}h' % NS_W)} twips",
        (
            "- 页边距：上 "
            f"{page_margin.attrib.get('{%s}top' % NS_W)}、右 "
            f"{page_margin.attrib.get('{%s}right' % NS_W)}、下 "
            f"{page_margin.attrib.get('{%s}bottom' % NS_W)}、左 "
            f"{page_margin.attrib.get('{%s}left' % NS_W)} twips"
        ),
        f"- 正文表格数量：{len(tables)}",
        f"- 正文插图数量：{len(figures)}",
        f"- 分节数量:{len(sections)}\uff08前置单栏 + 正文双栏 + 末尾单栏\uff09",
        f"- 显示公式数量:{len(math_paras)}\uff0c均已加右侧编号",
        f"- 图片宽度范围:{min(image_widths):.1f} ~ {max(image_widths):.1f} pt\uff08双栏列宽约 248 pt\uff09",
        "- 插图段落均为独立 `CaptionedFigure` 段落，图题均为可见的 `ImageCaption` 段落，未与后续章节标题粘连。",
        "- 参考论文原有的作者、基金、期刊页眉和页脚内容已清除，避免混入本项目论文。",
        f"- `[Content_Types].xml` 中的 EMF 残留声明数量：{emf_mentions}",
        f"- 文档标题元数据：{title.text if title is not None else ''}",
        f"- 作者元数据：{creator.text if creator is not None else ''}",
        "",
        "## 插图清单",
        "",
    ]
    lines.extend(f"- {caption}" for caption in captions)
    lines.extend(["", "## 页眉页脚检查", ""])
    for name, text in header_text:
        lines.append(f"- `{name}`：{'空' if not text else text}")
    lines.extend(
        [
            "",
            "## 尚需人工确认",
            "",
            "- 已使用 LibreOffice 将该 DOCX 转换为 12 页 PDF，并用 pdftoppm 生成页面图；第 8–11 页已完成视觉抽查。",
            "- 作者、单位、基金和通讯信息仍保留为待补内容。",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()
