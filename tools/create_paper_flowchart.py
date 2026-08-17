from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "03_排版与审校" / "论文图表素材" / "论文插图" / "图01_系统流程图.png"


def font(size: int):
    for path in (
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\msyh.ttc"),
    ):
        if path.exists():
            return ImageFont.truetype(str(path), size=size, index=0)
    return ImageFont.load_default()


def centered(draw: ImageDraw.ImageDraw, box, text: str, fnt, fill="black") -> None:
    left, top, right, bottom = box
    bbox = draw.multiline_textbbox((0, 0), text, font=fnt, align="center", spacing=5)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    draw.multiline_text(
        ((left + right - width) / 2, (top + bottom - height) / 2),
        text,
        font=fnt,
        fill=fill,
        align="center",
        spacing=5,
    )


def arrow(draw: ImageDraw.ImageDraw, start, end, width=3) -> None:
    draw.line((*start, *end), fill="black", width=width)
    if end[0] != start[0]:
        direction = 1 if end[0] > start[0] else -1
        draw.polygon(
            [
                end,
                (end[0] - direction * 18, end[1] - 10),
                (end[0] - direction * 18, end[1] + 10),
            ],
            fill="black",
        )
    else:
        direction = 1 if end[1] > start[1] else -1
        draw.polygon(
            [
                end,
                (end[0] - 10, end[1] - direction * 18),
                (end[0] + 10, end[1] - direction * 18),
            ],
            fill="black",
        )


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1800, 900), "white")
    draw = ImageDraw.Draw(image)
    title_font = font(38)
    box_font = font(25)
    detail_font = font(20)

    centered(draw, (40, 24, 1760, 76), "游标卡尺自动读数识别系统流程", title_font)

    boxes = [
        ("输入图像", "固定相机采集"),
        ("ROI 定位", "裁剪有效结构"),
        ("预处理", "增强、二值化"),
        ("区域分离", "主尺 / 游标尺"),
        ("主尺识别", "刻线检测 + OCR"),
        ("游标识别", "谷底、连通域、零线"),
        ("读数融合", "整数 + 0.02 mm 小数"),
        ("输出结果", "读数、置信度、可视化"),
    ]
    positions = []
    bw, bh = 300, 135
    xs = [70, 470, 870, 1270]
    ys = [150, 475]
    for row, y in enumerate(ys):
        for col, x in enumerate(xs):
            idx = row * 4 + col
            name, detail = boxes[idx]
            draw.rectangle((x, y, x + bw, y + bh), outline="black", fill="white", width=3)
            centered(draw, (x + 8, y + 18, x + bw - 8, y + 70), name, box_font)
            centered(draw, (x + 8, y + 75, x + bw - 8, y + bh - 15), detail, detail_font)
            positions.append((x, y))

    for col in range(3):
        x, y = positions[col]
        arrow(draw, (x + bw, y + bh / 2), (positions[col + 1][0], y + bh / 2))
    # The second row continues from the split stage into the two readers.
    # Route the connector around the left edge so the reading order remains
    # left-to-right on the second row.
    split_x = positions[3][0] + bw / 2
    main_x, main_y = positions[4]
    route_y = main_y + bh / 2
    draw.line((split_x, positions[3][1] + bh, split_x, route_y), fill="black", width=3)
    draw.line((split_x, route_y, main_x + bw, route_y), fill="black", width=3)
    draw.polygon(
        [(main_x + bw, route_y), (main_x + bw + 18, route_y - 10), (main_x + bw + 18, route_y + 10)],
        fill="black",
    )
    for col in range(3):
        x, y = positions[4 + col]
        arrow(draw, (x + bw, y + bh / 2), (positions[4 + col + 1][0], y + bh / 2))

    image.save(OUT, format="PNG", optimize=True)
    # Keep the copy used by the Markdown builder in sync.
    mirror = ROOT / "paper" / "03_排版与审校" / "论文图表素材" / "图01_系统流程图.png"
    image.save(mirror, format="PNG", optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
