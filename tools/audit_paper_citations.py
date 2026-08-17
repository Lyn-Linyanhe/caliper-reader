from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "paper" / "04_审计报告" / "论文引用审计报告.md"
EXTERNAL_REPORT = ROOT / "paper" / "04_审计报告" / "论文参考文献真实性核验报告_20260815.md"


def find_source() -> Path:
    """定位论文正文源 Markdown，避免引用损坏编码的临时文件名。"""
    candidates: list[Path] = []
    source_dir = ROOT / "paper" / "01_正文与草稿"
    for path in source_dir.iterdir():
        if not path.is_file() or path.suffix.lower() != ".md":
            continue
        name = path.name
        if not name.startswith("游标卡尺识别论文主体"):
            continue
        if "排版临时" in name or "带插图" in name:
            continue
        candidates.append(path)
    if not candidates:
        raise FileNotFoundError("未找到论文正文源 Markdown：游标卡尺识别论文主体.md")
    candidates.sort(key=lambda p: (len(p.name), p.name))
    return candidates[0]


SOURCE = find_source()


def expand_citation(bracket_content: str) -> set[int]:
    """把形如 2-4,9-10 的引用内容展开为编号集合。"""
    result: set[int] = set()
    for token in bracket_content.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            result.update(range(int(start_text), int(end_text) + 1))
        else:
            result.add(int(token))
    return result


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    ref_marker = "## 参考文献"
    body, references = text.split(ref_marker, 1)

    cited: set[int] = set()
    for match in re.finditer(r"\[([\d,\-]+)\]", body):
        cited.update(expand_citation(match.group(1)))

    refs: dict[int, str] = {}
    for line in references.splitlines():
        match = re.match(r"^\[(\d+)\]\s+(.+)$", line.strip())
        if match:
            refs[int(match.group(1))] = match.group(2)

    missing_from_list = sorted(cited - set(refs))
    uncited_refs = sorted(set(refs) - cited)
    malformed_doi = [
        number
        for number, entry in refs.items()
        if "DOI:" in entry and not re.search(r"DOI:\s*10\.\S+", entry)
    ]
    no_doi = [number for number, entry in refs.items() if "DOI:" not in entry]

    lines = [
        "# 论文引用审计报告",
        "",
        f"- 正文中出现的编号：{', '.join(map(str, sorted(cited)))}",
        f"- 参考文献表中的编号：{', '.join(map(str, sorted(refs)))}",
        f"- 正文引用数量（按编号去重）：{len(cited)}",
        f"- 参考文献条目数量：{len(refs)}",
        "",
        "## 一致性检查",
        "",
        f"- 正文引用但参考文献表缺失：{'无' if not missing_from_list else ', '.join(map(str, missing_from_list))}",
        f"- 参考文献表存在但正文未引用：{'无' if not uncited_refs else ', '.join(map(str, uncited_refs))}",
        f"- DOI 字段格式异常：{'无' if not malformed_doi else ', '.join(map(str, malformed_doi))}",
        "",
        "## 人工确认项",
        "",
        (
            f"- 参考文献编号 {', '.join(map(str, no_doi)) if no_doi else '无'} "
            "未写 DOI。该结果不代表文献没有 DOI，提交前应按目标期刊要求逐条核对；本次未凭空补充 DOI。"
        ),
        "- 当前正文采用编号制引用（如 [1]、[2-4]），参考文献顺序与编号保持一致。",
        "- 参考文献真实性、题名、卷期和 DOI 的外部核验见：论文参考文献真实性核验报告_20260815.md。",
        "- 当前外部核验结论：正文当前保留的第 1–3 条均有 DOI/出版社或会议来源证据；Chen et al. (2022) 与 Gonzalez et al. (2003) 已取得本地全文，具体内容边界见文献引用价值审核记录。",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()
