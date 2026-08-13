# Scale Standardization Curves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为主尺和游标尺建立统一、可追溯的标准化曲线结果，在详细模式中展示原始投影、结构支撑和归一化响应，同时保证正式刻线与最终读数完全不变。

**Architecture:** 新增一个只负责结果契约和曲线数组规整的 `caliper/standardization.py`。主尺和游标尺继续在各自模块中计算图像证据和分类，只把结果组装成统一字典；详细模式把同一份字典传给绘图函数，快速模式不计算曲线。标准化结果只挂在 `step_results` 和游标检测诊断对象上，不进入 `merge_readings()` 的正式输入。

**Tech Stack:** Python 3, NumPy, OpenCV, pytest, Tkinter 现有动态调试页。

## Global Constraints

- 不强制拟合或补足 51 条游标刻线。
- 不按理论网格生成没有图像前景支持的刻线。
- 不使用图片文件名、期望读数或人工真值修正曲线或读数。
- 不改写 `main_ticks`、`vernier_ticks`、`zero_x`、对齐结果、`vernier_reading` 或 `total`。
- 快速模式不得因标准化曲线增加额外计算或调试图。
- 保留 `_standardize_tick_response()` 和 `_build_length_clustered_standard_response()` 的现有返回形式，已有调用和测试继续有效。
- 所有新增字段只作为诊断数据，`quality` 不是概率，也不是测量误差上限。

---

### Task 1: 建立统一标准化结果契约

**Files:**
- Create: `caliper/standardization.py`
- Create: `tests/test_standardization_contract.py`
- Modify: `caliper/__init__.py` only if the new helper is intentionally exposed; do not expose it in the public API by default.

**Interfaces:**
- Produces: `empty_standardization(width, x_offset=0) -> dict` and `build_standardization_result(width, x_offset, raw_projection, support, normalized_response, tick_records, classification) -> dict`.
- Consumes: NumPy arrays or array-like values and already computed observed tick records from the scale modules.

- [ ] **Step 1: Write failing contract tests**

```python
import numpy as np

from caliper.standardization import (
    build_standardization_result,
    empty_standardization,
)


def test_empty_standardization_has_three_width_aligned_curves():
    result = empty_standardization(12, x_offset=37)

    assert result['version'] == 1
    assert result['width'] == 12
    assert result['x_offset'] == 37
    assert set(result['curves']) == {
        'raw_projection', 'support', 'normalized_response'
    }
    assert all(value.shape == (12,) for value in result['curves'].values())
    assert result['ticks'] == []
    assert result['classification']['mode'] == 'unknown'


def test_builder_sanitizes_curves_and_keeps_tick_evidence():
    result = build_standardization_result(
        width=5,
        x_offset=10,
        raw_projection=[0, 1, 2, 3, 4, 99],
        support=[1, 2, 3],
        normalized_response=[0, 1, 0, 0, 0],
        tick_records=[{
            'x': 2,
            'x_projection': 2,
            'measured_length': 14,
            'support_value': 3,
            'normalized_value': 1.0,
            'class': 'short',
            'quality': 0.8,
        }],
        classification={'mode': 'single', 'centers': [14], 'counts': [1]},
    )

    assert result['curves']['raw_projection'].shape == (5,)
    assert result['curves']['support'].shape == (5,)
    assert result['curves']['normalized_response'].shape == (5,)
    assert result['ticks'][0]['x'] == 2.0
    assert result['classification']['mode'] == 'single'


def test_builder_replaces_nonfinite_curve_values_with_zero():
    result = build_standardization_result(
        width=3,
        x_offset=0,
        raw_projection=[np.nan, np.inf, 1],
        support=None,
        normalized_response=None,
        tick_records=[],
        classification=None,
    )

    assert np.array_equal(result['curves']['raw_projection'], [0.0, 0.0, 1.0])
    assert np.array_equal(result['curves']['support'], [0.0, 0.0, 0.0])
    assert result['classification']['mode'] == 'unknown'
```

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run:

