# Baseline Error Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the five evidence-backed baseline errors without changing the established ROI, region-split, vernier, or OCR behavior for the other images.

**Architecture:** Keep the existing recognition path as the authority and add narrowly scoped fallbacks only at the stage that is demonstrably failing. OCR gets a grayscale-specific candidate branch, region splitting gets a local starvation recovery, vernier detection gets evidence-gated candidate recovery, and alignment exposes globally near-equivalent candidates instead of pretending that a pixel-level tie is unique. The original result remains deterministic and is retained as the primary result.

**Tech Stack:** Python, OpenCV, NumPy, pytest, the existing `CaliperPipeline` and `tools/evaluate_all_pipeline.py` batch evaluator.

**Spec:** `debug_tupian_batch_evaluation_20260814_baseline/evaluation.json` and `debug_tupian_batch_evaluation_20260814_baseline_diagnostics/diagnostics.json`.

## Global Constraints

- Do not force the vernier detector to output 51 lines.
- Do not replace the current ROI candidate-selection strategy globally.
- Do not replace the current valley-bounded vernier region logic globally.
- Do not use the filename truth inside the recognition pipeline; filenames are evaluation truth only.
- Every change must be checked against all 49 input images, with 48 numeric truths.
- The existing fast path and detailed/debug path must keep the same formal tick positions and reading unless a test explicitly covers the new recovery behavior.
- A fallback may be selected only when the current stage reports a failure or a measured evidence condition defined in the task.

---

### Task 1: Establish a machine-readable before/after baseline

**Files:**
- Modify: `tools/evaluate_all_pipeline.py` only if a stable JSON summary field is missing.
- Test: `tests/test_batch_evaluation_report.py`
- Artifacts: `debug_tupian_batch_evaluation_20260814_baseline/`

**Interfaces:**
- Consumes: `tupian/*.jpg`, `CaliperPipeline(fast_mode=True)`.
- Produces: a summary containing `count_total`, `count_with_truth`, `count_failed`, all three tolerance counts, and per-image `reading_mm`, `abs_error_mm`, `suspected_error_module`, and stage diagnostics.

- [ ] **Step 1: Assert the current baseline contract**

  Add or retain tests that verify the evaluator records 49 images, 48 numeric truths, zero pipeline failures, and the five current rows with errors above `0.10 mm`.

- [ ] **Step 2: Run the baseline command**

  Run:

  ```powershell
  python tools/evaluate_all_pipeline.py --input-dir tupian --output-dir debug_tupian_batch_evaluation_20260814_baseline
  ```

  Expected baseline: 28/48 within `0.02 mm`, 43/48 within `0.10 mm`, 46/48 within `0.50 mm`; errors are `130.70`, `40.20`, `140.00`, `60.96`, and `50.50`.

- [ ] **Step 3: Commit the baseline artifact metadata**

  Record the command and summary in the plan or evaluation metadata. Do not overwrite the input images or formal recognition code.

### Task 2: Recover the clipped outer ROI for `130.70` without changing global ROI ordering

**Files:**
- Modify: `caliper/roi_extract.py` (full-body evidence propagation and a bounded recovery candidate).
- Modify: `caliper/pipeline.py` (trigger recovery for short runs even when `error` is `None`).
- Test: `tests/test_roi_candidate_selection.py`.

**Interfaces:**
- Consumes: the projection-selected body box, the independently measured full-height body range, and the current vernier reliability gate.
- Produces: the unchanged primary ROI plus a bounded local candidate only when the selected body box is asymmetric around the full-body evidence. No global candidate priority changes and no synthetic ticks.

- [ ] **Step 1: Add a failing regression test for the current `130.70` selection**

  Run the real `130.70.jpg` ROI path and assert that the current `body` box starts to the right of the full-height body range and ends in the ruler tail. The test must fail until `full_y_body` is exposed and a bounded candidate restores the missing left span while trimming the tail.

