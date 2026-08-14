# Vernier Per-Tick Correction Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the diagnostic vernier correction path account for every formal candidate, recover only candidates supported by real binary evidence, and prove that formal reading remains unchanged.

**Architecture:** Keep formal projection detection, zero-line detection, sub-pixel refinement, and alignment unchanged. Build a separate debug candidate list from formal candidates plus bounded periodic top-projection evidence; trace each candidate independently and retain a state for every candidate, including failures. Export only the binary diagnostic mask and its metadata.

**Tech Stack:** Python 3, NumPy, OpenCV, pytest, existing `CaliperPipeline` diagnostics.

## Global Constraints

- Do not force the diagnostic candidate count to 51.
- Do not create a candidate without binary image evidence.
- Do not feed recovered candidates or the straightened mask into formal reading, zero-line localization, or alignment.
- Use an independent trace for every tick; do not apply one global angle.
- Preserve existing unrelated user changes in the dirty worktree.

---

### Task 1: Preserve unmatched formal candidates in diagnostic recovery

**Files:**
- Modify: `caliper/vernier_scale.py:_recover_binary_top_evidence_ticks`
- Test: `tests/test_vernier_per_tick_correction.py`

**Interfaces:**
- Consumes: `detection`, formal tick records, `x_offset`, `x_start`, `x_end`.
- Produces: one diagnostic record for every in-ROI formal candidate plus any additional binary-top evidence candidate; each record retains `source` and coordinates.

- [x] **Step 1: Write the failing test**

```python
def test_recovery_keeps_formal_candidate_without_top_evidence():
    band = np.zeros((40, 120), dtype=np.uint8)
    band[:30, 20] = 255
    band[:30, 60] = 255
    formal = [
        {'x': 20, 'x_projection': 20},
        {'x': 60, 'x_projection': 60},
        {'x': 100, 'x_projection': 100},
    ]
    detection = {
        'band': band,
        'expected_gap': 40.0,
        'vernier_tick_roi': (20, 101),
    }

    records = vernier_scale._recover_binary_top_evidence_ticks(
        detection, formal, 0, band.shape[1]
    )

    assert {round(record['formal_x_projection']) for record in records
            if 'formal_x_projection' in record} == {20, 60}
    assert any(round(record['x_projection']) == 100 and
               record['source'] == 'formal_projection_unmatched'
               for record in records)
```

- [x] **Step 2: Run the focused test to verify it fails**

Run: `pytest -q tests/test_vernier_per_tick_correction.py::test_recovery_keeps_formal_candidate_without_top_evidence`

Expected: FAIL because the current merge iterates only `evidence_xs` and drops formal x=100.

- [x] **Step 3: Implement the minimal merge fix**

After matching each binary evidence x, append every in-ROI formal record that was not matched. Preserve its original coordinates, set `source` to `formal_projection_unmatched`, and keep a deterministic x sort. Do not append formal records outside the selected ROI.

- [x] **Step 4: Run the focused test to verify it passes**

Run: `pytest -q tests/test_vernier_per_tick_correction.py::test_recovery_keeps_formal_candidate_without_top_evidence`

Expected: PASS.

### Task 2: Strengthen regression coverage for formal-path isolation

**Files:**
- Modify: `tests/test_vernier_per_tick_correction.py`

**Interfaces:**
- Consumes: detailed and fast `CaliperPipeline` results for the same image.
- Produces: assertions that formal ticks, zero line, total, alignment, and reading fields are unchanged by debug correction.

- [x] **Step 1: Add the regression assertions**

Run detailed and fast mode on `tupian/72.52.jpg`; compare formal tick x positions, zero x, total, vernier reading, main reading, aligned tick/index, and alignment error. Assert only the detailed diagnostic correction field differs.

- [x] **Step 2: Run the focused test**

Run: `pytest -q tests/test_vernier_per_tick_correction.py`

Expected: PASS.

### Task 3: Run full verification and export current evidence

**Files:**
- Generate: `debug_tupian_vernier_pixel_correction_current_20260814_v2/`
- Verify: `tools/export_vernier_pixel_correction_images.py`

**Interfaces:**
- Consumes: representative images in `tupian/`.
- Produces: raw binary ROI, straightened binary ROI, comparison figure, and JSON counts/source/status for each selected image.

- [x] **Step 1: Run all relevant tests**

Run: `pytest -q tests/test_vernier_per_tick_correction.py tests/test_vernier_standard_curve.py tests/test_vernier_pixel_correction_export.py tests/test_research_paths_preserved.py`

Expected: PASS with no formal-reading regression.

- [x] **Step 2: Export representative images**

Run:

```powershell
python tools/export_vernier_pixel_correction_images.py `
  --input-dir tupian `
  --output-dir debug_tupian_vernier_pixel_correction_current_20260814_v2 `
  --image 30.00.jpg `
  --image 72.52.jpg `
  --image 90.14.jpg `
  --image 120.60.jpg `
  --image 140.00.jpg
```

- [x] **Step 3: Inspect JSON and images**

Confirm every `candidate_states` entry corresponds to a formal or evidence-backed candidate, `trace_count + untraced_count == candidate_count`, and any unmatched formal candidate carries an explicit failure or fallback state rather than disappearing.