```powershell
python -m pytest -q tests/test_standardization_contract.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'caliper.standardization'`.

- [ ] **Step 3: Implement the minimal contract module**

Implement the following behavior in `caliper/standardization.py`:

```python
from __future__ import annotations

import numpy as np


def _curve(signal, width: int) -> np.ndarray:
    out = np.zeros(max(0, int(width)), dtype=float)
    if out.size == 0 or signal is None:
        return out
    values = np.asarray(signal, dtype=float).reshape(-1)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    out[:min(out.size, values.size)] = values[:out.size]
    return out


def empty_standardization(width: int, x_offset: int = 0) -> dict:
    width = max(0, int(width))
    return {
        'version': 1,
        'width': width,
        'x_offset': int(x_offset),
        'curves': {
            'raw_projection': np.zeros(width, dtype=float),
            'support': np.zeros(width, dtype=float),
            'normalized_response': np.zeros(width, dtype=float),
        },
        'ticks': [],
        'classification': {
            'mode': 'unknown',
            'centers': [],
            'counts': [],
            'separation': 0.0,
            'threshold': None,
        },
    }


def build_standardization_result(
    width: int,
    x_offset: int,
    raw_projection,
    support,
    normalized_response,
    tick_records: list[dict],
    classification: dict | None,
) -> dict:
    result = empty_standardization(width, x_offset)
    result['curves'] = {
        'raw_projection': _curve(raw_projection, result['width']),
        'support': _curve(support, result['width']),
        'normalized_response': _curve(
            normalized_response, result['width']
        ),
    }
    result['ticks'] = [dict(record) for record in (tick_records or [])]
    if classification:
        result['classification'].update(dict(classification))
    return result
```

Do not add serialization, UI state, or formal-reading logic to this module.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```powershell
python -m pytest -q tests/test_standardization_contract.py
```

Expected: PASS.

- [ ] **Step 5: Run `git diff --check` and commit the contract**

```powershell
git diff --check
git add caliper/standardization.py tests/test_standardization_contract.py
git commit -m "feat: add standardization curve result contract"
```

### Task 2: 接入主尺标准化曲线

**Files:**
- Modify: `caliper/main_scale.py:recognize_main_scale`, `_draw_main_ticks`, `_empty_main_result`
- Create: `tests/test_main_standardization.py`

**Interfaces:**
- Consumes: `main_ticks`, `vproj_norm`, `_seam_anchored_support(binary, band_y1, band_y2)`.
- Produces: `main_result['standardization']`, or `None` when `make_debug=False`.
- Formal behavior preserved: `main_ticks`, `main_gap`, and `main_digits` keep their current values.

- [ ] **Step 1: Write failing main-scale integration tests**

```python
import cv2
import numpy as np

from caliper.main_scale import recognize_main_scale


def _main_region():
    gray = np.full((40, 80), 220, dtype=np.uint8)
    binary = np.zeros_like(gray)
    for x in (10, 20, 30, 40, 50, 60):
        binary[5:35, x] = 255
    return {
        'image': gray,
        'binary': binary,
        'tick_band': (5, 35),
        'y_offset': 0,
        'height': 40,
    }


def test_detailed_main_result_contains_width_aligned_standardization():
    result = recognize_main_scale(_main_region(), make_debug=True)

    standard = result['standardization']
    assert standard['width'] == 80
    assert standard['x_offset'] == 0
    assert standard['curves']['raw_projection'].shape == (80,)
    assert standard['curves']['support'].shape == (80,)
    assert standard['curves']['normalized_response'].shape == (80,)
    assert len(standard['ticks']) == len(result['main_ticks'])


def test_fast_main_result_does_not_compute_standardization():
    result = recognize_main_scale(_main_region(), make_debug=False)
    assert result['standardization'] is None
```

- [ ] **Step 2: Run the focused tests and verify the expected failure**

