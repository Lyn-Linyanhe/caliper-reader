# Vernier Failure Local ROI Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover a valley-bounded vernier range from the smallest locally expanded ROI only after compact-ROI vernier detection fails.

**Architecture:** `roi_extract.py` will derive bounded recovery crop candidates from the existing compact and body boxes. `pipeline.py` will run those candidates only after the specific vernier failure, accepting the first candidate that passes the existing vernier reliability contract.

**Tech Stack:** Python 3, OpenCV, NumPy, standard-library `unittest`.

## Global Constraints

- Preserve the original compact ROI path and result for every non-failing image.
- Trigger only for `no_reliable_valley_bounded_tick_range`.
- Candidate boxes remain within `body`; do not use the full body as a direct fallback.
- Do not use image filenames, expected tick counts, synthetic ticks, or theoretical grids.

---

### Task 1: Bounded Candidate Construction

**Files:**
- Modify: `caliper/roi_extract.py`
- Test: `tests/test_roi_candidate_selection.py`

- [ ] Write failing tests for candidate bounds, unique names, and ascending added area.
- [ ] Run `python -m unittest tests.test_roi_candidate_selection -v` and confirm the new assertions fail because the helper is absent.
- [ ] Implement a helper that accepts `(compact_box, body_box)`, preserves y bounds, and returns only one-third/two-thirds local left/right and one-third bilateral expansions within body bounds.
- [ ] Run the focused test module until it passes.

### Task 2: Pipeline-Scoped Recovery

**Files:**
- Modify: `caliper/pipeline.py`
- Test: `tests/test_roi_candidate_selection.py`

- [ ] Write failing integration tests showing a normal input does not retry and `22.00` gets a nonzero result through a recovery crop.
- [ ] Run the new tests and verify they fail before production edits.
- [ ] Refactor the existing post-ROI stages into a helper, then retry only the bounded candidate crops after the exact vernier failure. Accept only an error-free vernier result containing a zero line and the configured minimum tick count; retain attempt diagnostics.
- [ ] Run focused tests and the existing ROI tests.

### Task 3: Dataset Regression

**Files:**
- Test: `tests/test_roi_candidate_selection.py`

- [ ] Add data regression assertions for `22.00`, `30.00`, `33.00`, and `80.90`, plus normal controls `70.00`, `72.52`, and `120.60`.
- [ ] Run the focused suite.
- [ ] Run `python tools/evaluate_all_pipeline.py` and compare all 48 labelled images with the prior evaluation.