- [ ] **Step 2: Define a bounded recovery evidence gate**

  Keep the existing projection/body/compact ordering. Generate one candidate from the full-body span only when both left truncation and right-tail measurements exceed the larger of two measured tick gaps or 4% of the body width:

  ```python
  margin = max(8, round(2.0 * measured_tick_gap))
  trigger_gap = max(margin, round(0.04 * full_body_width))
  recovery = (
      selected_x1 - full_body_x1 >= trigger_gap
      and selected_x2 - full_body_x2 >= trigger_gap
  )
  ```

  The candidate is bounded by `full_body_x1 - margin` and `full_body_x2 + margin`; it is a diagnostic/recovery crop, not a forced 51-line fit.

- [ ] **Step 3: Select the recovered pair only under the gate**

  Preserve the original result when its vernier run is reliable. For a short run, try the local candidate and accept it only if the existing vernier reliability gate passes; otherwise restore the original result and record the failed attempt in `roi_recovery`.

- [ ] **Step 4: Verify the target and controls before touching OCR**

  Run the focused ROI tests and the real images `130.70.jpg`, `30.00.jpg`, `33.00.jpg`, `90.14.jpg`, and `71.50.jpg`. Expected: controls retain their existing selected pair and reading; `130.70` exposes a measured recovery attempt without accepting an unvalidated partial crop. OCR remains a separate later task if the recovered ROI still leaves no main-digit candidate.

### Task 3: Add local region-split starvation recovery for `40.20`

**Files:**
- Modify: `caliper/region_split.py` only in a fallback helper called after the current split and band construction.
- Modify: `caliper/vernier_scale.py` only to expose a structured “no reliable valley-bounded tick range” result if it is not already present.
- Test: `tests/test_region_split_endpoint_seam.py` and a new `tests/test_region_split_starvation_recovery.py` if needed.

**Interfaces:**
- Consumes: the current `split_y`, `seam_source`, `region_vernier`, and binary/gray ROI.
- Produces: either the unchanged current split or a locally adjusted split with `recovery_reason`, `recovery_offset`, and vernier-band evidence.

- [ ] **Step 1: Capture the current failure condition**

  Assert the real `40.20.jpg` state: `seam_source == "projection_valley"`, `split_y == 573`, `main_tick_count == 11`, and zero vernier candidates.

- [ ] **Step 2: Evaluate a bounded seam neighborhood**

  When the current split yields no vernier candidates, test only a small neighborhood around the existing split using the existing band detector. Do not reopen ROI candidate selection and do not change the split for images that already have a valid vernier band.

- [ ] **Step 3: Select recovery by vernier evidence, not by target count**

  Accept a nearby split only when it produces a valley-bounded periodic run with valid two-sided peak support and internal continuity. The candidate count is a tie-breaker only; it must not be a requirement of 51.

- [ ] **Step 4: Verify no broad split regression**

  Run the region-split regression tests and the full evaluator. Confirm that all existing endpoint-seam cases keep their original split source and that `40.20` reaches vernier detection instead of returning an empty region.

### Task 4: Promote evidence-gated vernier candidate recovery for `140.00`

**Files:**
- Modify: `caliper/vernier_scale.py` (`_detect_vernier_band_projection`, `_build_ticks_from_band_detection`, and the existing per-tick correction metadata).
- Test: `tests/test_vernier_per_tick_correction.py`, `tests/test_vernier_valley_regressions.py`.

**Interfaces:**
- Consumes: formal projection candidates, component/top-edge evidence, per-tick traces, and continuity metrics.
- Produces: formal tick candidates only when evidence-gated recovery is valid; otherwise preserves the current formal candidates and diagnostics.

- [ ] **Step 1: Add a failing assertion for `140.00`**

  Record that the current formal path has 44 ticks while the debug evidence has 54 candidates and 52 traces. Also assert that the current result is `140.48`.

- [ ] **Step 2: Separate recovered evidence from synthetic display pixels**

  Ensure candidate recovery uses traced pixels or component/top-edge evidence only. Never use the synthetic continuous display mask as a reading candidate source.