```powershell
python -m pytest -q tests/test_main_standardization.py
```

Expected: FAIL because `recognize_main_scale()` currently has no `standardization` key.

- [ ] **Step 3: Add the main-scale builder without changing detection**

Add a private builder in `caliper/main_scale.py` with this interface:

```python
def _build_main_standardization(
    width: int,
    vproj_norm: np.ndarray,
    support: np.ndarray,
    ticks: list[dict],
) -> dict:
    """Build display-only main-scale evidence from accepted ticks."""
```

The builder must:

1. Compute each tick's support value as the maximum support in `x_projection ± 2`.
2. Reuse `_standardize_tick_response(width, ticks, support)` for the response array.
3. Preserve the existing p75/p85 threshold behavior for displayed amplitudes.
4. Set `class='short'` or `class='long'` only when the support values are finite and at least three values support a stable split; otherwise use `class='unknown'` and `classification.mode='unknown'`.
5. Set `quality` to a bounded diagnostic ratio based on the tick support and the median positive support; it must not be consumed by production recognition.
6. Call `build_standardization_result(width, 0, vproj_norm, support, response, records, classification)`.

The classification dictionary must include at least:

```python
{
    'mode': 'single' | 'two_clusters' | 'unknown',
    'centers': [float, ...],
    'counts': [int, ...],
    'separation': float,
    'threshold': float | None,
}
```

- [ ] **Step 4: Reuse the structured result in the main drawing function**

Change `_draw_main_ticks(...)` to accept `standardization=None`. Remove its duplicate local construction of `support` and `response` and read:

```python
curves = standardization['curves'] if standardization else {
    'support': _seam_anchored_support(binary, band_y1, band_y2),
    'normalized_response': np.zeros(w, dtype=float),
}
```

Keep the existing three-panel order and colors. Update only the normalized-panel title to include `classification.mode`, center values, and counts when available. Do not draw any candidate that is absent from `main_ticks`.

- [ ] **Step 5: Attach the result only in detailed mode and preserve empty output**

In `recognize_main_scale()` calculate:

```python
standardization = None
if make_debug:
    support = _seam_anchored_support(binary, band_y1, band_y2)
    standardization = _build_main_standardization(
        w, vproj_norm, support, main_ticks
    )
```

Pass it to `_draw_main_ticks(...)` and return `'standardization': standardization`. Update `_empty_main_result()` to include `'standardization': None` without changing any existing empty values.

- [ ] **Step 6: Run focused and existing research tests**

```powershell
python -m pytest -q tests/test_main_standardization.py tests/test_research_paths_preserved.py tests/test_main_tick_extent_recovery.py
```

Expected: PASS; `main_ticks` and `main_gap` assertions remain unchanged.

- [ ] **Step 7: Commit the main-scale integration**

```powershell
git add caliper/main_scale.py tests/test_main_standardization.py
git commit -m "feat: expose main scale standardization evidence"
```

### Task 3: 接入游标尺标准化曲线

**Files:**
- Modify: `caliper/vernier_scale.py:recognize_vernier_scale`, `_build_length_clustered_standard_response`, `_draw_vernier_ticks_on_band`, `_empty_vernier_result`
- Modify: `tests/test_vernier_standard_curve.py`
- Create: `tests/test_vernier_standardization_contract.py`

**Interfaces:**
- Consumes: `band_detection['proj_norm']`, `vernier_ticks`, `_component_bottom_response`, `x1`.
- Produces: `vernier_result['standardization']` and the same object at `vernier_result['vernier_band_detection']['standardization']` in detailed mode.
- Formal behavior preserved: `zero_x`, `vernier_reading`, `alignment_confidence`, and mapped tick list are unchanged.

- [ ] **Step 1: Add tests for canonical cluster metadata and attached curves**

