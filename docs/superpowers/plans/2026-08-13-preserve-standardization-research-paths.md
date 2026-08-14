# Preserve Standardization Research Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve and explicitly test the standard-response, length-clustering, per-tick correction, and vernier-rectification research paths that are not yet part of formal reading, without changing formal recognition behavior.

**Architecture:** Keep production recognition and research/diagnostic code in the same existing modules, but mark research entry points by their API and documentation. Restore only functions whose historical implementation has a clear future research role, expose no research result to `CaliperResult` unless an existing debug path requests it, and add contract tests that make accidental deletion visible.

**Tech Stack:** Python 3, NumPy, OpenCV, pytest, Git history inspection, Markdown project documentation.

## Global Constraints

- Do not reset, checkout, clean, or overwrite unrelated user changes.
- Research paths must not alter the default formal reading, zero-line location, alignment, or merged total.
- Display-only standard curves must use observed tick lengths/clusters; do not add a forced 51-line theoretical curve.
- Per-tick correction must allow each tick to have its own slope; it must remain diagnostic until a separately tested production switch is introduced.
- `vernier_rectify.rectify_vernier_region()` and related helpers must remain available for future integration.

---

### Task 1: Inventory research paths and historical deletions

**Files:**
- Read: `caliper/vernier_scale.py`, `caliper/vernier_rectify.py`, `caliper/main_scale.py`, `caliper/utils.py`
- Read: `tests/test_legacy_code_cleanup.py`, `tests/test_vernier_standard_curve.py`, `tests/test_vernier_per_tick_correction.py`
- Read: Git history for the four modules

**Interfaces:**
- Produces an exact keep/remove list for implementation and documentation.

- [x] **Step 1: Enumerate current research entry points.**

  Confirm the current standard-response, length-clustering, per-tick tracing, and rectification functions and whether they are called by `CaliperPipeline` in fast and detailed modes.

- [x] **Step 2: Compare deleted names with Git history.**

  Treat a historical helper as recoverable only when it directly supports future standardization/校正 research and does not re-enter formal recognition implicitly.

- [x] **Step 3: Record the keep/remove decision in the project manual.**

  The manual must distinguish “formal path”, “detailed display path”, and “future research path”.

### Task 2: Restore or retain future research APIs

**Files:**
- Modify: `caliper/main_scale.py`
- Modify: `caliper/utils.py`
- Modify: `caliper/vernier_scale.py`
- Modify: `caliper/vernier_rectify.py`

**Interfaces:**
- Preserved callable APIs include `_build_length_clustered_standard_response`, `_build_per_tick_straightened_band`, `_trace_vernier_tick_centerline`, and `rectify_vernier_region`.
- Any restored helper must be opt-in and must not be called from the default formal reading path.

- [ ] **Step 1: Keep the current observed-length standard response.**

  Keep `_build_length_clustered_standard_response(width, ticks, x_offset)` as the display/research implementation. It returns `(response, info)` and uses one or two observed length clusters; it must not synthesize missing ticks.

- [ ] **Step 2: Keep per-tick independent tracing and straightening.**

  Keep `_trace_vernier_tick_centerline(...)` and `_build_per_tick_straightened_band(...)` as detailed diagnostics. Do not replace them with a global angle correction.

- [ ] **Step 3: Keep the whole-region rectification helper.**

  Keep `rectify_vernier_region(region, color_region=None)` and `_find_vernier_body_x_range()` documented as future integration code; the current pipeline may continue using only the body-range helper.

- [ ] **Step 4: Reclassify any historical main-scale/utils helper before restoring it.**

  Restore only a helper that can be called explicitly for research and does not fabricate formal ticks or alter formal outputs. Leave obsolete production alternatives deleted when they have no distinct future research contract.

### Task 3: Add anti-deletion and behavior-isolation tests

**Files:**
- Modify: `tests/test_legacy_code_cleanup.py`
- Modify or create: `tests/test_research_paths_preserved.py`

**Interfaces:**
- Tests import research APIs directly and compare formal fast/detailed outputs on a representative image.

- [ ] **Step 1: Replace incorrect deletion assertions for research APIs.**

  The cleanup test must not assert absence for standardization/校正 helpers that the project explicitly intends to retain.

- [ ] **Step 2: Add presence and output-shape contracts.**

  Assert that standard response returns a one-dimensional response plus cluster metadata, per-tick diagnostics retain candidate states, and `rectify_vernier_region()` returns region/color/transform keys.

- [ ] **Step 3: Add formal-path isolation regression.**

  Run the same image through fast and detailed pipelines and assert the research artifacts do not change `total`, `main_reading`, `vernier_reading`, or `zero_x`.

- [ ] **Step 4: Run focused tests.**

  Run `python -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp/research tests/test_legacy_code_cleanup.py tests/test_vernier_standard_curve.py tests/test_vernier_per_tick_correction.py tests/test_research_paths_preserved.py` and require all tests to pass.

### Task 4: Update documentation and stale configuration comments

**Files:**
- Modify: `docs/项目代码说明书.md`
- Modify: `caliper/config.py`

**Interfaces:**
- Documentation names the exact module/function ownership and states whether each path is formal, detailed-only, or future research.

- [ ] **Step 1: Correct the legacy-code table.**

  Remove retained research functions from the “deleted legacy” list and add a “保留但未接入正式读数” table with their future purpose and activation boundary.

- [ ] **Step 2: Correct config-field status descriptions.**

  Mark fields that are currently unread as compatibility/future-research parameters rather than claiming that deleted code consumes them.

- [ ] **Step 3: Add the maintenance rule.**

  State that a research path may be deleted only after checking its tests, manual entry, and future-integration purpose.

### Task 5: Full verification

**Files:**
- Read-only verification of all changed files

- [ ] **Step 1: Run the full test suite.**

  Run `python -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp/final` and require no failures.

- [ ] **Step 2: Compile all Python modules.**

  Run `python -m compileall -q caliper main.py tools tests`.

- [ ] **Step 3: Check patch hygiene.**

  Run `git diff --check` and inspect `git status --short`; preserve unrelated user files and report the exact changed paths.
