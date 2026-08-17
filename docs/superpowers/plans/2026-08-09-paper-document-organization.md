# 论文文档整理 Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with review checkpoints.

**Goal:** 将项目根目录中的论文相关文档集中到 `paper/` 分类目录，并生成可检索的根目录索引，同时保持论文工具和测试可运行。

**Architecture:** 使用工作区内的 `Move-Item -LiteralPath` 完成可恢复的文件移动；论文工具通过集中路径常量指向新目录；根目录 `文档索引.md` 作为人工入口，记录用途、版本关系和推荐底稿。代码、数据、调试输出和开发规划文件不移动。

**Tech Stack:** PowerShell 文件操作、Python `pathlib`/`pytest`、Markdown、DOCX/ZIP 结构检查。

## Global Constraints

- 只整理论文相关文件；项目代码、数据集、调试图、实验脚本和 `docs/superpowers/` 记录保持原位。
- 不删除文件，不覆盖用户已有修改，不使用 Git 回退命令。
- 论文推荐底稿为 `paper/02_Word版本/基于机器视觉的游标卡尺自动读数识别系统设计2_算法一致性审校版.docx`。
- 移动后所有论文工具和论文测试必须使用新路径。

---

### Task 1: Create paper directories and move classified artifacts

**Files:**
- Create: `paper/01_正文与草稿/`
- Create: `paper/02_Word版本/`
- Create: `paper/03_排版与审校/`
- Create: `paper/04_审计报告/`
- Create: `paper/05_临时文档/`
- Move: files listed in `docs/superpowers/specs/2026-08-09-paper-document-organization-design.md`
- Move: `论文图表素材/` to `paper/03_排版与审校/论文图表素材/`

**Interfaces:**
- Produces the stable paths consumed by Tasks 2 and 3.

- [x] **Step 1: Verify every source path exists before moving.**

Run a PowerShell assertion over the exact file list from the design spec. Expected: no missing paths.

- [x] **Step 2: Create target directories.**

Use `New-Item -ItemType Directory -Force` for the five `paper/` directories.

- [x] **Step 3: Move files and `paper_render_audit/`.**

Use `Move-Item -LiteralPath` within the workspace. Do not move `docs/superpowers`, source code, datasets, or debug directories.

- [x] **Step 4: Verify no duplicate remains at the old paths.**

Expected: every moved source path is absent and every target path exists.

### Task 2: Update paper tooling and tests to use stable paths

**Files:**
- Modify: `tools/build_paper_with_figures.py`
- Modify: `tools/audit_paper_citations.py`
- Modify: `tools/calibrate_paper_docx.py`
- Modify: `tools/check_final_paper.py`
- Modify: `tests/test_calibrate_paper_docx.py`
- Modify: `tests/test_paper_algorithm_consistency_audit.py`

**Interfaces:**
- Existing script entry points remain unchanged.
- `tools.audit_paper_citations.find_source()` searches `paper/01_正文与草稿/`.
- Existing command-line defaults continue to work without extra arguments.

- [x] **Step 1: Replace root-level paper constants with `ROOT / "paper" / ...` paths.**

Keep algorithm behavior unchanged; only path constants and source-directory iteration change.

- [x] **Step 2: Update tests to locate moved DOCX fixtures.**

Use explicit `ROOT / "paper" / "02_Word版本" / filename` paths or a constrained glob within that directory.

- [x] **Step 3: Run focused paper tests.**

Run:

```powershell
python -m pytest tests\test_paper_algorithm_consistency_audit.py tests\test_reference_format_contract.py tests\test_calibrate_paper_docx.py -q
```

Expected: all existing paper tests pass.

### Task 3: Generate the document index

**Files:**
- Create: `文档索引.md`

**Interfaces:**
- Human-facing entry point from the repository root.
- Links use repository-relative paths and identify the recommended version.

- [x] **Step 1: Record the directory map and each paper artifact.**

Include purpose, status (`源稿`/`工作稿`/`推荐底稿`/`报告`/`临时`), and version relationship.

- [x] **Step 2: Record excluded project assets.**

State that code, `tupian/`, `debug_*`, `tools/`, `tests/`, and `docs/superpowers/` remain in place.

- [x] **Step 3: Check every index link.**

Expected: every linked file and directory exists.

### Task 4: End-to-end verification

**Files:**
- Verify: `paper/` and `文档索引.md`
- Verify: modified tooling and tests

- [x] **Step 1: Run all paper-related tests.**

```powershell
python -m pytest tests\test_paper_algorithm_consistency_audit.py tests\test_user_paper_algorithm_patch.py tests\test_reference_format_contract.py tests\test_calibrate_paper_docx.py -q
```

- [x] **Step 2: Validate DOCX ZIP readability.**

Open every moved `.docx` with Python `zipfile` and require `word/document.xml`.

- [x] **Step 3: Run a final path audit.**

Search `tools/` and `tests/` for old root-level paper paths. Expected: no executable path reference remains except historical text in documentation.