- [ ] **Step 3: Gate promotion on periodic coverage and trace quality**

  Promote recovered candidates only when the selected valley pair remains valid, the recovered positions have stable spacing over the observed run, and the untraced fraction is below the existing diagnostic limit. Do not pad or fit a missing target number.

- [ ] **Step 4: Add the zero-line prior for a near-perfect first tick**

  When the first formal tick/`zero_x` is within the measured pixel tolerance of a main tick and no stronger candidate evidence exists, retain index 0 as a valid alignment candidate. Record the reason in alignment diagnostics rather than silently changing the formula.

- [ ] **Step 5: Verify fast/detail consistency**

  Update the existing fast/detail test so both paths use the same promoted formal candidates and still agree on tick positions and reading for all unaffected images.

### Task 5: Report global alignment ambiguity for `60.96` and `50.50`

**Files:**
- Modify: `caliper/vernier_scale.py` (`find_best_alignment`, `_make_alignment_ambiguity`).
- Modify: `caliper/reading_display.py` and `caliper/merger.py` only for displaying/storing the alternate candidate.
- Test: `tests/test_alignment_ambiguity.py`.

**Interfaces:**
- Consumes: all vernier-to-main pixel errors, `precision`, and `main_gap`.
- Produces: the existing primary reading plus an `alignment_ambiguity` record containing all materially near-equivalent candidate indices, readings, errors, and margin.

- [ ] **Step 1: Add failing tests for non-adjacent ties**

  Construct error arrays where the best candidate and a candidate several indices away differ by less than the configured pixel margin. Assert that both candidates are reported; the current adjacent-only implementation must fail this test.

- [ ] **Step 2: Rank candidates deterministically**

  Keep the minimum-error candidate as primary. Report additional candidates whose error margin is within the configured uncertainty threshold, including non-adjacent indices. Do not change the primary reading merely to match filename truth.

- [ ] **Step 3: Surface the alternate value**

  Preserve the current UI primary value and add a compact alternate/reference string through the existing `format_alignment_ambiguity` path. The result object must remain backward-compatible when no ambiguity exists.

- [ ] **Step 4: Verify the two target images**

  Run the real pipeline for `60.96.jpg` and `50.50.jpg`. Expected: the existing primary values remain deterministic, while the ambiguity record includes the visually plausible alternate candidates rather than claiming a unique alignment.

### Task 6: Full regression and acceptance review

**Files:**
- Modify: no production file unless a test exposes a concrete regression.
- Test: all `tests/` relevant to pipeline, OCR, region split, vernier detection, and alignment.
- Artifacts: `debug_tupian_batch_evaluation_20260814_after_baseline_repair/`

- [ ] **Step 1: Run focused tests**

  Run the OCR, region-split, vernier, and alignment test files before the full suite.

- [ ] **Step 2: Run the full test suite**

  Run `pytest -q` and keep the output in the work log.

- [ ] **Step 3: Run the 49-image evaluator**

  Run:

  ```powershell
  python tools/evaluate_all_pipeline.py --input-dir tupian --output-dir debug_tupian_batch_evaluation_20260814_after_baseline_repair
  ```

- [ ] **Step 4: Compare per-image deltas**

  Require that the five target images improve or gain an explicit ambiguity record, and that every image outside the target set changes by at most the established visual tolerance unless its diagnostic evidence also improves.

- [ ] **Step 5: Update the project documentation**

  Document the fallback trigger, evidence gate, and ambiguity semantics in `README.md` and `docs/项目代码说明书.md`; do not describe diagnostic-only continuous display masks as formal recognition output.

---

## Self-review

- The plan covers the five baseline errors and does not treat the evaluator's module labels as proof of cause.
- No task forces 51 vernier lines or changes the global ROI candidate order.
- OCR, region split, vernier promotion, and alignment each have an isolated regression test before full-batch evaluation.
- The plan preserves both primary readings and explicit uncertainty where the pixels do not support a unique alignment.
