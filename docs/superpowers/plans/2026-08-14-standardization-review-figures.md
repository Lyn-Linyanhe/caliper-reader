# Standardization Review Figures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export ten standalone audit PNGs showing rotated-ROI main/vernier scale crops and their display-only normalized standardization curves.

**Architecture:** Add a focused exporter that runs the existing detailed pipeline, maps each standardization curve back to the corresponding rotated ROI x-domain, and renders a two-panel OpenCV figure. The exporter consumes existing `step_results` and never changes recognition results or the paper assets.

**Tech Stack:** Python 3.12, NumPy, OpenCV, pytest.

## Global Constraints

- Use `CaliperPipeline(fast_mode=False)` so diagnostic standardization data exists.
- Use `orient.rotated_color` and split-region coordinates as the image source; never crop from the original image.
- Do not read filename values as algorithm input and do not alter formal reading, tick detection, alignment, or OCR.
- Do not force a theoretical tick count or fabricate a curve; render a labeled placeholder when standardization is absent.
- Keep existing merged debug exports and paper files unchanged.

---

### Task 1: Review-figure rendering helpers

**Files:**
- Create: `tools/export_standardization_review_figures.py`
- Test: `tests/test_standardization_review_figures.py`

**Interfaces:**
- `render_review_figure(rotated_color, split_result, scale_name, scale_result, filename) -> tuple[np.ndarray, dict]`
- `export_review_figures(input_dir: Path, output_dir: Path, filenames: list[str]) -> dict`

- [ ] **Step 1: Write focused tests** for curve-domain crop mapping, zero-line marker metadata, and a missing-standardization placeholder.
- [ ] **Step 2: Run the focused tests** and verify the new helper is initially unavailable.
- [ ] **Step 3: Implement OpenCV rendering** with a shared x-axis content rectangle, rotated-ROI crop, normalized-response curve, accepted tick markers, vernier zero marker, and placeholder text for missing data.
- [ ] **Step 4: Implement the batch exporter** with the five agreed sample names, PNG writing, and JSON summary containing source/crop metadata.
- [ ] **Step 5: Run focused tests** and verify all pass.

### Task 2: Generate and inspect the ten audit figures

**Files:**
- Create: `debug_tupian_standardization_review_20260814/`

- [ ] **Step 1: Run the exporter** for `30.00.jpg`, `72.52.jpg`, `90.14.jpg`, `120.60.jpg`, and `140.00.jpg`.
- [ ] **Step 2: Verify exactly five `_main_review.png` and five `_vernier_review.png` files plus the summary JSON exist.
- [ ] **Step 3: Inspect representative PNGs** for rotated-ROI provenance, correct main/vernier crop, aligned curve peaks, no clipping, and a separately visible vernier zero line.
- [ ] **Step 4: Report the output directory and any sample whose standardization is empty; do not add images to the paper.
