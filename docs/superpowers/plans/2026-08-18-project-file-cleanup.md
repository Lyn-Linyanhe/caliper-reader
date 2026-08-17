# Project File Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove unreferenced scratch files from the project while preserving source code, test data, paper deliverables, and reproducibility-critical diagnostics.

**Architecture:** Cleanup is conservative and two-tiered. Clearly disposable caches and root-level scratch outputs are removed; large historical diagnostic directories remain in place until their evidence status is confirmed, then can be moved to an external archive. No tracked source, tests, paper source, or current audit snapshot is deleted.

**Tech Stack:** PowerShell file inventory, Git status/reference search, existing project documentation, 7-Zip/archive checks.

**Spec:** User request: clean unused and expired project files without damaging the active algorithm, test data, or paper materials.

## Global Constraints

- Do not modify or remove tracked source code, tests, `tupian/`, `paper/`, `docs/`, or current audit evidence.
- Do not remove `debug_tupian_batch_evaluation_20260813_research_audit_v2/`, `debug_tupian_standardization_review_20260814_shared_x/`, `debug_tupian_vernier_pixel_correction_current_20260814_v2/`, or `paper/03_排版与审校/paper_render_audit/`.
- Remove only untracked paths with no source/document references and an unambiguous cache or scratch role.
- Verify the final Git status and confirm the protected paths still exist.

### Task 1: Inventory and protect active evidence

**Files:**
- Read: `.gitignore`, `README.md`, `docs/项目代码说明书.md`, `docs/源码审计报告_20260813.md`
- Read: `paper/03_排版与审校/文档索引.md`
- No source files are modified.

- [x] Record the active source, test-data, paper, and audit paths.
- [x] Record the explicitly protected diagnostic snapshots.

### Task 2: Remove disposable scratch outputs

**Paths to remove:**
- `.pytest_cache/`
- `.pytest_tmp_table2/`
- `.docx_render_table2/`
- `__pycache__/`
- `.pytest_tmp_reference_audit/`
- `tmp_pytest_paper_audit/`
- `.tmp_edge_profile_audit/`
- `.tmp_edge_profile_audit_2/`
- `.tmp_lo_profile_audit/`
- `.tmp_lo_profile_audit_v2/`
- `.tmp_lo_profile_png/`
- `tmp_std_check/`
- Root `paper_render_audit/` (temporary rendering cache; the protected audit directory is under `paper/03_排版与审校/`).
- Root `.tmp_batch_audit_output.jsonl`, `.tmp_config_audit_report.md`, `.tmp_config_reads_current.txt`, `.tmp_defs.txt`, `.tmp_defs_current.txt`
- Root-level `debug_*.png` and `tmp_*.png` files only; dated diagnostic directories are excluded.

- [x] Resolve every path and verify it is inside the repository.
- [x] Remove only the listed untracked scratch paths.
- [x] Recount the paths and record the freed size; 127,507,748 bytes were targeted.
- [x] Leave the inaccessible empty `.pytest_cache/` directory in place and report the permission limitation.

### Task 3: Keep or separately archive historical diagnostics

**Protected paths:**
- `debug_tupian_batch_evaluation_20260813_research_audit_v2/`
- `debug_tupian_standardization_review_20260814_shared_x/`
- `debug_tupian_vernier_pixel_correction_current_20260814_v2/`
- `debug_tupian_standardization_20260814/`
- `debug_tupian_batch_evaluation_20260815_current/`
- `debug_tupian_standardization_review_20260814_final_v9/`
- `debug_tupian_binary_compare_20260815/`
- `paper/03_排版与审校/paper_render_audit/`

- [x] Do not delete historical `debug_tupian_*` directories in this cleanup pass.
- [x] Produce a separate size/name report for later archival approval during inventory.

### Task 4: Verify cleanup

- [x] Run `git status --short --untracked-files=all` and confirm no tracked file changed because of cleanup.
- [x] Confirm `tupian/`, `paper/`, source code, tests, and protected diagnostics remain present.
- [x] Search active code/docs for references to the removed scratch names; only the cleanup plan/script intentionally mention them.
- [x] Report removed paths, approximate freed space, retained evidence, and deferred archive candidates.