```python
import cv2
import numpy as np
import pytest

from caliper.pipeline import CaliperPipeline
from caliper.vernier_scale import _build_length_clustered_standard_response


def test_cluster_info_keeps_legacy_keys_and_adds_canonical_aliases():
    _response, info = _build_length_clustered_standard_response(
        100,
        [{'x_projection': i * 10, 'length': value}
         for i, value in enumerate([10, 11, 10, 11, 20, 21, 20, 21])],
        0,
    )

    assert info['mode'] == 'two_length_clusters'
    assert info['classification_mode'] == 'two_clusters'
    assert info['centers'] == info['cluster_centers']
    assert info['counts'] == info['cluster_counts']
    assert info['separation'] > 0.0


def test_detailed_vernier_result_attaches_one_standardization_object():
    image = cv2.imread('tupian/30.00.jpg')
    assert image is not None
    pipeline = CaliperPipeline(fast_mode=False)
    result = pipeline.run(image)
    vernier = pipeline.step_results['vernier']
    standard = vernier['standardization']
    detection_standard = vernier['vernier_band_detection']['standardization']

    assert standard is detection_standard
    assert standard['curves']['raw_projection'].shape == (
        standard['width'],
    )
    assert len(standard['ticks']) == len(vernier['vernier_ticks'])
    assert result.total is not None


def test_fast_vernier_result_does_not_compute_standardization():
    image = cv2.imread('tupian/30.00.jpg')
    assert image is not None
    pipeline = CaliperPipeline(fast_mode=True)
    pipeline.run(image)
    assert pipeline.step_results['vernier']['standardization'] is None
```

- [ ] **Step 2: Run the focused tests and verify the expected failure**

```powershell
python -m pytest -q tests/test_vernier_standardization_contract.py
```

Expected: FAIL because canonical aliases and attached `standardization` are not present.

- [ ] **Step 3: Extend cluster metadata without changing cluster labels**

In `_build_length_clustered_standard_response()`, retain the existing keys:

```python
'mode': 'two_length_clusters' | 'single_length_cluster',
'cluster_centers': [...],
'cluster_counts': [...],
```

and add:

```python
'classification_mode': 'two_clusters' | 'single' | 'unknown',
'centers': list(cluster_centers),
'counts': list(cluster_counts),
'separation': float,
'threshold': None,
```

For a valid two-cluster result calculate `separation = (high - low) / max(low, 1.0)`. For single-cluster or insufficient data use `separation=0.0`, empty centers/counts where no stable estimate exists, and do not change the existing amplitude behavior or legacy `mode` values.

- [ ] **Step 4: Add a vernier structured-result builder**

Add this private function in `caliper/vernier_scale.py`:

```python
def _build_vernier_standardization(
    band_detection: dict,
    ticks: list[dict],
) -> dict:
    """Build display-only vernier evidence in the detection-band coordinates."""
```

The function must:

1. Read `x1`, `proj_norm`, and the detection-band width from `band_detection`.
2. Call `_component_bottom_response(width, ticks, x1)` for the support curve.
3. Call `_build_length_clustered_standard_response(width, ticks, x1)` for the normalized response and legacy-compatible cluster info.
4. Build one record per accepted tick using local x (`tick['x'] - x1`), local projection x, measured `length`, component support, normalized amplitude, class (`short`, `long`, or `unknown`) and bounded quality.
5. Call `build_standardization_result(width, x1, band_detection['proj_norm'], support, response, records, classification)`.

The returned curves must be display-only arrays; do not mutate `ticks` or `band_detection['tick_xs_local']`.

- [ ] **Step 5: Attach one object and reuse it in rendering**

After accepted `vernier_ticks` have been built and classified, but before zero-line selection, add:

```python
standardization = None
if make_debug:
    standardization = _build_vernier_standardization(
        band_detection, vernier_ticks
    )
    band_detection['standardization'] = standardization
```

Return `'standardization': standardization` from `recognize_vernier_scale()`. Update `_draw_vernier_ticks_on_band(..., standardization=None)` to consume this object for the support and normalized panels. Keep the current raw projection and panel order. Update the title to show canonical classification mode, centers, counts and separation, while retaining the current `single_length_cluster`/`two_length_clusters` meaning in the internal info.

