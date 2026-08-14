# 游标尺谷底结构过滤 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 拒绝从图像边缘空白开始、或中间含大断裂的假游标谷底对，使零线回到真实游标刻线带的首条刻线。

**Architecture:** 保留现有完整游标带、双谷底范围、实测周期、候选去重和评分模型。在现有评分前加两个由图像投影直接计算的硬条件：每个谷底两侧必须都有刻线峰支撑，两个谷底之间不得有超过阈值的低响应断裂。通过结构过滤后仍使用既有深度、周期、间距和连通域评分选择最佳对。

**Tech Stack:** Python 3、NumPy、OpenCV、项目现有裸函数回归测试。

## Global Constraints

- 生产逻辑不得使用文件名。
- 不固定游标刻线数量，不补线，不拟合理论曲线或网格。
- 不改 ROI、区域分离、主尺 OCR 或后续对齐逻辑。
- 保留“完整游标带 -> 两个谷底 -> 范围内第一条真实刻线为零线”的主结构。
- 保持 `40.30`、`72.52`、`74.56`、`80.70`、`100.60` 当前可接受的读数。

---

### Task 1: 为谷底结构条件建立失败测试

**Files:**
- Modify: `tests/test_vernier_valley_regressions.py`
- Modify: `caliper/vernier_scale.py:743-755`

**Interfaces:**
- Produces `_valley_has_two_sided_peak_support(proj_norm, valley, observed_period, tick_threshold, near_periods, far_periods) -> bool`.
- Produces `_pair_has_no_large_internal_valley(smooth, left, right, valley_threshold, observed_period, max_break_periods) -> bool`.

- [ ] **Step 1: Write failing pure-signal tests**

Add this import and tests to `tests/test_vernier_valley_regressions.py`:

```python
import numpy as np

from caliper.vernier_scale import (
    _pair_has_no_large_internal_valley,
    _suppress_duplicate_candidates,
    _valley_has_two_sided_peak_support,
)


def test_edge_valley_without_outer_peak_is_rejected():
    projection = np.zeros(80, dtype=float)
    projection[12:20] = 0.9
    projection[25:33] = 0.9
    assert not _valley_has_two_sided_peak_support(
        projection, (0, 6), 8.0, 0.5, 1.0, 2.0
    )


def test_valley_between_two_peak_bands_is_supported():
    projection = np.zeros(96, dtype=float)
    projection[8:16] = 0.9
    projection[32:40] = 0.9
    assert _valley_has_two_sided_peak_support(
        projection, (20, 24), 8.0, 0.5, 1.0, 2.0
    )


def test_large_internal_low_response_break_is_rejected():
    smooth = np.ones(120, dtype=float) * 0.8
    smooth[48:64] = 0.05
    assert not _pair_has_no_large_internal_valley(
        smooth, (8, 16), (104, 112), 0.2, 8.0, 1.5
    )


def test_short_intertick_low_response_does_not_break_pair():
    smooth = np.ones(120, dtype=float) * 0.8
    smooth[52:58] = 0.05
    assert _pair_has_no_large_internal_valley(
        smooth, (8, 16), (104, 112), 0.2, 8.0, 1.5
    )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
@'
from tests import test_vernier_valley_regressions as t
t.test_edge_valley_without_outer_peak_is_rejected()
t.test_valley_between_two_peak_bands_is_supported()
t.test_large_internal_low_response_break_is_rejected()
t.test_short_intertick_low_response_does_not_break_pair()
'@ | python -
```

Expected: import error because the two helpers do not exist yet.

- [ ] **Step 3: Implement the smallest pure helpers**

Insert after `_valley_segment_quality()` in `caliper/vernier_scale.py`:

