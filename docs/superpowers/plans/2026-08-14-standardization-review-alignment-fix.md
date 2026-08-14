# Standardization Review Alignment Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the standalone standardization review figures use one explicit half-open local x-domain so every displayed image pixel, tick marker, and curve sample maps to the same screen coordinate.

**Architecture:** Keep the recognition and standardization data unchanged. Update only the review exporter: derive one display domain `[start, end)` in standardization-local coordinates, extract the rotated image with the exact corresponding source interval, and render both image pixels and curve samples through the same local-to-screen mapping. Add metadata and tests that fail when the image and curve spans differ or when marker coordinates are computed from different domains.

**Tech Stack:** Python 3, NumPy, OpenCV, pytest.

## Global Constraints

- This is a display/export fix only; formal reading, tick detection, zero-line detection, and standardization arrays must not change.
- Use half-open intervals `[start, end)` everywhere internally; serialized `crop_x` and `curve_x_local` must document the same convention.
- Do not fabricate missing ticks or force a 51-tick grid.
- Preserve existing rotated ROI input and fixed curve y-axis range.
- Keep fast mode unchanged; only the standalone review export is modified.

---

### Task 1: Add failing domain-consistency tests

**Files:**
- Modify: `tests/test_standardization_review_figures.py`
- Test: `tests/test_standardization_review_figures.py`

**Interfaces:**
- Consumes: `render_review_figure`, synthetic standardization records, rotated ROI arrays.
- Produces: assertions for `display_domain`, exact source/curve span equality, and shared marker mapping.

- [ ] **Step 1: Write tests for the explicit half-open domain.**

```python
def test_review_metadata_uses_one_half_open_display_domain():
    rotated = np.full((50, 80, 3), 160, dtype=np.uint8)
    result = {
        'standardization': _standardization(),
        'main_ticks': [{'x': 12}, {'x': 28}, {'x': 44}, {'x': 60}],
    }
    _image, metadata = render_review_figure(
        rotated, _split_result(), 'main', result, '30.00.jpg'
    )
    assert metadata['display_domain'] == {'start': 0, 'end': 80}
    assert metadata['image_source_x'] == [0, 80]
    assert metadata['curve_source_x'] == [0, 80]
    assert metadata['source_span'] == metadata['curve_span'] == 80


def test_review_image_and_curve_keep_marker_positions_when_crop_is_not_full_width():
    rotated = np.full((50, 100, 3), 160, dtype=np.uint8)
    split = _split_result()
    split['region_main']['tick_band'] = (7, 20)
    standardization = _standardization(width=100)
    standardization['ticks'] = [
        {'x': 20.0, 'x_local': 20.0, 'x_projection': 20.0},
        {'x': 80.0, 'x_local': 80.0, 'x_projection': 80.0},
    ]
    result = {'standardization': standardization, 'main_ticks': []}
    _image, metadata = render_review_figure(
        rotated, split, 'main', result, '30.00.jpg'
    )
    assert metadata['source_span'] == metadata['curve_span']
    assert metadata['tick_screen_x_image'] == metadata['tick_screen_x_curve']
```

- [ ] **Step 2: Run the focused tests and verify the new metadata assertions fail before implementation.**

Run: `python -m pytest tests/test_standardization_review_figures.py -q`

Expected: the existing tests pass, while the new `display_domain`/span assertions fail because the exporter does not yet expose the explicit shared domain.

---

### Task 2: Implement one shared image/curve display domain

**Files:**
- Modify: `tools/export_standardization_review_figures.py:87-386`

**Interfaces:**
- Consumes: `standardization.width`, `standardization.x_offset`, vernier `vernier_tick_roi`, accepted tick records, rotated ROI.
- Produces: `_curve_crop_range` returning a single half-open domain; `_draw_image_content` and `_curve_panel` both consume that domain; metadata fields `display_domain`, `image_source_x`, `curve_source_x`, `source_span`, `curve_span`.

- [ ] **Step 1: Make `_curve_crop_range` return the shared local domain and exact source interval.**

Use the following return contract:

```python
return {
    'start': int(start),
    'end': int(end),
    'image_x1': int(x_offset + start),
    'image_x2': int(x_offset + end),
    'x_offset': int(x_offset),
    'width': int(width),
}
```

