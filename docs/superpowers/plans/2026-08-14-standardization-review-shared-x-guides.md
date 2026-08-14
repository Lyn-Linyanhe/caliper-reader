# Shared X-Domain Review Guides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the standalone standardization review figures visibly prove that the upper rotated crop and lower normalized curve use the same horizontal display domain.

**Architecture:** Keep the existing display-only half-open source domain `[start, end)` and centralize its conversion to screen coordinates. Render both panels inside the same content rectangle, derive marker positions once, and add shared guide metadata/tests so visual alignment cannot silently diverge.

**Tech Stack:** Python 3, NumPy, OpenCV, pytest.

## Global Constraints

- Change only `tools/export_standardization_review_figures.py` and its focused tests.
- Do not modify formal tick detection, zero-line detection, alignment, readings, or standardization arrays.
- Use half-open intervals `[start, end)` for both the rotated image crop and curve slice.
- Keep the fixed content rectangle (`_CONTENT_LEFT` through `_CONTENT_RIGHT`) and fixed curve y-axis range.
- Do not fabricate ticks or force a theoretical 51-tick grid.

---

### Task 1: Add failing shared-guide assertions

**Files:**
- Modify: `tests/test_standardization_review_figures.py`

**Interfaces:**
- Consumes: `render_review_figure` metadata.
- Produces: assertions for one shared screen-coordinate list and equal panel boundaries.

- [x] **Step 1: Add the failing test.**

```python
def test_review_exposes_one_shared_marker_geometry():
    rotated = np.full((50, 100, 3), 160, dtype=np.uint8)
    standardization = _standardization(width=100)
    standardization['ticks'] = [
        {'x': 12.0, 'x_local': 12.0, 'x_projection': 12.0},
        {'x': 28.0, 'x_local': 28.0, 'x_projection': 28.0},
        {'x': 44.0, 'x_local': 44.0, 'x_projection': 44.0},
        {'x': 60.0, 'x_local': 60.0, 'x_projection': 60.0},
    ]
    _image, metadata = render_review_figure(
        rotated, _split_result(), 'main',
        {'standardization': standardization}, '30.00.jpg'
    )

    assert metadata['image_content_x'] == metadata['curve_content_x']
    assert metadata['shared_tick_screen_x'] == metadata['tick_screen_x_image']
    assert metadata['shared_tick_screen_x'] == metadata['tick_screen_x_curve']
    assert metadata['shared_zero_screen_x'] == metadata['zero_screen_x_image']
    assert metadata['shared_zero_screen_x'] == metadata['zero_screen_x_curve']
```

- [x] **Step 2: Run the focused test and confirm the new fields fail.**

Run: `python -m pytest tests/test_standardization_review_figures.py::test_review_exposes_one_shared_marker_geometry -q`

Expected: FAIL with a missing `shared_tick_screen_x` metadata key.

---

### Task 2: Centralize marker geometry and draw continuous guides

**Files:**
- Modify: `tools/export_standardization_review_figures.py:210-400`

**Interfaces:**
- Consumes: one display domain, accepted local tick x values, optional local zero x.
- Produces: `shared_tick_screen_x`, `shared_zero_screen_x`, and a figure whose guides use the same screen columns in both panels.

- [x] **Step 1: Add a shared geometry helper.**

```python
def _shared_marker_geometry(start, end, tick_xs, zero_x):
    tick_screen_x = [
        _map_content_x(x, start, end)
        for x in tick_xs if start <= x < end
    ]
    zero_screen_x = (
        _map_content_x(zero_x, start, end)
        if zero_x is not None and start <= zero_x < end else None
    )
    return tick_screen_x, zero_screen_x
```

Use this helper before rendering either panel. Pass the resulting screen x values to both panel renderers instead of recalculating them independently.

- [x] **Step 2: Keep image and curve source spans exact.**

Retain `crop = rotated[y1:y2, image_x1:image_x2]` and `curve[start:end]`; assert `image_x2-image_x1 == end-start` before drawing. Resize only the complete image crop into the shared content rectangle, without changing marker coordinates.

- [x] **Step 3: Draw shared guides through the separator.**

After stacking the panels, draw a thin muted guide at each shared tick x from the upper marker baseline through the lower panel. Draw the zero guide in red with the existing thickness. These guides are display-only and must not alter the source crop or curve.

- [x] **Step 4: Record the shared geometry.**

Add the following metadata fields:

```python
'shared_tick_screen_x': list(shared_tick_screen_x),
'shared_zero_screen_x': shared_zero_screen_x,
'shared_content_x': [_CONTENT_LEFT, _CONTENT_RIGHT],
```

Keep existing `tick_screen_x_image`, `tick_screen_x_curve`, `zero_screen_x_image`, and `zero_screen_x_curve` for backward compatibility.

---

### Task 3: Verify and re-export the audit figures

**Files:**
- Test: `tests/test_standardization_review_figures.py`
- Create: `debug_tupian_standardization_review_20260814_shared_x/`

**Interfaces:**
- Consumes: the corrected exporter and the five review samples.
- Produces: ten PNG audit figures and a summary JSON with shared geometry metadata.

- [x] **Step 1: Run focused tests.**

Run: `python -m pytest tests/test_standardization_review_figures.py -q`

Expected: all tests pass, including equal image/curve marker lists and shared boundaries.

- [x] **Step 2: Run the regression set.**

Run: `python -m pytest tests/test_standardization_visual_exports.py tests/test_vernier_standard_curve.py tests/test_vernier_standardization_contract.py -q`

Expected: all tests pass; only known Windows pytest-cache permission warnings may remain.

- [x] **Step 3: Export the five sample pairs.**

Run:

```powershell
python tools/export_standardization_review_figures.py `
  --input-dir tupian `
  --output-dir debug_tupian_standardization_review_20260814_shared_x `
  --image 30.00.jpg `
  --image 72.52.jpg `
  --image 90.14.jpg `
  --image 120.60.jpg `
  --image 140.00.jpg
```

- [x] **Step 4: Mechanically audit the exported metadata.**

For every main/vernier figure, assert `shared_content_x == image_content_x == curve_content_x`, `shared_tick_screen_x == tick_screen_x_image == tick_screen_x_curve`, and the analogous zero-line equality.
