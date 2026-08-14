# Vernier Standard Curve Clustering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a detailed-mode-only, length-clustered standard response curve to the existing vernier tick page without changing any recognition decision or reading.

**Architecture:** A pure helper in `caliper/vernier_scale.py` will convert final observed tick lengths into a fixed-width Gaussian response and diagnostics. The existing `_draw_vernier_ticks_on_band` will render that response in an additional panel; `recognize_vernier_scale` remains unchanged except for receiving the resulting visual image as before.

**Tech Stack:** Python 3.12, NumPy, OpenCV, pytest.

## Global Constraints

- Only final accepted `vernier_ticks` may enter the standard response; rejected candidates, expected grids, file names, and synthetic ticks are prohibited.
- The response must be display-only: it must not change valley scoring, zero selection, alignment, `vernier_reading`, `zero_x`, or `CaliperResult.total`.
- Do not add third-party dependencies; deterministic one-dimensional two-cluster iteration uses NumPy only.
- Keep the existing “游标刻度线” GUI tab; do not add a tab and do not generate detailed panels in fast mode.
- No commit is part of this task because the shared worktree contains unrelated uncommitted changes.

---

### Task 1: Add failing tests for length clustering and display-only regression

**Files:**
- Modify: `tests/test_vernier_debug_panel.py`
- Create: `tests/test_vernier_standard_curve.py`
- Reference: `caliper/vernier_scale.py:260-420`, `caliper/pipeline.py:250-285`

**Interfaces:**
- Consumes: a new `_build_length_clustered_standard_response(width: int, ticks: list[dict], x_offset: int) -> tuple[np.ndarray, dict]`.
- Produces: tests that specify cluster levels and prove the detailed panel does not alter a real image result.

- [ ] **Step 1: Write the failing unit tests for two clusters and single-cluster fallback**

```python
from caliper.vernier_scale import _build_length_clustered_standard_response


def _ticks(lengths):
    return [
        {'x_projection': 10 + index * 10, 'length': length}
        for index, length in enumerate(lengths)
    ]


def test_length_clustered_response_marks_separated_lengths_as_two_clusters():
    response, info = _build_length_clustered_standard_response(
        100, _ticks([10, 11, 10, 11, 20, 21, 20, 21]), 0
    )

    assert info['mode'] == 'two_length_clusters'
    assert info['cluster_counts'] == [4, 4]
    assert response[10] == 1.0
    assert response[50] == 1.5


def test_length_clustered_response_rejects_nearly_uniform_lengths():
    response, info = _build_length_clustered_standard_response(
        100, _ticks([10, 10, 11, 10, 11, 10]), 0
    )

    assert info['mode'] == 'single_length_cluster'
    assert set(response[10 + index * 10] for index in range(6)) == {1.0}


def test_length_clustered_response_rejects_too_few_ticks():
    _response, info = _build_length_clustered_standard_response(
        100, _ticks([10, 20, 10, 20, 10]), 0
    )

    assert info['mode'] == 'single_length_cluster'
```

- [ ] **Step 2: Write the failing detailed-mode integration assertion**

Add to `tests/test_vernier_debug_panel.py`:

```python
def test_vernier_detail_panel_has_length_standard_response_without_reading_change():
    image = _read(Path('tupian') / '30.00.jpg')
    detailed = CaliperPipeline(fast_mode=False)
    detailed_result = detailed.run(image)
    fast = CaliperPipeline(fast_mode=True)
    fast_result = fast.run(image)

    panel = detailed.debug_images['4b_游标刻度线']
    assert panel.shape[0] > 1579
    assert detailed_result.total == fast_result.total
    assert detailed.step_results['vernier']['zero_x'] == pytest.approx(
        fast.step_results['vernier']['zero_x']
    )
```

- [ ] **Step 3: Run tests and confirm the expected RED failure**

Run: `python -m pytest -q tests/test_vernier_standard_curve.py tests/test_vernier_debug_panel.py`

Expected: import failure for `_build_length_clustered_standard_response`. After Task 2 makes the helper importable, rerun the UI test and confirm its `panel.shape[0] > 1579` assertion fails until Task 3 inserts the panel.

### Task 2: Implement deterministic length clustering and standard response

**Files:**
- Modify: `caliper/vernier_scale.py:260-420`
- Test: `tests/test_vernier_standard_curve.py`

**Interfaces:**
- Consumes: `width`, accepted ticks with `x_projection` and finite positive `length`, and the local global-x offset `x_offset`.
- Produces: `(response, info)`, where `response.shape == (width,)` and `info` has `mode`, `cluster_centers`, and `cluster_counts`.

- [ ] **Step 1: Add the pure helper before `_draw_vernier_ticks_on_band`**

