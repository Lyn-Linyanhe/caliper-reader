# Per-Tick Vernier Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the invalid common-slope shear experiment with a display-only, per-observed-tick straightening diagnostic.

**Architecture:** For every existing vernier candidate, trace only the seam-connected thin stroke row by row and record its own centreline. Shift only that trace's pixels to its own seam-side reference x, producing a diagnostic projection assembled from independently straightened observed strokes. The detector, zero selection, alignment and reading continue to use the original band.

**Tech Stack:** Python, NumPy, OpenCV, pytest.

## Global Constraints

- Delete all common-slope shear code, configuration, tests and documentation.
- No theoretical grid, fixed tick count, missing-tick filling or file-name input.
- A trace stops before a widened digit, a horizontal jump, or a long blank gap.
- Only detailed mode generates the per-tick correction evidence.
- The diagnostic must not alter `vernier_ticks`, `zero_x`, alignment or `CaliperResult.total`.

---

### Task 1: Trace individual seam-connected strokes

**Files:**
- Modify: `caliper/vernier_scale.py`
- Modify: `tests/test_vernier_per_tick_correction.py`

- [x] Write a failing synthetic test for `_trace_vernier_tick_centerline(band, approx_x, observed_period)`: a line sloping right by one pixel every five rows returns its seam reference x and one centre point per row.
- [x] Run `python -m pytest -q tests/test_vernier_per_tick_correction.py`; confirm missing-helper failure.
- [x] Implement narrow-segment tracking using the existing top-stroke width, continuity and gap constraints; return `points`, `reference_x`, `y_start` and `y_end`.
- [x] Re-run the focused test; confirm it passes.

### Task 2: Build a per-tick straightened diagnostic band

**Files:**
- Modify: `caliper/vernier_scale.py`
- Modify: `tests/test_vernier_per_tick_correction.py`

- [x] Write a failing synthetic test for `_build_per_tick_straightened_band(...)`: two lines with opposite slopes both become vertical at their independent seam references, while an untraced digit-like wide component is absent.
- [x] Run the test and confirm it fails because the builder does not exist.
- [x] Implement row-wise translation for every traced narrow segment using `reference_x - centre_x`; compose only those shifted segments in a blank diagnostic band.
- [x] Delete `_estimate_vernier_band_shear`, `_apply_vernier_band_shear`, branch selection helpers and associated configuration.
- [x] Re-run focused tests.

### Task 3: Visualize and validate without changing reading

**Files:**
- Modify: `caliper/vernier_scale.py`
- Modify: `tests/test_vernier_debug_panel.py`
- Modify: `README.md`

- [x] Write a detailed-mode test asserting the returned diagnostic contains traces and a per-tick projection while detailed and fast results retain identical `total` and `zero_x`.
- [x] Run it against the new detailed diagnostic.
- [x] Add to the existing `4b_游标刻线` page: a raw-band trace overlay, the raw projection and the independently straightened projection. Mark raw and corrected candidates separately.
- [x] Run `python -m pytest -q tests/test_vernier_per_tick_correction.py tests/test_vernier_debug_panel.py tests/test_vernier_valley_regressions.py tests/test_vernier_top_stroke_split.py tests/test_alignment_ambiguity.py`.
- [x] Export and inspect `72.52.jpg`, `50.00.jpg`, `30.00.jpg`; report trace count and projection evidence. `72.52` traces 50/52, `50.00` traces 24/52, and `30.00` traces 50/51.
