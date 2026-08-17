from pathlib import Path
import re

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MD = ROOT / "paper" / "01_正文与草稿" / "游标卡尺识别论文主体.md"
FIG_DIR = ROOT / "paper" / "03_排版与审校" / "论文图表素材"
OUT_FIG_DIR = FIG_DIR / "论文插图"
OUT_MD = ROOT / "paper" / "01_正文与草稿" / "游标卡尺识别论文主体_带插图.md"


FIGURES = {
    1: ("图01_系统流程图.png", "240pt"),
    2: ("图02_ROI定位_30.00.png", "240pt"),
    3: ("图03_预处理_30.00.png", "240pt"),
    4: ("图04_区域分离_30.00.png", "240pt"),
    5: ("图05_主尺刻线_30.00.png", "240pt"),
    6: ("图06_OCR候选_30.00.png", "240pt"),
    7: ("图07_游标刻线_30.00.png", "240pt"),
    8: ("图08_游标连通域与长度聚类_30.00.png", "240pt"),
    9: ("图09_游标对齐_30.00.png", "240pt"),
    10: ("图10_正确样本最终标注_30.00.png", "240pt"),
    11: ("图11e_OCR失败最终_130.70.png", "240pt"),
    12: ("图11f_游标对齐偏差_75.58.png", "240pt"),
}


def resize_figures() -> None:
    OUT_FIG_DIR.mkdir(parents=True, exist_ok=True)
    for filename, _ in FIGURES.values():
        src = FIG_DIR / filename
        dst = OUT_FIG_DIR / filename
        if not src.exists():
            raise FileNotFoundError(src)
        with Image.open(src) as image:
            image = image.convert("RGB")
            if image.width > 1800:
                height = round(image.height * 1800 / image.width)
                image = image.resize((1800, height), Image.Resampling.LANCZOS)
            image.save(dst, format="JPEG", quality=90, optimize=True)


def build_markdown() -> None:
    text = SOURCE_MD.read_text(encoding="utf-8")
    pattern = re.compile(r"^图\s+(\d+)\s+(.+?)\s*$", re.MULTILINE)

    def replace(match: re.Match[str]) -> str:
        number = int(match.group(1))
        caption = f"图 {number} {match.group(2).strip()}"
        item = FIGURES.get(number)
        if item is None:
            return caption
        filename, width = item
        rel = f"论文图表素材/论文插图/{filename}"
        return f"![{caption}]({rel}){{width={width}}}\n\n{caption}\n"

    OUT_MD.write_text(pattern.sub(replace, text), encoding="utf-8")


if __name__ == "__main__":
    resize_figures()
    build_markdown()
    print(OUT_MD)
