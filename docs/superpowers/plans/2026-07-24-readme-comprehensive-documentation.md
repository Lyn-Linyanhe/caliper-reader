# README Comprehensive Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `README.md` a complete, code-accurate guide to the caliper-reading pipeline, its output contract, diagnostics, operation, and limits.

**Architecture:** Preserve the existing single-document README format while organizing it from user-facing operation to implementation detail. Every algorithm description must be traceable to the current modules, and every statement about a fallback must say when it is used and what it does not do.

**Tech Stack:** Python 3.12+, OpenCV, NumPy, Tkinter, Tesseract/EasyOCR, pytest.

## Global Constraints

- Do not change production recognition logic, test logic, image assets, or configuration.
- Do not state that file names participate in production recognition; they are test truth only.
- Do not claim that missing ticks are synthesized or that 51 ticks are forcibly fitted.
- State that formal vernier readings use only the `0.02 mm` grid and that ambiguity references never replace the formal result.
- Retain the existing Chinese-language README and PowerShell examples.

---

### Task 1: Audit the documentation contract against the implementation

**Files:**
- Modify: `README.md`
- Reference: `caliper/pipeline.py`, `caliper/roi_extract.py`, `caliper/region_split.py`, `caliper/main_scale.py`, `caliper/vernier_scale.py`, `caliper/merger.py`, `caliper/result.py`, `main.py`
- Test: `tests/test_alignment_ambiguity.py`, `tests/test_vernier_debug_panel.py`

**Interfaces:**
- Consumes: `CaliperPipeline.run(image, progress_callback=None) -> CaliperResult`.
- Produces: README sections that name stable result fields and debug keys without promising internal helper behaviour as a public API.

- [x] **Step 1: List user-visible pipeline stages and outputs**

Document these stages in order: ROI, preprocessing, orientation correction, region split, main-scale ticks, vernier valleys/ticks/zero line, main OCR, merge, diagnostics. List `CaliperResult.main_scale`, `vernier_scale`, `total`, `precision`, `confidence`, `image_annotated`, `debug_images`, and `extra_info` with units and diagnostic status.

- [x] **Step 2: Audit non-negotiable recognition constraints**

Document that the first verified observed tick inside the selected vernier valley span is zero, final vernier value is `best_index * 0.02`, parabolic interpolation is diagnostic-only, and an ambiguity reference is limited to an observed adjacent tick.

- [x] **Step 3: Audit failure semantics**

Document `total == 0.0` as a failed reading that must be inspected with the diagnostic reason, not a valid zero measurement. Explain OCR fallback and local ROI recovery without describing either as a guaranteed repair.

### Task 2: Rewrite README as a complete operational and technical guide

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: audited pipeline behaviour from Task 1.
- Produces: a standalone Chinese README with install, GUI, API, workflow, output, debugging, testing, constraints, and known limitations sections.

- [x] **Step 1: Replace the overview and quick-start sections**

Add project scope, supported caliper precision, end-to-end processing diagram, dependency installation for `python`, and a separate note that Tesseract itself must be installed when using `pytesseract`.

- [x] **Step 2: Expand every recognition stage**

Give each stage its implementation module, inputs, observable evidence, selection/fallback rules, output fields, and failure implications. Include the OCR retry band and the `zero_x`-relative integer rule.

- [x] **Step 3: Add output and ambiguity contract**

Define the equations `main_scale`, `vernier_scale`, and `total`; distinguish formal output from `extra_info['alignment_ambiguity']`; include the meaning of `primary_total`, `reference_total`, and pixel error margin.

- [x] **Step 4: Add diagnostic, GUI, API, test, and limitation reference**

List quick-mode versus detailed-mode debug images, the vertically combined vernier page, progress callback signature, test commands, image-regression convention, current regression baseline, and unresolved failure classes.

### Task 3: Verify documentation accuracy and repository integrity

**Files:**
- Modify: `README.md`
- Test: `tests/test_alignment_ambiguity.py`, `tests/test_vernier_debug_panel.py`

**Interfaces:**
- Consumes: completed README.
- Produces: verified documentation that matches current source and does not alter executable behaviour.

- [x] **Step 1: Check README headings and required terminology**

Run `rg -n "离散|歧义|0.02|不补线|不强制拟合|快速模式|详细模式|alignment_ambiguity|0.0" README.md` and confirm every required constraint appears.

- [x] **Step 2: Run documentation-adjacent regression tests**

Run `python -m pytest -q tests/test_alignment_ambiguity.py tests/test_vernier_debug_panel.py`.
Expected: all tests pass; no source file other than `README.md` and this plan changes during the documentation task.

- [x] **Step 3: Review the diff**

Run `git diff --check -- README.md docs/superpowers/plans/2026-07-24-readme-comprehensive-documentation.md`.
Expected: no whitespace errors.
