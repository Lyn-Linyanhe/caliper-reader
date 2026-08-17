from pathlib import Path
import zipfile

from tools.extract_reference_format import extract_reference_format


def _reference_docx() -> Path:
    matches = [
        path
        for path in Path(r"E:/朱").glob("*9952644*.docx")
        if zipfile.is_zipfile(path)
    ]
    assert matches, "reference paper DOCX not found"
    return matches[0]


def test_reference_page_contract():
    contract = extract_reference_format(_reference_docx())
    page = contract["page"]["pgSz"]
    margins = contract["page"]["pgMar"]
    assert page["w"] == "11908"
    assert page["h"] == "16216"
    assert margins["top"] == "875"
    assert margins["right"] == "920"
    assert margins["bottom"] == "1059"
    assert margins["left"] == "907"


def test_reference_title_and_body_contract():
    contract = extract_reference_format(_reference_docx())
    title = contract["title"]
    assert title["paragraph"]["jc"] == "center"
    assert title["run"]["fonts"]["eastAsia"] == "宋体"
    assert title["run"]["sz"]["val"] == "44"
    assert title["paragraph"]["spacing"]["line"] == "240"

    body_heading = contract["body_heading"]
    assert body_heading["run"]["fonts"]["eastAsia"] == "黑体"
    assert body_heading["run"]["sz"]["val"] == "21"
    assert body_heading["paragraph"]["spacing"]["line"] == "255"


def test_reference_caption_and_table_contract():
    contract = extract_reference_format(_reference_docx())
    assert contract["caption"]["run"]["fonts"]["eastAsia"] == "楷体"
    assert contract["caption"]["run"]["sz"]["val"] == "18"
    assert contract["table_caption"]["run"]["fonts"]["eastAsia"] == "黑体"
    assert contract["table_count"] > 0


def test_reference_has_double_column_body_section():
    contract = extract_reference_format(_reference_docx())
    columns = [
        section.get("cols", {}).get("num")
        for section in contract["sections"]
        if "cols" in section
    ]
    assert "2" in columns
