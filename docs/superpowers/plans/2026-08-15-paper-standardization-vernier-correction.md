# 标准化刻度线与游标逐线校正论文补充实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不补写具体异常案例的前提下，将主尺/游标尺标准化刻度线实现和游标尺逐线方向校正写成与当前代码一致的算法级论文内容。

**Architecture:** 以 `paper/01_正文与草稿/游标卡尺识别论文主体.md` 为唯一正文源稿，在游标候选筛选之后增加“刻线位置精细定位”小节，并把标准化表示、逐线方向校正、长度聚类明确为详细模式的诊断/可视化路径。通过既有插图构建脚本生成带图 Markdown，再用既有模板校准脚本生成双栏 Word，并转换 PDF 做 XML、页数、公式和图题检查。

**Tech Stack:** UTF-8 Markdown、Python、Pandoc、LibreOffice、PDF 渲染工具、pytest。

**Spec:** `paper/01_正文与草稿/游标卡尺识别论文主体.md` 与当前 `caliper/vernier_scale.py`、`caliper/utils.py` 的已核实字段和调用链。

## Global Constraints

- 不补写或扩写 `140.00` 等具体错误案例；实验章节保留总体统计和已有必要的错误类型概述。
- 不把标准化曲线、逐线校正带、连续补绘带或长度聚类结果写成正式读数输入。
- 不声称强制拟合 51 条游标刻线；正式候选数量由图像证据决定。
- 论文必须区分 `x_projection`、`x_refined`、`x_precise` 和正式显示坐标 `x`。
- 正式游标对齐使用亚像素坐标比较误差，最终小数读数仍按 0.02 mm 离散分度输出。
- 保留原有双栏模板、公式编号、图题字体和作者/单位待补信息。

---

### Task 1: 补充游标刻线位置精细定位小节

**Files:**
- Modify: `paper/01_正文与草稿/游标卡尺识别论文主体.md`
- Test: `tests/test_paper_algorithm_consistency_audit.py`

**Interfaces:**
- Consumes: 当前游标投影候选、连通域关联、逐行二值中心和 `refine_tick_x_subpixel` 的实际流程。
- Produces: 论文中独立说明初始候选、几何精化、亚像素精化、字段含义、零线映射和正式对齐输入。

- [ ] **Step 1: 在游标连通域筛选后插入“游标刻线位置精细定位”小节。**
- [ ] **Step 2: 用代码字段逐项说明 `x_projection`、`x_refined`、`x_precise` 和 `x`，避免把投影峰误写成最终位置。**
- [ ] **Step 3: 说明零刻度线由第一条投影候选映射到正式刻线，正式对齐优先使用 `x_precise`。**
- [ ] **Step 4: 删除或改写任何把诊断曲线当作正式位置检测的表述。**

### Task 2: 收束标准化刻度线与逐线校正表述

**Files:**
- Modify: `paper/01_正文与草稿/游标卡尺识别论文主体.md`

**Interfaces:**
- Consumes: 已有主尺标准化曲线、游标标准化曲线、逐线方向校正和长度聚类段落。
- Produces: 明确标准化刻度线的输入、归一化响应、长短刻线聚类、逐线偏移校正与正式识别路径的边界。

- [ ] **Step 1: 保留主尺标准化响应的实际支撑长度和显示幅值定义。**
- [ ] **Step 2: 保留游标每条刻线独立计算偏移量的校正公式，不假设所有刻线共用方向。**
- [ ] **Step 3: 明确连续补绘仅用于显示，不能产生正式候选或改变零线、对齐和读数。**
- [ ] **Step 4: 保留长度一维聚类的样本数、百分位截断、中心迭代和两簇显示门槛。**

### Task 3: 重新生成并校准论文产物

**Files:**
- Modify: `paper/01_正文与草稿/游标卡尺识别论文主体_带插图.md`
- Create/Modify: `paper/02_Word版本/基于机器视觉的游标卡尺自动读数识别系统设计2_标准化与逐线校正版.docx`
- Create: `paper/03_排版与审校/paper_render_audit/standardization_correction_final/*.pdf/png`

**Interfaces:**
- Consumes: 修改后的源稿、既有论文图表素材、参考格式 Word。
- Produces: 带插图源稿、双栏 Word、PDF 页面图和审校报告。

- [ ] **Step 1: 运行 `python tools/build_paper_with_figures.py`。**
- [ ] **Step 2: 按既有模板命令将带插图 Markdown 转为 DOCX，再运行 `python tools/calibrate_paper_docx.py --input ... --output ...`。**
- [ ] **Step 3: 使用 LibreOffice 转 PDF，并用 `pdftoppm` 生成页面图。**
- [ ] **Step 4: 检查正文双栏、图题、公式编号、表格和章节编号。**

### Task 4: 一致性与回归检查

**Files:**
- Modify: `paper/04_审计报告/论文最终排版检查报告.md`（如报告路径指向旧版本）
- Test: `tests/test_paper_algorithm_consistency_audit.py tests/test_reference_format_contract.py tests/test_calibrate_paper_docx.py`

- [ ] **Step 1: 运行论文算法一致性审计，确认新增字段与代码符号可追溯。**
- [ ] **Step 2: 运行 Word 模板、引用格式和排版契约测试。**
- [ ] **Step 3: 检查 PDF 页数及页面渲染，确认没有公式截断、图题覆盖或栏间溢出。**
- [ ] **Step 4: 汇报改动范围，明确未加入具体 `140.00` 案例。**

---

## Self-review

- 计划覆盖了用户要求的标准化刻度线实现和游标尺刻线校正。
- 计划明确排除具体错误案例补写，并保留诊断路径与正式读数路径的边界。
- 计划包含源稿、插图稿、Word、PDF 和自动检查，且未安排任何识别代码修改。