Clamp `start` and `end` so `0 <= start < end <= width` and `0 <= image_x1 < image_x2 <= rotated_width`. Do not add an inclusive endpoint to either slice.

- [ ] **Step 2: Render image pixels from exactly `[image_x1:image_x2]` and curve samples from exactly `[start:end]`.**

Pass the same `start` and `end` to both panels. The image renderer may resize the complete crop to the fixed content rectangle for readability, but it must report `source_span = image_x2 - image_x1`; the curve renderer must report `curve_span = end - start`. Both spans must be equal before export; otherwise raise a `ValueError` instead of silently drawing a misleading comparison.

- [ ] **Step 3: Centralize the screen mapping.**

Keep `_map_content_x(x_local, start, end, left, right)` as the only conversion from local x to screen x. Use it for tick markers, zero marker, image overlay positions, and curve vertical guides. For curve samples, map the sample's local x as `start + index`, not a separately inferred width.

- [ ] **Step 4: Add explicit metadata and a visible domain label.**

Add to each figure summary:

```python
'display_domain': {'start': int(start), 'end': int(end)},
'image_source_x': [int(image_x1), int(image_x2)],
'curve_source_x': [int(start), int(end)],
'source_span': int(image_x2 - image_x1),
'curve_span': int(end - start),
```

Use the existing title/footer area to display `x=[start,end)` so reviewers can distinguish the source interval from the screen rectangle.

- [ ] **Step 5: Run focused tests.**

Run: `python -m pytest tests/test_standardization_review_figures.py -q`

Expected: all review exporter tests pass, including the new domain/span assertions.

---

### Task 3: Export and inspect corrected audit figures

**Files:**
- Create: `debug_tupian_standardization_review_20260814_v2/`
- Modify: none in production code.

**Interfaces:**
- Consumes: `tools/export_standardization_review_figures.py` and the existing five audit samples.
- Produces: ten corrected PNGs plus `standardization_review_summary.json` with domain metadata.

- [ ] **Step 1: Export the five sample pairs.**

Run:

```powershell
python tools/export_standardization_review_figures.py `
  --input-dir tupian `
  --output-dir debug_tupian_standardization_review_20260814_v2 `
  --image 30.00.jpg `
  --image 72.52.jpg `
  --image 90.14.jpg `
  --image 120.60.jpg `
  --image 140.00.jpg
```

- [ ] **Step 2: Verify every exported pair mechanically.**

Run a small JSON audit that asserts for every main/vernier figure:

```python
assert figure['source_span'] == figure['curve_span']
assert figure['image_source_x'][1] - figure['image_source_x'][0] == figure['source_span']
assert figure['curve_source_x'][1] - figure['curve_source_x'][0] == figure['curve_span']
assert figure['tick_screen_x_image'] == figure['tick_screen_x_curve']
```

- [ ] **Step 3: Visually inspect at least `30.00`, `72.52`, and `120.60`.**

Confirm that the upper crop contains the same tick interval named in the footer and that every green/red marker intersects the corresponding visible upper stroke while matching the lower peak/guide.

---

### Task 4: Regression verification and handoff

**Files:**
- Modify: `tests/test_standardization_review_figures.py` only if assertions need compatibility updates.

- [ ] **Step 1: Run all standardization and review tests.**

Run:

```powershell
python -m pytest tests/test_standardization_review_figures.py tests/test_standardization_visual_exports.py tests/test_vernier_standard_curve.py tests/test_vernier_standardization_contract.py -q
```

Expected: all tests pass; any Windows temporary-directory permission warning is reported separately and not treated as a code failure.

- [ ] **Step 2: Confirm formal reading invariance.**

Run the existing detailed pipeline tests and compare `total`, `zero_x`, and alignment fields before/after export changes. The exporter must not import or mutate recognition arrays.

- [ ] **Step 3: Report the corrected output directory and remaining visual limitations.**

State clearly whether the upper image strokes themselves align with lower peaks, not merely whether marker lines share screen x. If a stroke is slanted or missing, record that as an input/recognition limitation rather than hiding it with a marker.