```python
def _build_length_clustered_standard_response(width: int,
                                              ticks: List[dict],
                                              x_offset: int) -> tuple[np.ndarray, dict]:
    response = np.zeros(max(0, int(width)), dtype=float)
    valid = []
    for tick in ticks:
        try:
            length = float(tick.get('length', 0.0))
            local_x = int(round(
                float(tick.get('x_projection', tick.get('x', 0))) - x_offset
            ))
        except (TypeError, ValueError):
            continue
        if np.isfinite(length) and length > 0.0:
            valid.append((local_x, length))

    info = {
        'mode': 'single_length_cluster',
        'cluster_centers': [],
        'cluster_counts': [],
    }
    if len(valid) >= 6:
        lengths = np.asarray([length for _x, length in valid], dtype=float)
        lo, hi = np.percentile(lengths, [5, 95])
        clipped = np.clip(lengths, lo, hi)
        centers = np.percentile(clipped, [25, 75]).astype(float)
        if abs(float(centers[1] - centers[0])) > 1e-9:
            for _ in range(20):
                labels = (np.abs(clipped - centers[1]) <
                          np.abs(clipped - centers[0])).astype(int)
                counts = np.bincount(labels, minlength=2)
                if np.any(counts == 0):
                    break
                updated = np.asarray([
                    np.mean(clipped[labels == 0]),
                    np.mean(clipped[labels == 1]),
                ])
                if float(np.max(np.abs(updated - centers))) < 1e-3:
                    centers = updated
                    break
                centers = updated
            labels = (np.abs(clipped - centers[1]) <
                      np.abs(clipped - centers[0])).astype(int)
            counts = np.bincount(labels, minlength=2)
            order = np.argsort(centers)
            centers = centers[order]
            labels = np.where(labels == order[0], 0, 1)
            counts = np.bincount(labels, minlength=2)
            if (
                min(counts) >= 3
                and centers[1] - centers[0] >= max(2.0, 0.20 * np.median(clipped))
            ):
                info = {
                    'mode': 'two_length_clusters',
                    'cluster_centers': [float(centers[0]), float(centers[1])],
                    'cluster_counts': [int(counts[0]), int(counts[1])],
                }
            else:
                labels = np.zeros(len(valid), dtype=int)
        else:
            labels = np.zeros(len(valid), dtype=int)
    else:
        labels = np.zeros(len(valid), dtype=int)

    for (local_x, _length), label in zip(valid, labels):
        amplitude = 1.5 if info['mode'] == 'two_length_clusters' and label == 1 else 1.0
        for offset in range(-3, 4):
            x = local_x + offset
            if 0 <= x < response.size:
                response[x] = max(
                    response[x],
                    amplitude * np.exp(-0.5 * (offset / 1.1) ** 2),
                )
    return response, info
```

Use the exact acceptance condition:

```python
separated = (
    min(cluster_counts) >= 3
    and centers[1] - centers[0] >= max(2.0, 0.20 * np.median(clipped_lengths))
)
```

For every valid final tick, write a seven-point Gaussian centered at its local x coordinate with `sigma=1.1`; amplitudes are `1.0` in single-cluster mode, otherwise `1.0` for the lower-center cluster and `1.5` for the upper-center cluster. Use `np.maximum` for overlap.

- [ ] **Step 2: Run the pure unit test and confirm GREEN**

Run: `python -m pytest -q tests/test_vernier_standard_curve.py`

Expected: three tests pass and no image file is written.

### Task 3: Render the standard panel without affecting recognition data

**Files:**
- Modify: `caliper/vernier_scale.py:260-340`
- Modify: `tests/test_vernier_debug_panel.py`
- Test: `tests/test_vernier_standard_curve.py`, `tests/test_vernier_debug_panel.py`

**Interfaces:**
- Consumes: `(response, info)` from Task 2 and final `vernier_ticks` already passed to `_draw_vernier_ticks_on_band`.
- Produces: one additional visual-only panel inside the existing `vis_ticks` image.

- [ ] **Step 1: Build and insert the panel after component-bottom support**

```python
standard_response, cluster_info = _build_length_clustered_standard_response(
    band_w, vernier_ticks, x1
)
mode = cluster_info['mode'].replace('_', ' ')
title = (
    'Length-normalized standard response '
    f"({mode}; short=1.0, long=1.5)"
)
standard_panel = _draw_vernier_projection_panel(
    standard_response, band_w, title, (255, 190, 60), candidates,
    value_max=1.5,
)
```

`_draw_vernier_projection_panel` already accepts `value_max`; pass `value_max=1.5` so the standard response is not per-panel normalized and the existing `1.0`/`1.5` reference levels are visible.

Stack panels in this exact order: narrow-band image, raw projection, component-bottom support, standard response. Do not save `cluster_info` into `band_detection`, `vernier_result`, or any result field.

- [ ] **Step 2: Run UI and unit regressions**

Run: `python -m pytest -q tests/test_vernier_standard_curve.py tests/test_vernier_debug_panel.py tests/test_alignment_ambiguity.py`

Expected: all tests pass.

- [ ] **Step 3: Run one real-image diagnostic and inspect it**

Run: `python -m pytest -q tests/test_vernier_debug_panel.py`

Then run the detailed pipeline for `30.00.jpg`, write `pipeline.debug_images['4b_游标刻度线']` to a PNG, and inspect it. Confirm it has the new title, green final-tick markers, and no blank panel.

### Task 4: Verify recognition invariance and document the diagnostic-only behaviour

**Files:**
- Modify: `README.md:400-450`
- Test: `tests/test_vernier_standard_curve.py`, `tests/test_vernier_debug_panel.py`

**Interfaces:**
- Consumes: visual-only implementation from Task 3.
- Produces: documentation that explains the curve as a cluster-derived display rather than an algorithmic decision signal.

- [ ] **Step 1: Add a concise UI diagnostic description**

Add under the “游标刻度线” debug-image description:

```markdown
长度标准化曲线只使用最终接受的游标刻线长度做一维两类聚类。
两簇分离不足时显示单类；它不参与谷底、零线、对齐或读数。
```

- [ ] **Step 2: Run full relevant verification**

Run: `python -m pytest -q tests/test_vernier_standard_curve.py tests/test_vernier_debug_panel.py tests/test_alignment_ambiguity.py`

Run: `git diff --check -- caliper/vernier_scale.py tests/test_vernier_standard_curve.py tests/test_vernier_debug_panel.py README.md`

Expected: all tests pass and no whitespace errors.
