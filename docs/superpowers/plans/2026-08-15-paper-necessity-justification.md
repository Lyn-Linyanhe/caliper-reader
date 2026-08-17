# 论文算法必要性说明补全实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在论文方法部分逐模块说明保留该步骤的必要性，并确保正文、Word、PDF 与审计结果一致。

**Architecture:** 以现有 Markdown 正文为唯一内容源，在区域分离、主尺检测与 OCR、游标检测与对齐、实验复核四组位置补充“问题—必要步骤—省略后果”的短段落。随后由现有构建脚本生成带图 Markdown 和 Word，再用 LibreOffice 渲染 PDF，最后运行引用与排版测试。

**Tech Stack:** Markdown, Python 构建脚本, LibreOffice, pytest, PowerShell。

**Spec:** `paper/01_正文与草稿/游标卡尺识别论文主体.md` 中现有方法章节及 `paper/04_审计报告/方法表述精简版审校报告_20260815.md`。

## Global Constraints

- 不新增未经代码或实验支持的算法、参数、准确率和引用。
- 标准化曲线、逐线校正和聚类仍明确为详细模式诊断功能，不改变正式读数路径。
- 不恢复已删除的表 2 具体参数堆列。
- 保持双栏 Word 模板、公式、图片和图题的既有排版规则。

### Task 1: 补全方法模块的必要性表述

**Files:**
- Modify: `paper/01_正文与草稿/游标卡尺识别论文主体.md`

- [x] 在区域分离、主尺刻线、主尺标准化、OCR、游标谷底、连通域、精细定位、逐线校正、对齐、歧义处理等小节补充简洁必要性段落。
- [x] 在实验错误归因和可视化小节说明保留中间证据的必要性。
- [x] 检查所有新增表述是否与当前实现边界一致。

### Task 2: 重建交付文档

**Files:**
- Modify: `paper/01_正文与草稿/游标卡尺识别论文主体_带插图.md`
- Modify: `paper/02_Word版本/游标卡尺识别论文主体_最终排版.docx`
- Create/refresh: `paper/03_排版与审校/paper_render_audit/...`

- [x] 运行 `python tools/build_paper_with_figures.py`。
- [x] 按现有构建/校准流程生成并校准 Word，保留公式、图题、双栏设置。
- [x] 用 LibreOffice 将 Word 转为 PDF。

### Task 3: 审计与回归检查

**Files:**
- Modify: `paper/04_审计报告/方法表述必要性审校报告_20260815.md`

- [x] 运行引用审计和论文排版测试。
- [x] 检查正文、Word、PDF 的章节、公式、图片数量与新增必要性表述一致。
- [x] 记录模板遗留的 EMF/PNG 警告，不将其误报为本次修改造成的错误。
