# 参考论文格式校准 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将游标卡尺论文 DOCX 的前置部分、正文段落、图题和表格格式按用户提供的参考论文实际 XML 属性校准，而不是仅依赖 Pandoc 样式名。

**Architecture:** 保留现有 Markdown→Pandoc→reference-doc 生成链路，用一个独立的 DOCX XML 后处理器复制参考文档的页面属性和关键段落直接格式。后处理器只修改论文输出文件，不修改原始参考文档；校准结果通过 XML 回归检查验证。

**Tech Stack:** Python 3.12、zipfile、xml.etree.ElementTree、Pandoc DOCX、用户参考 DOCX。

## Global Constraints

- 参考页面尺寸必须保持 `11908 × 16216` twips。
- 参考页边距必须保持上 `875`、右 `920`、下 `1059`、左 `907` twips。
- 不得保留参考论文中的作者、基金、期刊页眉、页脚和样例图片。
- 不得凭空修改论文实验数据和参考文献内容。
- 图题必须在 Word 中可见，不能只写入图片 `docPr@descr`。
- 作者、单位、基金等尚未提供的信息继续保留“待补”。
- 正文必须采用参考模板的“前置区单栏、主体双栏、参考文献分节”结构。
- 系统流程图必须采用黑白细框、黑色箭头和黑色文字，不使用蓝色填充或装饰性配色。
- 表格必须按参考模板校准表题、表头、边框、列宽、单元格内边距和表内字体，不接受 Pandoc 默认表格样式。

---

### Task 1: 建立参考格式属性基线

**Files:**
- Create: `tools/extract_reference_format.py`
- Create: `tests/test_reference_format_contract.py`
- Read: `E:/朱/论文编号为 9952644的论文正文脱敏版本.docx`

**Interfaces:**
- `extract_reference_format(reference_docx: Path) -> dict`
- 输出页面属性、标题/作者/摘要/正文/图题/表格的可复核 XML 属性。

- [ ] **Step 1: Write the failing test**

```python
def test_reference_page_contract():
    contract = extract_reference_format(reference_docx)
    assert contract["page"]["width"] == "11908"
    assert contract["page"]["height"] == "16216"
    assert contract["page"]["margins"]["top"] == "875"
    assert contract["title"]["font_size_half_points"] == "44"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_reference_format_contract.py -q
```

Expected: FAIL because `extract_reference_format` does not yet exist.

- [ ] **Step 3: Implement the minimal extractor**

读取 `word/document.xml`，按正文中第一个标题、作者、摘要、关键词、正文段落及图题段落提取 `w:pPr`、首个运行的 `w:rPr` 和 `word/document.xml` 的 `w:sectPr`。

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
pytest tests/test_reference_format_contract.py -q
```

Expected: PASS.

### Task 2: 校准论文前置部分

**Files:**
- Create: `tools/calibrate_paper_docx.py`
- Modify: `tools/clean_reference_headers.py`
- Test: `tests/test_calibrate_paper_docx.py`

**Interfaces:**
- `calibrate_docx(input_docx: Path, reference_docx: Path, output_docx: Path) -> None`
- 输入为 Pandoc 生成的含插图 DOCX，输出为清除样例元数据并完成格式校准的 DOCX。

- [ ] **Step 1: Write the failing test**

检查最终文档前 12 个正文段落：

```python
assert title_run_fonts["eastAsia"] == "宋体"
assert title_run_size == "44"
assert title_paragraph_jc == "center"
assert author_run_fonts["eastAsia"] == "仿宋"
assert author_run_size == "21"
assert visible_caption_count == figure_count
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_calibrate_paper_docx.py -q
```

Expected: FAIL because the current title uses `FirstParagraph` inheritance and lacks the reference title's direct formatting.

- [ ] **Step 3: Implement direct-format copying**

在 `calibrate_paper_docx.py` 中：

1. 从参考文档复制 `sectPr` 页面尺寸、页边距和栏设置。
2. 对中文题名设置居中、宋体、44 half-points、line=240。
3. 对中文作者/单位设置居中、仿宋、21 half-points、line=240。
4. 将中文摘要和英文摘要标签与正文改为参考论文的可见段落结构，并设置 21 half-points、line=240。
5. 对正文标题设置黑体、21 half-points、line=255、after=145。
6. 对正文段落设置与参考论文一致的首行缩进和 line spacing。
7. 不修改正文文字内容和实验数据。

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
pytest tests/test_calibrate_paper_docx.py -q
```

