# README Algorithm and Parameter Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `README.md` from a workflow guide to an algorithm-level reference that explains the implemented calculations, decisions, defaults, and parameter tradeoffs.

**Architecture:** Keep the existing user-facing quick start and debugging guide, then add a parameter map and algorithm detail beneath each stage. Tables distinguish active parameters from legacy/unconsumed configuration fields, and explain direction of effect and unsafe independent tuning.

**Tech Stack:** Python, OpenCV, NumPy, current `caliper/config.py` defaults.

## Global Constraints

- Documentation only; do not change any recognition code or default value.
- Every parameter value must match `caliper/config.py` and its actual call sites.
- Explain `valley_preferred_tick_count=51` as a tie-break preference, never a forced count or synthetic-tick mechanism.
- Preserve the existing rule: production reading does not use file names, theoretical tick grids, or missing-tick fabrication.

---

### Task 1: Build the algorithm and parameter inventory

**Files:**
- Modify: `README.md`
- Reference: `caliper/config.py`, `caliper/preprocess.py`, `caliper/region_split.py`, `caliper/main_scale.py`, `caliper/vernier_scale.py`, `caliper/ocr.py`, `caliper/merger.py`

**Interfaces:**
- Consumes: `config.preprocess`, `config.region_split`, `config.main_scale`, `config.vernier_scale`, `config.ocr`, `config.merger`.
- Produces: an exact mapping from a parameter group to its active algorithm stage and effect.

- [x] **Step 1: Record formulas and gates**

Document the adaptive threshold, component-endpoint seam selection, valley total-score weighted sum, alignment error, ambiguity threshold clamp, OCR search window, and final reading equations. Name the condition that rejects each candidate.

- [x] **Step 2: Classify active parameters**

Group active defaults by preprocessing, split, main scale, vernier, OCR and result-quality; for each state default, units, direction of effect, and risk when changed alone.

- [x] **Step 3: Identify non-contract configuration**

State that configuration fields not reached by the current path are not tuning knobs, preventing a reader from treating legacy compatibility settings as live algorithm controls.

### Task 2: Add algorithm-level sections to README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1 inventory.
- Produces: an algorithm reference that can be used to diagnose a visible failure before editing a parameter.

- [x] **Step 1: Add parameter discipline and notation**

Define image dimensions `W`, `H`, main-tick pixel gap `g`, observed vernier period `p`, and specify the one-variable-at-a-time test protocol.

- [x] **Step 2: Expand each algorithm stage**

Insert equations, selection order, default values, and parameter effect tables for preprocessing, region split, main ticks, vernier valleys/components/alignment, and OCR/merge.

- [x] **Step 3: Add a tuning dependency map**

Show which visualization proves each parameter class should be considered and prohibit downstream tuning when ROI or `split_y` is wrong.

### Task 3: Verify source accuracy and documentation integrity

**Files:**
- Modify: `README.md`
- Test: `tests/test_alignment_ambiguity.py`, `tests/test_vernier_debug_panel.py`

**Interfaces:**
- Consumes: final README.
- Produces: documentation with parameter defaults and behavioural constraints validated against source.

- [x] **Step 1: Check every documented default against config**

Run `rg -n "gamma: float = 1.5|vertical_open_height_ratio: float = 0.032|peak_threshold_factor: float = 0.20|valley_preferred_tick_count: int = 51|align_ambiguity_margin_max_px: float = 0.10|main_label_group_gap_ratio: float = 0.75" caliper/config.py README.md`.

- [x] **Step 2: Check mandatory constraints and diff whitespace**

Run `rg -n "不补线|不强制拟合|并列候选|不是强制|参数.*默认值|调参" README.md` and `git diff --check -- README.md`.

- [x] **Step 3: Run algorithm-adjacent regressions**

Run `python -m pytest -q tests/test_alignment_ambiguity.py tests/test_vernier_debug_panel.py`.
Expected: all tests pass; no production source change.
