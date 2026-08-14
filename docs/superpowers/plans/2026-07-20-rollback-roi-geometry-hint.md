# Roll Back Premature ROI Geometry Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the conservative ROI and post-orientation detection path, then reintroduce valley and vertical-component evidence only inside the final `region_vernier`.

**Architecture:** ROI remains a broad-to-compact crop selector and must not determine ruler split, vernier tick positions, or zero-line coordinates. After orientation and `split_scales()`, `recognize_vernier_scale()` owns all valley-pair selection and uses the real final `region_vernier` tick band. Vertical opening remains an evidence filter for candidates; raw projection remains the source of valley and peak positions.

**Tech Stack:** Python 3, OpenCV, NumPy, standard-library `unittest`.

## Global Constraints

- Do not use the image filename in production recognition logic.
- Do not impose 51 ticks, generate missing ticks, or fit a theoretical tick curve/grid.
- Do not use OCR text to select an ROI boundary.
- Keep the broad projection, body, and compact ROI candidates; never replace a compact candidate with a visibly wider fallback merely because downstream OCR failed.
- Do not change the existing OCR expanded-retry, multi-digit grouping, main-scale short-tick recovery, or final read-merger behavior in this task.
- Run tests with `python -m unittest`; `pytest` is unavailable.
- Preserve existing user work in the dirty worktree. Do not run reset, checkout, or clean.

---

### Task 1: Lock the ROI Boundary Contract

**Files:**
- Modify: `tests/test_roi_candidate_selection.py`
- Modify: `caliper/roi_extract.py:954-1239`

**Interfaces:**
- `_select_reading_roi_candidate(enhanced, projection_box, body_box, x_diag, compact_builder=None, structure_validator=None) -> tuple[tuple, dict]` continues to return a selected box and diagnostic dictionary.
- `info['candidate_boxes']` contains only `projection`, `body`, and `compact` candidates.
- `info['selected_stage']` is one of `projection`, `body`, or `compact`.

- [ ] **Step 1: Write failing tests for ROI isolation**

  Add a test that patches `caliper.roi_extract._find_vernier_reading_window` to raise `AssertionError('ROI must not run ruler splitting')`, then calls `_select_reading_roi_candidate(...)` with the existing synthetic fixture. Assert no assertion is raised and the compact/body selector behaves exactly as today.

  Add a test that calls `locate_roi_lowres()` on `tupian/30.00.jpg`, then asserts:

  ```python
  selection = result['roi_selection']
  self.assertNotIn('vernier_window', selection['candidate_boxes'])
  self.assertNotEqual(selection['selected_stage'], 'geometry_refined')
  self.assertIsNone(result.get('roi_refinement'))
  ```

- [ ] **Step 2: Verify the tests fail for the intended reason**

  Run:

  ```powershell
  python -m unittest tests.test_roi_candidate_selection.ReadingRoiCandidateSelectionTests.test_roi_selection_does_not_run_vernier_geometry -v
  python -m unittest tests.test_roi_candidate_selection.ReadingRoiCandidateSelectionTests.test_lowres_roi_has_no_cross_stage_geometry_refinement -v
  ```

  Expected: the first test fails because `_select_reading_roi_candidate()` calls `_find_vernier_reading_window()`; the second fails because the result contains the geometry-refinement state.

- [ ] **Step 3: Remove premature geometry decisions from ROI selection**

  In `caliper/roi_extract.py`:

  - Delete `_find_vernier_reading_window()` and all ROI-only geometry diagnostics it exists to support.
  - In `_select_reading_roi_candidate()`, build only the existing compact candidate. Keep the existing structure validator and body fallback behavior.
  - Remove `vernier_window`, `roi_refinement`, and `geometry_refined` from `candidate_boxes`, result dictionaries, and ROI visualization colors.
  - In `locate_roi_lowres()`, stop returning `roi_refinement`; preserve `roi_selection` and the three crop candidates for diagnostics.

  The selector must follow this precise decision order:

  ```python
  if compact is not None and structure_validator(enhanced, compact, x_diag):
      return compact, compact_info
  if compact is not None:
      info['fallback_reason'] = 'compact_structure_invalid'
  if body_box is not None:
      return body_box, body_info
  info['selected_stage'] = 'projection'
  info['fallback_reason'] = 'body_unavailable'
  return projection_box, info
  ```