Expected: PASS.

### Task 3: 校准图题、表格和样例元数据清理

**Files:**
- Modify: `tools/clean_reference_headers.py`
- Modify: `tools/check_final_paper.py`
- Test: `tests/test_calibrate_paper_docx.py`

- [ ] **Step 1: Write the failing checks**

```python
assert no_reference_sample_author_text
assert all_caption_paragraphs_use_image_caption_style
assert all_tables_have_table_grid_style
assert no_emf_media_files
```

- [ ] **Step 2: Implement**

1. 保留每张图唯一一个 `ImageCaption` 可见图题。
2. 清除模板样例页眉、页脚和 EMF 关系。
3. 从参考 DOCX 读取表题段落、`tblBorders`、`tblGrid`、`tcMar` 和表内运行属性。
4. 将论文表格的边框、列宽、单元格内边距、表头字体和表内字号按参考属性写入。
5. 更新检查报告，记录页面属性、图题数量、表格数量、表格列宽和样例文本扫描结果。

- [ ] **Step 3: Run checks**

```powershell
pytest tests/test_calibrate_paper_docx.py -q
python tools/check_final_paper.py
```

Expected: PASS; report states that 12 figures have visible captions and no sample metadata remains.

### Task 4: 重新生成最终交付文件

**Files:**
- Modify: `游标卡尺识别论文主体_带插图.md`
- Create: `游标卡尺识别论文主体_参考格式_含插图.docx`
- Create: `游标卡尺识别论文主体_最终排版.docx`
- Create: `论文最终排版检查报告.md`

- [ ] **Step 1: Generate source and DOCX**

```powershell
python tools/build_paper_with_figures.py
pandoc 游标卡尺识别论文主体_带插图.md --from markdown+tex_math_single_backslash --to docx `
  --reference-doc="E:\朱\论文编号为 9952644的论文正文脱敏版本.docx" `
  -o 游标卡尺识别论文主体_参考格式_含插图.docx --resource-path=.
```

- [ ] **Step 2: Apply calibration and cleanup**

```powershell
python tools/calibrate_paper_docx.py
python tools/clean_reference_headers.py
python tools/check_final_paper.py
```

- [ ] **Step 3: Run final XML regression**

```powershell
pytest tests/test_reference_format_contract.py tests/test_calibrate_paper_docx.py -q
```

Expected: PASS, with page size/margins matching the reference and visible captions equal to figure count.

### Task 5: 重绘黑白系统流程图

**Files:**
- Modify: `tools/create_paper_flowchart.py`
- Modify: `论文图表素材/论文插图/图01_系统流程图.png`

- [ ] **Step 1:** 将流程框填充改为白色，边框、箭头和文字改为黑色，去掉蓝色和灰色装饰。
- [ ] **Step 2:** 保留“输入图像→ROI 定位→预处理→区域分离→主尺识别→游标识别→读数融合→输出结果”的主链路。
- [ ] **Step 3:** 将中间结果可视化说明改成黑色细框中的简短黑色文字。
- [ ] **Step 4:** 查看 PNG，确认文字不越出框线且适合双栏宽度。

### Task 6: 提交前人工检查说明

**Files:**
- Modify: `论文最终排版检查报告.md`

- [ ] **Step 1:** 明确记录本机未安装 LibreOffice/Word，无法自动生成 PDF 页面截图。
- [ ] **Step 2:** 列出用户打开 DOCX 后需要人工确认的项目：标题居中、作者单位换行、摘要分页、表格跨页、图题可见性和图像清晰度。
- [ ] **Step 3:** 不宣称“与模板完全一致”，除非 XML 属性和人工视觉检查均通过。
