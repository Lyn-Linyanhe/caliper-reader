# OCR Multi-Digit Label Gap 0.75 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group real `10`-`15` main-scale labels with up to a 0.75-main-gap character spacing so multi-digit OCR labels no longer collapse to their leading digit.

**Architecture:** Keep the existing per-character template OCR and `_group_main_ocr_labels` guards. Change only the `OCRConfig.main_label_group_gap_ratio` default, with a focused unit test that exercises the grouping path and dataset regression tests that verify end-to-end readings.

**Tech Stack:** Python 3, NumPy, OpenCV, existing caliper pipeline.

## Global Constraints

- Only group labels whose leading character is `1` and whose numeric value is from `10` through `15`.
- Do not change OCR crops, templates, connected-component filtering, main tick detection, vernier detection, or readout merging.
- Preserve the existing label-to-main-tick binding and nearest-left-of-zero selection.
- Do not infer labels that have no recognized character candidates.

---

### Task 1: Cover the wider label grouping boundary

**Files:**
- Create: `tests/test_main_ocr_grouping.py`
- Modify: `caliper/config.py:323`

**Interfaces:**
- Consumes: `caliper.merger._group_main_ocr_labels(char_candidates, main_ticks, main_gap)`.
- Consumes: `caliper.result.DigitInfo` and `config.ocr.main_label_group_gap_ratio`.
- Produces: automated proof that a 33px gap at a 48px main gap forms label `11`, while a 37px gap does not.

- [ ] **Step 1: Write the failing test**

```python
from caliper.config import config
from caliper.merger import _group_main_ocr_labels
from caliper.result import DigitInfo


def candidate(value, x1, x2):
    digit = DigitInfo(
        x=(x1 + x2) // 2,
        y=20,
        value=value,
        text=str(value),
        confidence=0.9,
        bbox=(x1, 0, x2, 40),
    )
    return {
        "digit": digit,
        "value": value,
        "text": str(value),
        "confidence": 0.9,
        "bbox": digit.bbox,
        "cc_confidence": 0.9,
        "center_x": digit.x,
        "source": "single_char",
    }


def test_groups_11_at_33px_gap():
    labels = _group_main_ocr_labels(
        [candidate(1, 1871, 1891), candidate(1, 1924, 1944)],
        [{"x": 1908}],
        main_gap=48.0,
    )
    assert [(label["text"], label["source"]) for label in labels] == [("11", "grouped_2digit")]


def test_does_not_group_11_beyond_075_main_gap():
    labels = _group_main_ocr_labels(
        [candidate(1, 1871, 1891), candidate(1, 1928, 1948)],
        [{"x": 1881}, {"x": 1938}],
        main_gap=48.0,
    )
    assert all(label["source"] == "single_char" for label in labels)
```

- [ ] **Step 2: Run the test before the configuration change**

Run: `python -m pytest tests/test_main_ocr_grouping.py -v`

Expected: `test_groups_11_at_33px_gap` fails because the previous 0.55 ratio permits only 26.4px.

- [ ] **Step 3: Change the configuration default**

```python
class OCRConfig:
    main_label_group_gap_ratio: float = 0.75
```

Leave `_group_main_ocr_labels` unchanged so its existing `1` plus `0`-to-`5` guard remains the only grouping policy.

- [ ] **Step 4: Run the focused unit test**

Run: `python -m pytest tests/test_main_ocr_grouping.py -v`

Expected: both tests pass.

- [ ] **Step 5: Commit the focused change**

```bash
git add caliper/config.py tests/test_main_ocr_grouping.py
git commit -m "fix: widen main OCR label grouping gap"
```

### Task 2: Verify target samples and whole dataset

**Files:**
- Modify: `tools/evaluate_main_short_tick_recovery.py` only if its existing output needs the `main_derivation.ocr_text` field for reporting.
- Read: `tupian/*.jpg`
- Read: `debug_tupian_main_short_tick_recovery_20260719/evaluation.json`

**Interfaces:**
- Consumes: `CaliperPipeline(fast_mode=True).run(image)`.
- Consumes: `result.extra_info["main_derivation"]` fields `ocr_text`, `ocr_reason`, and `ocr_candidates`.
- Produces: end-to-end verification of target readings and an all-image regression summary.

- [ ] **Step 1: Run the four target samples**

Run:

```powershell
$names=@('100.00.jpg','100.74.jpg','110.00.jpg','110.50.jpg')
foreach($n in $names){
  python -c "from tools.export_ocr_issue_samples import read_image,INPUT_DIR; from caliper.pipeline import CaliperPipeline; p=CaliperPipeline(fast_mode=True); r=p.run(read_image(INPUT_DIR/'$n')); d=r.extra_info['main_derivation']; print('$n', r.main_scale, r.total, d.get('ocr_text'))"
}
```

Expected: OCR text `10`, `10`, `11`, `11`; main readings `100`, `100`, `110`, `110`.

- [ ] **Step 2: Run unchanged-path checks**

Run the same command for `120.60.jpg`, `50.98.jpg`, and `90.28.jpg`.

Expected: `120.60` remains grouped as `12`; `50.98` remains `50.98`; `90.28` remains `90.27`.

- [ ] **Step 3: Run full numeric dataset evaluation**

Run: `python tools/evaluate_main_short_tick_recovery.py`

Expected: the four target samples no longer have leading-digit main-scale readings, and the output JSON is refreshed without runtime exceptions.

- [ ] **Step 4: Run static checks**

Run:

```powershell
python -m py_compile caliper/config.py caliper/merger.py caliper/pipeline.py
git diff --check -- caliper/config.py tests/test_main_ocr_grouping.py
```

Expected: both commands exit successfully.

- [ ] **Step 5: Commit verification support if modified**

```bash
git add tools/evaluate_main_short_tick_recovery.py
git commit -m "test: report OCR label grouping regression"
```
