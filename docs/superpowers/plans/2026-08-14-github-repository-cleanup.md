# GitHub Repository Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronize the public project repository with the current code and documentation while excluding local datasets, paper deliverables, debug exports, and test caches.

**Architecture:** Keep the existing source layout (`caliper/`, `tools/`, `tests/`, `docs/`, `templates/`) and add only repository-level ignore rules plus the reusable vernier review exporter. Stage files by explicit path classes instead of using `git add .`, then verify the staged tree before one normal push to `origin/master`.

**Tech Stack:** Git, Python 3.12, pytest, OpenCV/NumPy diagnostic exporters.

**Spec:** User request: organize the current project and update its corresponding GitHub repository.

## Global Constraints

- Do not force-push, reset, checkout away user changes, or delete local data.
- Do not upload `tupian/`, `paper/`, debug images, Word/PDF deliverables, or test caches.
- Preserve existing source, tests, README, templates, and algorithm documentation.
- Run focused tests and compile checks before committing; report any full-suite timeout.

---

### Task 1: Define repository hygiene rules

**Files:**
- Modify: `.gitignore`
- Test: `git status --short --untracked-files=all`

- [x] Add ignore patterns for pytest caches, local temporary outputs, sample-image directories, paper build artifacts, and generated debug folders without changing existing tracked files.
- [x] Confirm ignored paths no longer appear as candidates while source and documentation files remain visible.

### Task 2: Select the public project change set

**Files:**
- Stage: tracked source changes under `caliper/` and `main.py`
- Stage: public tools under `tools/*.py`
- Stage: tests under `tests/*.py`
- Stage: `README.md`, `docs/*.md`, `docs/superpowers/{plans,specs}/*.md`, and templates
- Exclude: `tupian/`, `paper/`, root debug images, `tmp_*`, `.pytest_tmp*`, and generated reports

- [x] Review the staged name list and ensure no private image, document, cache, or credential is included.
- [x] Include `tools/merge_vernier_pixel_correction_figures.py` and its regression test for the latest diagnostic feature.

### Task 3: Verify the staged repository

**Files:**
- Test: `tests/test_vernier_pixel_correction_merge.py`
- Test: `tests/test_vernier_pixel_correction_export.py`
- Test: `python -m py_compile` for changed Python modules

- [x] Run focused exporter tests with a workspace-local pytest base directory.
- [x] Compile changed modules and inspect `git diff --cached --check`.
- [x] Run the full suite with a bounded timeout; record the result if repository-wide integration tests exceed the limit.

### Task 4: Commit and synchronize

**Files:**
- Commit: all approved staged files

- [ ] Create one descriptive commit on the current `master` branch.
- [ ] Fetch `origin`, verify the remote branch has not advanced unexpectedly, then push normally with `git push origin master`.
- [ ] Confirm the pushed commit and working-tree status, leaving excluded local artifacts untouched.