- [ ] **Step 4: Verify the ROI tests pass**

  Run:

  ```powershell
  python -m unittest tests.test_roi_candidate_selection -v
  ```

  Expected: candidate-selection tests pass after removing/replacing old geometry-refinement assertions. The `100.60` and `40.20` structure-preservation tests remain enabled.

### Task 2: Remove Cross-Rotation Geometry Hints

**Files:**
- Modify: `tests/test_roi_candidate_selection.py`
- Modify: `caliper/pipeline.py:21-52,189-230`
- Modify: `caliper/vernier_scale.py:1618-1738`

**Interfaces:**
- `CaliperPipeline._run_remainder(original, orient_result, progress_callback=None) -> CaliperResult` has no geometry-hint parameter.
- `recognize_vernier_scale(region, main_gap, color_region=None, main_ticks=None, make_debug=True) -> dict` has no geometry-hint parameter.

- [ ] **Step 1: Write a failing no-fallback test**

  Add a test that creates the real `region_vernier` from `tupian/30.00.jpg` after preprocessing, orientation, and `split_scales()`. Patch `_detect_vernier_band_projection` to return `None`, call `recognize_vernier_scale(...)`, and assert:

  ```python
  self.assertEqual(result['failure_reason'], 'no_reliable_valley_bounded_tick_range')
  ```

  This asserts that the recognizer reports a missing final-region observation rather than accepting a low-resolution ROI-derived substitute.

- [ ] **Step 2: Verify the test fails for the intended reason**

  Run:

  ```powershell
  python -m unittest tests.test_roi_candidate_selection.ReadingRoiCandidateSelectionTests.test_vernier_detector_has_no_roi_geometry_fallback -v
  ```

  Expected: it fails because the current detector can invoke `_detect_vernier_band_from_geometry_hint()`.

- [ ] **Step 3: Remove the hint transport and fallback**

  In `caliper/pipeline.py`:

  - Delete `_map_roi_geometry_hint()`.
  - Stop computing `geometry_hint` after orientation.
  - Restore `_run_remainder()` to three arguments and call `recognize_vernier_scale()` without an extra hint.

  In `caliper/vernier_scale.py`:

  - Delete `_detect_vernier_band_from_geometry_hint()`.
  - Remove `geometry_hint` from `recognize_vernier_scale()` and delete its fallback call.
  - Preserve `_detect_vernier_band_projection()` as the sole source of a horizontal vernier range.

- [ ] **Step 4: Verify the focused tests pass**

  Run:

  ```powershell
  python -m unittest tests.test_roi_candidate_selection tests.test_main_ocr_grouping -v
  ```

  Expected: all focused tests pass. A failed final-region valley detection returns the explicit existing failure reason and does not synthesize a zero line.

### Task 3: Make Final-Region Valley Evidence Explicit

**Files:**
- Modify: `tests/test_vernier_scale.py` or create `tests/test_vernier_valley_evidence.py`
- Modify: `caliper/vernier_scale.py:_detect_vernier_band_projection`

**Interfaces:**
- `_detect_vernier_band_projection(binary, main_gap, gray, tick_band=None) -> dict | None` remains the only range detector.
- A successful result includes `source='final_region_valley_projection'`, `selected_valley_pair`, `tick_xs_global`, `period_clarity`, `component_support`, `selection_score`, and `tick_structure`.

- [ ] **Step 1: Write failing observed-evidence tests**

  Build `region_vernier` from `tupian/24.20.jpg`, `72.52.jpg`, `74.56.jpg`, and `100.60.jpg` using the real pipeline up to region split. For each successful detection, assert the following are image-observed values rather than a fixed count:

  ```python
  self.assertEqual(detection['source'], 'final_region_valley_projection')
  self.assertGreaterEqual(len(detection['tick_xs_global']), 3)
  self.assertEqual(len(detection['selected_valley_pair']), 2)
  self.assertGreater(detection['period_clarity'], 0.0)
  ```

  Add a synthetic binary image with two low-projection valleys and observed vertical components; assert candidates outside the selected valley pair are absent from `tick_xs_global`.

- [ ] **Step 2: Verify failures**

  Run:

  ```powershell
  python -m unittest tests.test_vernier_valley_evidence -v
  ```

  Expected: source naming or selected-pair containment assertions fail before the diagnostics are made explicit.

