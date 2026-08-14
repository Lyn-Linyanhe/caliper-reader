# Reading-Window ROI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select the smallest evidence-preserving ROI and recover a verified OCR integer right of the zero line as `N - 1`.

**Architecture:** Retain the broad projection and body-refined ROI candidates. A compact candidate is used only after actual scale and body evidence remains present. Extract OCR label selection into a helper so normal left-side selection and the guarded right-side fallback are independently testable.

**Tech Stack:** Python 3, OpenCV, NumPy, standard-library `unittest`.

## Global Constraints

- Do not use the screw-template matcher in the main ROI path.
- Do not use a fixed 51-tick expectation or synthesize ticks.
- Use measured scale bands, observed body geometry, valley-bounded vernier evidence, and OCR-to-tick bindings only.
- Run tests with `python -m unittest`; `pytest` is unavailable.

---

### Task 1: Guarded OCR Integer Fallback

**Files:**
- Modify: `caliper/merger.py:168-321`
- Modify: `tests/test_main_ocr_grouping.py`

**Interfaces:**
- Produces `_select_main_label_for_zero(ocr_candidates, zero_x, main_gap) -> tuple[dict | None, str | None]`.
- The strategy string is `left_of_zero`, `right_of_zero_minus_one`, or `None`.

- [ ] **Step 1: Write failing tests**

Add a `label(value, ref_tick_x)` fixture returning a dict with `value`, `ref_tick_x`, `confidence=0.9`, and `cc_confidence=0.9`. Add these assertions:

    selected, strategy = _select_main_label_for_zero([label(8, 108.0)], 98.0, 12.0)
    self.assertEqual((selected['value'], strategy), (7, 'right_of_zero_minus_one'))

    selected, strategy = _select_main_label_for_zero([label(8, 125.0)], 98.0, 12.0)
    self.assertEqual((selected, strategy), (None, None))

    selected, strategy = _select_main_label_for_zero([label(7, 84.0), label(8, 108.0)], 98.0, 12.0)
    self.assertEqual((selected['value'], strategy), (7, 'left_of_zero'))

- [ ] **Step 2: Verify failure**

Run: `python -m unittest tests.test_main_ocr_grouping -v`

Expected: import failure for `_select_main_label_for_zero`.

- [ ] **Step 3: Implement helper and integrate it**

Implement this exact selection behavior:

    side_tol = max(4.0, float(main_gap) * 0.20)
    left = [c for c in ocr_candidates if float(c['ref_tick_x']) <= float(zero_x) + side_tol]
    if left:
        return max(left, key=lambda c: (c['ref_tick_x'], c['confidence'], c['cc_confidence'])), 'left_of_zero'
    right = [c for c in ocr_candidates
             if 0.0 < float(c['ref_tick_x']) - float(zero_x) <= float(main_gap) + side_tol
             and int(c['value']) > 0]
    if not right:
        return None, None
    source = min(right, key=lambda c: (c['ref_tick_x'], -c['confidence'], -c['cc_confidence']))
    selected = dict(source)
    selected['value'] = int(source['value']) - 1
    selected['text'] = str(selected['value'])
    return selected, 'right_of_zero_minus_one'

Replace the inline choice at `caliper/merger.py:293-302`. Preserve the original bound tick as `ref_x`, preserve `extra_ticks`, and expose `ocr_label_selection` in returned debug data.

- [ ] **Step 4: Verify passing tests**

Run: `python -m unittest tests.test_main_ocr_grouping -v`

Expected: all grouping and new fallback tests pass.

- [ ] **Step 5: Commit**

Run: `git add caliper/merger.py tests/test_main_ocr_grouping.py`
Run: `git commit -m "fix: recover OCR label right of vernier zero"`

### Task 2: Preserve and Validate ROI Candidates

**Files:**
- Modify: `caliper/roi_extract.py:399-495`
- Modify: `caliper/roi_extract.py:624-754`
- Modify: `caliper/roi_extract.py:757-902`
- Create: `tests/test_roi_candidate_selection.py`

**Interfaces:**
- Produces `_select_reading_roi_candidate(enhanced, projection_box, body_box, x_diag, compact_builder=None, structure_validator=None) -> tuple[tuple, dict]`.
- Diagnostics contain `candidate_boxes`, `selected_stage`, and `fallback_reason`.