```python
def _valley_has_two_sided_peak_support(proj_norm, valley, observed_period,
                                       tick_threshold, near_periods, far_periods):
    if proj_norm is None or observed_period < 3.0:
        return False
    values = np.asarray(proj_norm, dtype=float)
    start, end = int(valley[0]), int(valley[1])
    near = max(1, int(round(observed_period * near_periods)))
    far = max(near + 1, int(round(observed_period * far_periods)))
    left_start, left_end = start - far, start - near
    right_start, right_end = end + near, end + far
    if left_start < 0 or right_end > values.size:
        return False
    return (float(np.max(values[left_start:left_end])) >= tick_threshold
            and float(np.max(values[right_start:right_end])) >= tick_threshold)


def _pair_has_no_large_internal_valley(smooth, left, right, valley_threshold,
                                       observed_period, max_break_periods):
    if smooth is None or observed_period < 3.0:
        return False
    start = max(0, int(left[1]))
    end = min(len(smooth), int(right[0]))
    if end <= start:
        return False
    low_segments = _contiguous_true_segments(
        np.asarray(smooth[start:end]) <= valley_threshold, min_len=1,
    )
    max_break = max(1, int(round(observed_period * max_break_periods)))
    return all(segment_end - segment_start < max_break
               for segment_start, segment_end in low_segments)
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: all four tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add caliper/vernier_scale.py tests/test_vernier_valley_regressions.py
git commit -m "test: cover vernier valley structure predicates"
```

### Task 2: 在现有评分前过滤不合格谷底对

**Files:**
- Modify: `caliper/config.py:281-292`
- Modify: `caliper/vernier_scale.py:847-918`
- Modify: `tests/test_vernier_valley_regressions.py`

**Interfaces:**
- Consumes Task 1 helpers and existing `proj_norm`、`signal`、`h_th`、`valley_th`、`left`、`right`、`observed_period`.
- Produces only structurally valid `pair_scores`; each item records `left_valley_supported`, `right_valley_supported`, and `internal_continuity`.

- [ ] **Step 1: Write the failing end-to-end regression**

Append this test:

```python
def test_zero_error_samples_do_not_select_the_left_edge_as_vernier_band():
    minimum_left_starts = {
        '40.00.jpg': 2000,
        '90.14.jpg': 2000,
        '71.50.jpg': 1500,
        '100.74.jpg': 500,
        '70.96.jpg': 900,
    }
    for filename, minimum_left_start in minimum_left_starts.items():
        vernier = _run(filename)
        detection = vernier['vernier_band_detection']
        left, _right, _middle = detection['selected_valley_pair']
        assert left[0] >= minimum_left_start, filename
        assert vernier['zero_x'] >= minimum_left_start, filename
        assert len(vernier['vernier_ticks']) > 0, filename
```

- [ ] **Step 2: Run regression and verify RED**

Run:

```powershell
@'
from tests import test_vernier_valley_regressions as t
t.test_zero_error_samples_do_not_select_the_left_edge_as_vernier_band()
'@ | python -
```

Expected: failure on `40.00.jpg`, whose selected left valley starts at `0`.

- [ ] **Step 3: Add configuration and gate the pair**

Add to `VernierScaleConfig` in `caliper/config.py`:

```python
    valley_peak_support_near_periods: float = 1.0
    valley_peak_support_far_periods: float = 2.0
    valley_internal_break_periods: float = 1.5
```

Immediately after `h_th` is computed in the nested pair loop of `_select_vernier_roi_from_valleys()`, add:

```python
            left_valley_supported = _valley_has_two_sided_peak_support(
                proj_norm, left, observed_period, h_th,
                config.vernier_scale.valley_peak_support_near_periods,
                config.vernier_scale.valley_peak_support_far_periods,
            )
            right_valley_supported = _valley_has_two_sided_peak_support(
                proj_norm, right, observed_period, h_th,
                config.vernier_scale.valley_peak_support_near_periods,
                config.vernier_scale.valley_peak_support_far_periods,
            )
            internal_continuity = _pair_has_no_large_internal_valley(
                signal, left, right, valley_th, observed_period,
                config.vernier_scale.valley_internal_break_periods,
            )
            if not (left_valley_supported and right_valley_supported
                    and internal_continuity):
                continue
```

