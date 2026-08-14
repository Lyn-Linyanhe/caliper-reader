# Project Code Audit and Manual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a code-accurate Chinese maintenance manual for the caliper-reading project after tracing its real runtime path, public interfaces, diagnostics, tests, and known limitations.

**Architecture:** The audit starts from executable entry points and follows concrete calls into each `caliper` module. Static inspection is checked against a small set of real pipeline executions and existing regression tests. The resulting manual is a standalone Markdown document under `docs/`; it separates active production behavior from debug-only and historical code paths.

**Tech Stack:** Python 3, OpenCV, NumPy, Tkinter GUI, pytest, Markdown.

## Global Constraints

- Preserve all pre-existing uncommitted work; do not reset, checkout, clean, or overwrite unrelated files.
- Do not push to GitHub or create a repository-wide commit without explicit user confirmation.
- State only behavior verified from the current source or a recorded execution.
- Keep the existing `README.md` unchanged; place the new detailed manual in `docs/`.

---

### Task 1: Establish the audit baseline

**Files:**
- Inspect: `main.py`, `caliper/*.py`, `requirements.txt`, `tests/*.py`, `tools/*.py`
- Create: `docs/项目代码说明书.md`

**Interfaces:**
- Consumes: executable entry points and current source tree.
- Produces: an inventory of active modules, public APIs, configuration objects, diagnostics, tools, and test assets.

- [ ] **Step 1: Record repository state and source inventory**

Run:

```powershell
git status --short
rg --files caliper tests tools
```

Expected: a list of existing user changes is recorded but not modified.

- [ ] **Step 2: Read every active production module and identify imports/call edges**

Run:

```powershell
rg -n "^(class|def) |^from |^import " main.py caliper
```

Expected: every pipeline stage can be tied to a concrete module and function.

- [ ] **Step 3: Inspect the public entry point and result contract**

Read `caliper/pipeline.py`, `caliper/result.py`, and `caliper/__init__.py`.

Expected: the manual can document `read_caliper()` and `read_caliper_from_array()` input/output behavior.

### Task 2: Trace the image-recognition pipeline

**Files:**
- Inspect: `caliper/roi_extract.py`, `caliper/preprocess.py`, `caliper/region_split.py`, `caliper/main_scale.py`, `caliper/vernier_scale.py`, `caliper/ocr.py`, `caliper/template_ocr.py`, `caliper/merger.py`, `caliper/utils.py`
- Test: `tests/test_roi_candidate_selection.py`, `tests/test_region_split_endpoint_seam.py`, `tests/test_main_tick_extent_recovery.py`, `tests/test_vernier_valley_regressions.py`, `tests/test_alignment_ambiguity.py`

**Interfaces:**
- Consumes: the inventory from Task 1.
- Produces: exact stage-by-stage descriptions of inputs, outputs, scoring, fallback behavior, and failure modes.

- [ ] **Step 1: Trace ROI, preprocessing, orientation, and scale split**

Read the four upstream modules and record each transformation and fallback condition.

Expected: the manual distinguishes the low-resolution ROI search, preprocessing binary image, RANSAC seam orientation, and endpoint/projection split paths.

- [ ] **Step 2: Trace main-scale and OCR processing**

Read `main_scale.py`, `ocr.py`, and `template_ocr.py`.

Expected: the manual states how ticks, OCR boxes, candidate digit groups, and integer anchors are obtained.

- [ ] **Step 3: Trace vernier processing and final reading merge**

Read `vernier_scale.py`, `merger.py`, and their regression tests.

Expected: the manual separates zero-line detection, alignment selection, ambiguity diagnostics, and the final `0.02 mm` quantization rule.

- [ ] **Step 4: Run representative images through the real pipeline**

Run:

```powershell
python -c "from caliper.pipeline import read_caliper; import json; [print(p, read_caliper('tupian/'+p).reading) for p in ['40.00.jpg','72.52.jpg','120.60.jpg']]"
```

Expected: three concrete observations can be included as examples, without treating them as universal accuracy claims.

### Task 3: Audit configuration, GUI, diagnostics, data, and tests

**Files:**
- Inspect: `caliper/config.py`, `main.py`, `caliper/reading_display.py`, `tools/*.py`, `tests/*.py`, `tupian/`
- Test: `tests/test_config_summary.py`, `tests/test_vernier_debug_panel.py`, `tests/test_batch_evaluation_report.py`

**Interfaces:**
- Consumes: the real pipeline trace from Task 2.
- Produces: configuration applicability table, GUI workflow description, diagnostic-image catalogue, dataset convention, and reproducible validation commands.

- [ ] **Step 1: Compare declared configuration with actual reads**

Run:

```powershell
rg -n "config\.|getattr\(config" caliper main.py
```

Expected: configuration fields are marked as active, dynamically read, or legacy/unreferenced.

- [ ] **Step 2: Inspect GUI and diagnostic image production**

Read `main.py` and the `save_debug` branches of `caliper/pipeline.py`.

Expected: every documented debug folder/panel is tied to the code that generates it.

- [ ] **Step 3: Inspect tools, test conventions, and evaluation output**

Read tool headers, `tests/conftest.py`, and `debug_tupian_batch_evaluation_20260808_final/evaluation.json`.

Expected: the manual documents the input naming convention, existing evaluation baseline, and known environment-specific pytest issue.

### Task 4: Write and validate the manual

**Files:**
- Create: `docs/项目代码说明书.md`

**Interfaces:**
- Consumes: all verified findings from Tasks 1–3.
- Produces: a self-contained Chinese project manual for developers and maintainers.

- [ ] **Step 1: Draft the manual with traceable sections**

Include repository layout, startup/API usage, data contracts, complete call chain, algorithm detail by stage, configuration table, GUI/debug output guide, test/evaluation guide, known limitations, and maintenance rules.

- [ ] **Step 2: Validate facts against source and executable checks**

Run:

```powershell
python -m pytest tests/test_config_summary.py tests/test_roi_candidate_selection.py tests/test_region_split_endpoint_seam.py tests/test_main_tick_extent_recovery.py tests/test_vernier_valley_regressions.py tests/test_alignment_ambiguity.py -q
```

Expected: pass or clearly documented environment/data failures; no behavior is altered merely to make an unrelated existing assertion pass.

- [ ] **Step 3: Review the document for unsupported claims**

Run:

```powershell
rg -n "TODO|TBD|待补充|可能" docs/项目代码说明书.md
```

Expected: no placeholder language is used for verified implementation claims.

- [ ] **Step 4: Report deliverables without committing or pushing**

Expected: the user receives the exact document path, validation outcome, and important known limitations.