Update `_empty_vernier_result(reason)` with `'standardization': None`. In fast mode do not insert a computed curve object into `band_detection`.

- [ ] **Step 6: Verify formal reading invariance**

```powershell
python -m pytest -q tests/test_vernier_standard_curve.py tests/test_vernier_standardization_contract.py tests/test_vernier_debug_panel.py tests/test_research_paths_preserved.py
```

Expected: PASS, including existing detailed/fast equality checks for `total` and `zero_x`.

- [ ] **Step 7: Commit the vernier integration**

```powershell
git add caliper/vernier_scale.py tests/test_vernier_standard_curve.py tests/test_vernier_standardization_contract.py
git commit -m "feat: expose vernier standardization curves"
```

### Task 4: 完善详细模式绘图和样例导出

**Files:**
- Modify: `caliper/main_scale.py` and `caliper/vernier_scale.py` only for labels/layout that consume the structured result.
- Create: `tools/export_standardization_samples.py`
- Create: `tests/test_standardization_visual_exports.py`
- Modify: `README.md` and `docs/项目代码说明书.md`

**Interfaces:**
- Consumes: `pipeline.step_results['main']['standardization']` and `pipeline.step_results['vernier']['standardization']`.
- Produces: detailed UI panels unchanged as one tab per scale; an offline sample directory containing PNG panels and a JSON summary.

- [ ] **Step 1: Add an export test before the script implementation**

```python
from pathlib import Path

from tools.export_standardization_samples import export_samples


def test_standardization_export_writes_panels_and_summary(tmp_path):
    export_samples(
        input_dir=Path('tupian'),
        output_dir=tmp_path,
        filenames=['30.00.jpg', '120.60.jpg'],
    )

    assert (tmp_path / '30.00_main_standardization.png').exists()
    assert (tmp_path / '30.00_vernier_standardization.png').exists()
    assert (tmp_path / 'standardization_summary.json').exists()
```

- [ ] **Step 2: Run the export test and verify the expected failure**

```powershell
python -m pytest -q tests/test_standardization_visual_exports.py
```

Expected: FAIL because the export module does not exist.

- [ ] **Step 3: Implement the offline exporter**

`tools/export_standardization_samples.py` must:

1. Read images with `np.fromfile` and `cv2.imdecode` so Chinese paths remain supported.
2. Run `CaliperPipeline(fast_mode=False)` for each requested image.
3. Save `pipeline.debug_images['3a_主尺刻度线']` and `pipeline.debug_images['4b_游标刻度线']` as PNG files using `cv2.imencode('.png')` and `tofile`.
4. Write a UTF-8 `standardization_summary.json` containing filename, reading, main classification, vernier classification, curve widths, and tick counts. Do not include filename truth as an input to the pipeline.
5. Expose `export_samples(input_dir: Path, output_dir: Path, filenames: list[str]) -> dict` for tests and a CLI with `--input-dir`, `--output-dir`, and repeated `--image` options.

- [ ] **Step 4: Keep the UI on the existing tabs**

Do not add a separate standardization tab. Verify the current dynamic tab order remains:

```text
3a_主尺刻度线 -> 4b_游标刻度线 -> 4c_游标对齐
```

The main and vernier panels should display their structured curves below the image. Make titles explicit about “观测投影/结构支撑/归一化响应” and show `single`, `two_clusters`, or `unknown` rather than implying a theoretical curve.

- [ ] **Step 5: Update documentation**

Add to `README.md` and `docs/项目代码说明书.md`:

- exact `standardization` field layout;
- coordinate rule: curve x is local, `x_offset` maps it to the rotated ROI;
- main support source and vernier component-bottom source;
- length-clustering conditions and fallback behavior;
- explicit statement that curves do not affect formal readings;
- exporter command:

```powershell
python tools/export_standardization_samples.py --input-dir tupian --output-dir debug_standardization_samples --image 30.00.jpg --image 120.60.jpg
```

- [ ] **Step 6: Run the export and inspect representative images**

```powershell
python tools/export_standardization_samples.py --input-dir tupian --output-dir debug_tupian_standardization_20260813 --image 30.00.jpg --image 120.60.jpg --image 72.52.jpg --image 130.70.jpg --image 40.20.jpg --image 140.00.jpg
```

Expected files: two scale panels per image plus `standardization_summary.json`. Inspect that the curves are below the source image, remain visible, and do not cover the source tick image with opaque boxes.

- [ ] **Step 7: Commit rendering, export and documentation**

```powershell
git add caliper/main_scale.py caliper/vernier_scale.py tools/export_standardization_samples.py tests/test_standardization_visual_exports.py README.md docs/项目代码说明书.md
git commit -m "feat: document and export scale standardization curves"
```

### Task 5: 全量回归与基线对比

**Files:**
- Modify: none unless a test exposes a contract regression.
- Read: `debug_tupian_batch_evaluation_20260813_research_audit_v2/evaluation.json`
- Generate: `debug_tupian_batch_evaluation_20260813_standardization/evaluation.json`, `.csv`, `.xlsx`

**Interfaces:**
- Consumes: completed main/vernier integrations and exporter.
- Produces: test logs, before/after evaluation summary, and a final implementation report.

- [ ] **Step 1: Run the complete test suite**

```powershell
python -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp/standardization_full
```

Expected: all existing tests plus new standardization tests pass; no formal-reading regression is allowed.

- [ ] **Step 2: Run static checks**

```powershell
python -m compileall -q caliper main.py tools tests
git diff --check
```

Expected: both commands exit with code 0.

- [ ] **Step 3: Run the 49-image batch evaluation**

```powershell
python tools/evaluate_all_pipeline.py --input-dir tupian --output-dir debug_tupian_batch_evaluation_20260813_standardization
```

Compare `evaluation.json` with `debug_tupian_batch_evaluation_20260813_research_audit_v2/evaluation.json` for:

```text
reading_mm
main_scale_mm
vernier_scale_mm
zero_x
within_0_02mm
within_0_10mm
within_0_50mm
mean_abs_error_mm
```

The values must be identical because standardization is diagnostic-only. If any value differs, stop and locate an unintended formal-path mutation before accepting the change.

- [ ] **Step 4: Verify representative standardization modes**

Read `standardization_summary.json` and verify:

- at least one vernier sample reports `two_clusters`;
- at least one sample reports `single` or `unknown` without raising an exception;
- `130.70.jpg` and `40.20.jpg` still expose their existing failure evidence rather than receiving fabricated curves;
- no sample reports a curve tick count larger than the accepted tick count.

- [ ] **Step 5: Update the project documentation with the measured result**

Append the actual test count, batch comparison, generated export directory, and any known no-curve failure cases to `README.md` and `docs/项目代码说明书.md`. Do not claim improved accuracy unless the batch metrics actually change and the change is intentionally enabled.

- [ ] **Step 6: Commit the verified implementation**

```powershell
git add README.md docs/项目代码说明书.md
git commit -m "test: verify standardization curves preserve readings"
```

## Self-Review Checklist

- [ ] Every design requirement has a corresponding task: unified contract (Task 1), main scale (Task 2), vernier scale (Task 3), UI/export (Task 4), and no-regression validation (Task 5).
- [ ] Legacy helper return keys remain unchanged; canonical aliases are additive.
- [ ] No task uses filename truth, fixed 51-line fitting, or theoretical gap filling.
- [ ] Fast mode has an explicit no-computation assertion.
- [ ] Empty, non-finite and insufficient-cluster cases have concrete tests and fallback values.
- [ ] The plan contains no `TBD`, `TODO`, or unspecified implementation step.
