# Vernier Tick Refinement Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure the per-tick local refinement coordinate is preserved and becomes the center used for final sub-pixel tick localization.

**Architecture:** Keep projection peaks as candidate recall evidence. For every accepted candidate, compute a local seam-side coordinate `x_refined`, persist it in the tick dictionary, and use it as the input center to the existing grayscale sub-pixel refiner. Candidate selection, connected-component support, valley selection, zero-line selection, and alignment algorithms remain unchanged.

**Tech Stack:** Python, NumPy, OpenCV, pytest.

## Global Constraints

- Do not use filename labels in production recognition.
- Do not add theoretical ticks or force a tick count.
- Do not turn connected-component support into a required acceptance condition.
- Preserve `x_projection` as the unmodified projection-candidate coordinate.
- Keep edits local to vernier tick construction and its tests.

---

### Task 1: Preserve and hand off the local refinement coordinate

**Files:**
- Modify: `caliper/vernier_scale.py:1836-1924`
- Modify: `tests/test_vernier_per_tick_correction.py`

**Interfaces:**
- Consumes: `_build_ticks_from_band_detection(band_detection, long_tick_factor=None) -> List[dict]`
- Produces: each returned tick contains `x_projection`, `x_refined`, `x_precise`, and `x`.

- [ ] **Step 1: Write the failing test**

```python
def test_tick_subpixel_refinement_uses_local_refined_center(monkeypatch):
    band = np.zeros((20, 30), dtype=np.uint8)
    band[:, 12] = 255
    gray_band = np.full((20, 30), 255, dtype=np.uint8)
    detection = {
        'band': band,
        'gray_band': gray_band,
        'band_y1': 0,
        'x1': 0,
        'expected_gap': 10.0,
        'tick_candidates': [{
            'x_projection': 10,
            'projection_strength': 1.0,
            'component_id': None,
            'component': None,
            'spacing_error': 0.0,
        }],
    }
    called_with = []

    monkeypatch.setattr(
        vernier_scale,
        '_refine_vernier_tick_from_band',
        lambda *_: {'x': 12.0, 'x_top': 12.0, 'x_bottom': 12.0,
                    'y_start': 0, 'y_end': 19, 'slope': 0.0},
    )
    monkeypatch.setattr(
        vernier_scale,
        'refine_tick_x_subpixel',
        lambda _gray, center, _y1, _y2: called_with.append(center) or center + 0.25,
    )

    ticks = vernier_scale._build_ticks_from_band_detection(detection)

    assert called_with == [12]
    assert ticks[0]['x_projection'] == 10
    assert ticks[0]['x_refined'] == pytest.approx(12.0)
    assert ticks[0]['x_precise'] == pytest.approx(12.25)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_vernier_per_tick_correction.py::test_tick_subpixel_refinement_uses_local_refined_center`

Expected: FAIL because the current implementation passes `10`, the projection candidate, to `refine_tick_x_subpixel`.

- [ ] **Step 3: Write minimal implementation**

```python
x_precise = refine_tick_x_subpixel(
    gray_band, int(round(x_refined)), ref_y1, ref_y2
) if gray_band is not None else x_refined

tick = {
    'x_projection': x + x_offset,
    'x_refined': x_refined + x_offset,
    'x_precise': x_precise + x_offset,
    'x': int(round(x_precise)) + x_offset,
}
```

Keep the pre-existing location and length extraction unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_vernier_per_tick_correction.py::test_tick_subpixel_refinement_uses_local_refined_center`

Expected: PASS.

- [ ] **Step 5: Run focused regressions**

Run: `python -m pytest -q tests/test_vernier_per_tick_correction.py tests/test_vernier_debug_panel.py tests/test_vernier_valley_regressions.py tests/test_vernier_top_stroke_split.py tests/test_vernier_standard_curve.py tests/test_alignment_ambiguity.py`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add caliper/vernier_scale.py tests/test_vernier_per_tick_correction.py docs/superpowers/specs/2026-07-30-vernier-tick-refinement-handoff-design.md docs/superpowers/plans/2026-07-30-vernier-tick-refinement-handoff.md
git commit -m "fix: hand off refined vernier tick center"
```