Store the three booleans plus `structure_valid=True` in the appended pair-score dictionary. Do not change the existing total-score formula.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
@'
from tests import test_vernier_valley_regressions as t
t.test_edge_valley_without_outer_peak_is_rejected()
t.test_valley_between_two_peak_bands_is_supported()
t.test_large_internal_low_response_break_is_rejected()
t.test_short_intertick_low_response_does_not_break_pair()
t.test_zero_error_samples_do_not_select_the_left_edge_as_vernier_band()
t.test_2420_keeps_the_leftmost_observed_vernier_tick_as_zero()
t.test_11050_and_14000_fall_back_to_a_structurally_valid_valley_pair()
'@ | python -
```

Expected: all assertions pass; the five target images no longer choose the erroneous left-side range.

- [ ] **Step 5: Commit Task 2**

```powershell
git add caliper/config.py caliper/vernier_scale.py tests/test_vernier_valley_regressions.py
git commit -m "fix: require structural vernier valley boundaries"
```

### Task 3: Protect Current Successes and Export the Evidence

**Files:**
- Modify: `tests/test_vernier_top_stroke_split.py`
- Modify: `tools/export_vernier_valley_diagnostics.py:155-190`

**Interfaces:**
- Consumes the `pair_scores` structure fields from Task 2.
- Produces JSON diagnostics showing the selected pair structure state.

- [ ] **Step 1: Write a protected-reading regression**

Append to `tests/test_vernier_top_stroke_split.py`:

```python
def test_valley_structure_filter_preserves_current_readings():
    expected = {
        '40.30.jpg': 40.30,
        '72.52.jpg': 72.52,
        '74.56.jpg': 74.56,
        '80.70.jpg': 80.70,
        '100.60.jpg': 100.60,
    }
    for filename, target in expected.items():
        image = cv2.imread(str(Path('tupian') / filename))
        pipeline = CaliperPipeline(fast_mode=True)
        result = pipeline.run(image)
        assert abs(result.total - target) <= 0.10, filename
```

- [ ] **Step 2: Run the protected-reading regression**

Run the following before and after Task 2; it must pass both times:

```powershell
@'
from tests import test_vernier_top_stroke_split as t
t.test_valley_structure_filter_preserves_current_readings()
'@ | python -
```

- [ ] **Step 3: Extend selected-pair diagnostics**

In `tools/export_vernier_valley_diagnostics.py`, find the item in `detection.get('pair_scores', [])` whose `left` and `right` equal `detection.get('selected_valley_pair')[:2]`. Set `selected_pair_score` to that item or `{}`. Add these fields to each report row:

```python
            'selected_left_valley_supported': selected_pair_score.get('left_valley_supported'),
            'selected_right_valley_supported': selected_pair_score.get('right_valley_supported'),
            'selected_internal_continuity': selected_pair_score.get('internal_continuity'),
            'pair_scores': detection.get('pair_scores', []),
```

- [ ] **Step 4: Run full validation and emit comparison images**

Run:

```powershell
@'
from tests import test_vernier_top_stroke_split as top
from tests import test_vernier_valley_regressions as valley
top.test_7252_digit_only_peak_has_no_top_stroke()
top.test_7252_zero_tick_is_split_above_the_attached_digit()
top.test_4030_zero_tick_is_split_above_its_attached_digit()
top.test_7252_zero_selection_skips_the_digit_only_projection_peak()
top.test_8070_keeps_its_existing_fraction_after_leading_digit_filtering()
top.test_10060_keeps_its_existing_fraction_after_leading_digit_filtering()
top.test_valley_structure_filter_preserves_current_readings()
valley.test_duplicate_suppression_does_not_chain_across_separate_ticks()
valley.test_2420_keeps_the_leftmost_observed_vernier_tick_as_zero()
valley.test_30_and_33_keep_observed_valley_bounded_vernier_evidence()
valley.test_11050_and_14000_fall_back_to_a_structurally_valid_valley_pair()
valley.test_zero_error_samples_do_not_select_the_left_edge_as_vernier_band()
print('focused vernier regressions: PASS')
'@ | python -
python tools\evaluate_all_pipeline.py
python tools\export_vernier_valley_diagnostics.py 40.00.jpg 90.14.jpg 71.50.jpg 100.74.jpg 70.96.jpg --output-dir debug_tupian_vernier_valleys_structure_20260722
git diff --check
```

Expected: focused regression functions pass, full `evaluation.json` is regenerated, and exported purple ranges are bounded by supported valleys instead of an image edge.

- [ ] **Step 5: Commit Task 3**

```powershell
git add tools/export_vernier_valley_diagnostics.py tests/test_vernier_top_stroke_split.py
git commit -m "docs: expose vernier valley structure diagnostics"
```