- [ ] **Step 3: Make the final-region evidence auditable**

  In `_detect_vernier_band_projection()`:

  - Retain raw vertical projection and valley-pair scoring as the coordinate source.
  - Retain vertical opening only for connected-component support and candidate validation.
  - Record the selected left/right valley segment and reject all candidates outside its interior plus the existing measured-period context margin.
  - Use one-to-one component assignment when two projection peaks compete for the same component.
  - Do not add absent peaks, fixed tick counts, or a theoretical curve.
  - Emit `source='final_region_valley_projection'` and diagnostics sufficient for visual export.

- [ ] **Step 4: Verify final-region tests pass**

  Run:

  ```powershell
  python -m unittest tests.test_vernier_valley_evidence -v
  ```

  Expected: all candidates are within the measured valley range and are backed by observed projection/component evidence.

### Task 4: Compare the Dataset Against the Last Good Baseline

**Files:**
- Modify: `tools/evaluate_all_pipeline.py`
- Create: `tools/export_final_region_valley_diagnostics.py`
- Modify: `docs/tick_visualization.md`

**Interfaces:**
- `tools/evaluate_all_pipeline.py` writes a dated output directory rather than overwriting `debug_tupian_all_results_20260719/evaluation.json`.
- `tools/export_final_region_valley_diagnostics.py` accepts one or more filenames and exports the final ROI, split line, raw projection, valleys, accepted/rejected candidates, connected-component support, and zero line.

- [ ] **Step 1: Write failing output-location and diagnostic-content tests**

  Add a test for the evaluator output-path builder that asserts output includes a caller-supplied run label. Add a test for the diagnostic-record serializer asserting the fields `selected_valley_pair`, `all_valley_segments`, `tick_xs_global`, `component_support`, and `source` exist.

- [ ] **Step 2: Verify failures**

  Run:

  ```powershell
  python -m unittest tests.test_evaluate_all_pipeline tests.test_vernier_valley_diagnostics -v
  ```

  Expected: tests fail because output is currently hard-coded and no final-region diagnostic serializer exists.

- [ ] **Step 3: Implement reproducible evaluation and visual export**

  - Add an optional `--run-label` argument to `tools/evaluate_all_pipeline.py`; its default is the current date. Write to `debug_tupian_all_results_<run-label>/evaluation.json`.
  - Implement the diagnostic exporter without using filename-derived recognition input. Filenames are only requested/exported test artifacts.
  - Add color/line meanings to `docs/tick_visualization.md`: raw projection, valley pair, accepted candidate, rejected candidate, component-supported candidate, split line, and zero line.

- [ ] **Step 4: Run focused samples and the complete 48-image regression**

  Run:

  ```powershell
  python tools/export_final_region_valley_diagnostics.py 24.20.jpg 72.52.jpg 74.56.jpg 100.60.jpg
  python tools/evaluate_all_pipeline.py --run-label 20260720_rollback
  ```

  Record and compare:

  | Metric | Current failed integration baseline | Acceptance target |
  | --- | ---: | ---: |
  | Images with error <= 0.50 mm | 20 / 48 | At least 34 / 48 |
  | Mean absolute error | 24.9767 mm | At most 16.54 mm |
  | `100.00`, `110.00`, `14.80`, `24.20`, `40.30` severe regressions | Present | No worse than pre-integration results |

  The task is not accepted if a target sample improves while aggregate metrics remain below the prior baseline.

- [ ] **Step 5: Produce the review summary**

  List the exact before/after metric counts, all samples above `0.50 mm`, and links to each focused visual diagnostic. Separate ROI/split/OCR/main-tick/vernier-zero failure categories so later changes are based on observed error modes.

## Plan Self-Review

- Task 1 removes only the low-resolution ROI-stage full ruler split and preserves conservative crop validation.
- Task 2 removes only cross-rotation/cross-scale geometry propagation and leaves the final-region detector as the source of truth.
- Task 3 keeps the user-approved double-valley approach and vertical opening, while explicitly prohibiting theoretical curves, tick fitting, and 51-tick assumptions.
- Task 4 makes each change measurable against the known 48-image baseline and produces inspectable evidence for later tuning.
