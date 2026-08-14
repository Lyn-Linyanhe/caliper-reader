# Vernier Debug Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show vernier valley selection and connected-component evidence beneath the existing vernier-tick image in detailed mode.

**Architecture:** `recognize_vernier_scale(..., make_debug=True)` will produce one vertically stacked `vis_ticks` image: existing tick view, valley view, and a new connected-component view. `CaliperPipeline` will continue to publish only `4b_游标刻度线`; fast mode remains unchanged because it keeps `make_debug=False`.

**Tech Stack:** Python 3.13, OpenCV, NumPy, pytest, Tkinter.

## Global Constraints

- Do not change ROI, split, valley selection, tick selection, or reading logic.
- Do not create a new UI tab.
- Do not generate the new visuals in fast mode.
- Visuals must use existing detected candidates and components only.

---

### Task 1: Specify Composite Vernier Debug Output

**Files:**
- Modify: `tests/test_vernier_debug_panel.py`
- Modify: `caliper/vernier_scale.py`

**Interfaces:**
- Consumes: `recognize_vernier_scale(region, main_gap, make_debug)`.
- Produces: non-empty `vis_ticks` that is taller than the original tick-only visualization, while `make_debug=False` retains no visualization.

- [ ] **Step 1: Write the failing test**

```python
def test_detailed_vernier_visual_stacks_valley_and_component_evidence():
    detailed = _run('60.50.jpg', make_debug=True)
    fast = _run('60.50.jpg', make_debug=False)

    assert detailed['vis_ticks'].shape[0] > 900
    assert fast['vis_ticks'] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vernier_debug_panel.py -q`

Expected: FAIL because the old tick-only image is shorter than the composite image.

- [ ] **Step 3: Implement the minimum output composition**

```python
def _stack_vernier_debug_views(*views):
    # Normalize widths, add separators, and vertically stack non-empty views.
    ...
```

Call it only when `make_debug=True`, passing the existing tick image, existing valley image, and a component-evidence image built from `band_detection` candidates.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_vernier_debug_panel.py -q`

Expected: PASS.

### Task 2: Verify Pipeline/UI Contract

**Files:**
- Test: `tests/test_vernier_debug_panel.py`
- Verify: `caliper/pipeline.py`, `main.py`

**Interfaces:**
- Consumes: pipeline debug key `4b_游标刻度线`.
- Produces: the existing UI tab renders the composite image without any new tab key.

- [ ] **Step 1: Add pipeline contract assertion**

```python
def test_pipeline_publishes_composite_under_existing_vernier_key():
    pipeline = CaliperPipeline(fast_mode=False)
    pipeline.run(_image('60.50.jpg'))

    assert '4b_游标刻度线' in pipeline.debug_images
    assert '4a_游标谷底' not in pipeline.debug_images
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vernier_debug_panel.py::test_pipeline_publishes_composite_under_existing_vernier_key -q`

Expected: FAIL until the component visual is appended to the published tick image.

- [ ] **Step 3: Verify detailed and fast pipeline behavior**

Run: `pytest tests/test_vernier_debug_panel.py -q`

Expected: PASS; no additional debug key is published in either mode.

### Task 3: Regress Reading and Inspect Output

**Files:**
- Verify: `tests/test_vernier_top_stroke_split.py`
- Verify: `tupian/60.50.jpg`, `tupian/75.58.jpg`

- [ ] **Step 1: Run zero-line regressions**

Run: `$env:PYTHONPATH='.'; pytest tests/test_vernier_top_stroke_split.py -q`

Expected: PASS.

- [ ] **Step 2: Export two detailed pipeline images**

Run the detailed pipeline on `60.50.jpg` and `75.58.jpg`, write `vis_ticks` under a new debug directory, and inspect that each image contains three stacked sections.

- [ ] **Step 3: Run complete suite**

Run: `$env:PYTHONPATH='.'; pytest tests -q`

Expected: only the known unrelated `40.20` ROI/seam assertions may fail; all visual and vernier regression tests pass.