- [ ] **Step 1: Write failing candidate-choice tests**

Use a synthetic `np.zeros((200, 500), np.uint8)` image. Set projection box to `(20, 180, 10, 490)`, body box to `(30, 170, 20, 450)`, and compact box to `(40, 160, 80, 300)`.

When `compact_builder=lambda *_: compact` and `structure_validator=lambda *_: False`, assert selected equals the body box and `fallback_reason == 'compact_structure_invalid'`.

When the validator returns `True`, assert selected equals compact and `selected_stage == 'compact'`.

- [ ] **Step 2: Verify failure**

Run: `python -m unittest tests.test_roi_candidate_selection -v`

Expected: import failure for `_select_reading_roi_candidate`.

- [ ] **Step 3: Implement non-destructive selection**

The selector must:
1. Build compact ROI from `_refine_roi_to_reading_window(enhanced, *body_box, x_diag)`.
2. Store all three candidates in `info['candidate_boxes']`.
3. Accept compact only when `_reading_roi_preserves_structure(enhanced, compact, x_diag)` returns true.
4. Otherwise return the body box with `selected_stage='body'`, and set `fallback_reason='compact_structure_invalid'` when a compact proposal existed.

The validator must reject a compact ROI when horizontal-band analysis does not expose both main and vernier bands, or when it excludes the body center observed over the full projected y band by more than one measured tick gap. It must not evaluate expected tick count.

In `_proj_find_x_range`, locate the body on the full projected y band before accepting the periodic ruler segment. If that segment excludes the body, return a dynamic tick-gap-margin span around the observed body. This rejects the `40.30` ruler tail.

In `locate_roi_lowres`, retain projection and body boxes and call the selector. Keep box diagnostics in the result and draw selected red, projection cyan, body yellow, rejected compact orange.

- [ ] **Step 4: Verify tests**

Run: `python -m unittest tests.test_roi_candidate_selection tests.test_main_ocr_grouping -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run: `git add caliper/roi_extract.py tests/test_roi_candidate_selection.py`
Run: `git commit -m "fix: validate compact reading-window ROI"`

### Task 3: Dataset Regression and Diagnostics

**Files:**
- Create: `tools/evaluate_reading_window_roi.py`
- Create: `tests/test_reading_window_roi_regression.py`
- Modify: `docs/tick_visualization.md`

**Interfaces:**
- Produces `evaluate_images(names) -> list[dict]`.
- Writes `debug_tupian_reading_window_roi_20260719/evaluation.json`.

- [ ] **Step 1: Write failing dataset assertions**

Assert that `evaluate_images(['40.20.jpg', '40.30.jpg', '100.60.jpg', '80.80.jpg'])` returns rows whose `vernier_tick_count >= 40`.

Assert that `evaluate_images(['50.98.jpg', '100.00.jpg', '120.60.jpg'])` returns rows whose `reading_mm > 0`.

- [ ] **Step 2: Verify failure**

Run: `python -m unittest tests.test_reading_window_roi_regression -v`

Expected: import failure for `evaluate_images`.

- [ ] **Step 3: Implement exporter**

For each normal pipeline result, record image, original ROI box, ROI selection diagnostics, main/vernier tick counts, zero x, OCR text, and final reading. Export ROI debug and final annotation. Document the ROI colors and fallback fields in `docs/tick_visualization.md`.

- [ ] **Step 4: Run focused and dataset checks**

Run: `python -m unittest tests.test_main_ocr_grouping tests.test_roi_candidate_selection tests.test_reading_window_roi_regression -v`

Expected: all tests pass.

Run: `python tools/evaluate_reading_window_roi.py`

Expected: JSON and images exist; `40.20`, `40.30`, `100.60`, and `80.80` retain vernier evidence and normal controls retain nonzero readings.

- [ ] **Step 5: Commit**

Run: `git add tools/evaluate_reading_window_roi.py tests/test_reading_window_roi_regression.py docs/tick_visualization.md`
Run: `git commit -m "test: add reading-window ROI regression diagnostics"`

## Plan Self-Review

- Task 1 covers bound OCR `N - 1` fallback.
- Task 2 covers compact ROI validation, vertical rollback, ruler-tail rejection, and no-template behavior.
- Task 3 covers failed samples, normal controls, and diagnostic export.
- All public helper names and result keys are defined before their consumers.
