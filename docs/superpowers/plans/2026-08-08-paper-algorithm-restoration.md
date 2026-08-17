# Paper Algorithm Restoration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在用户删减后的 Word 论文中补回必要的算法闭环，并保持所有用户已有的删改和版式。

**Architecture:** 以 `E:/朱/基于机器视觉的游标卡尺自动读数识别系统设计2.docx` 为只读输入，直接编辑其 `word/document.xml` 的正文段落，输出新的 DOCX。仅增加三处经代码核对的正文：区域分离、游标刻线长度聚类和对齐实现说明。

**Tech Stack:** Python 3、ZIP/XML、Pandoc、pytest。

## Global Constraints

- 不修改原用户 DOCX，不删除现有内容。
- 不补写或验证参考文献，不改引言的文献格式占位。
- 聚类只描述为调试可视化的确定性一维两类聚类，不夸大为读数决策依据。
- 只写入已由 `caliper/region_split.py` 与 `caliper/vernier_scale.py` 证实的算法行为。

---

### Task 1: 制作保持用户版式的算法补充版 DOCX

**Files:**
- Create: `基于机器视觉的游标卡尺自动读数识别系统设计2_算法补充版.docx`
- Create: `tools/patch_user_paper_algorithms.py`
- Test: `tests/test_user_paper_algorithm_patch.py`

**Interfaces:**
- Consumes: 用户编辑后的 DOCX 与三个准确的段落锚点。
- Produces: 保留原 DOCX 样式、图、表与分栏配置的补充版 DOCX。

- [ ] **Step 1: 写入修订前的失败检查**

```python
def test_user_paper_contains_required_algorithm_clarifications():
    text = extract_docx_text(OUTPUT_DOCX)
    assert '分割线定位采用“端点证据优先、投影谷底回退”' in text
    assert '长度聚类仅用于标准化可视化' in text
    assert '不以纵向重叠作为当前实现的硬过滤条件' in text
```

- [ ] **Step 2: 运行检查并确认原用户文档不含这些新增表述**

Run: `python -m pytest tests/test_user_paper_algorithm_patch.py -q`

Expected: FAIL because the output document has not been generated.

- [ ] **Step 3: 以 XML 克隆相邻正文格式并插入三个段落**

```python
insert_after('3.1 区域分离原理', region_split_paragraph)
insert_after('5.2 游标刻线候选与连通域筛选', cluster_paragraph)
replace_in_paragraph('且纵向范围存在重叠的主尺刻线', '并以亚像素坐标计算横向距离')
```

- [ ] **Step 4: 重新运行定向检查与 DOCX 格式检查**

Run: `python -m pytest tests/test_user_paper_algorithm_patch.py -q`

Expected: PASS; 插图、表格和分节计数与用户输入一致。
