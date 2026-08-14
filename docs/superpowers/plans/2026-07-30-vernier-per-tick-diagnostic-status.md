# Vernier Per-Tick Diagnostic Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve a diagnostic status for every formal vernier candidate during per-tick correction.

**Architecture:** Add optional failure metadata to the existing thin-stroke trace function and an optional candidate-state return from the straightening helper. Detailed-mode detection stores all states; UI diagnostics show both traced and untraced counts. No production recognition input changes.

**Tech Stack:** Python, NumPy, OpenCV, pytest.

## Global Constraints

- Debug-only behavior; `make_debug=False` remains free of correction diagnostics.
- Candidate source remains the final projection candidate list.
- Untraced is diagnostic state, never candidate rejection.
- No changes to zero-line selection or reading computation.

---

### Task 1: Record every candidate state

**Files:**
- Modify: `caliper/vernier_scale.py:1631-1721, 956-979, 471-519`
- Modify: `tests/test_vernier_per_tick_correction.py`

**Interfaces:**
- `_trace_vernier_tick_centerline(..., return_failure_reason=False)` returns its existing trace result by default; when requested returns `(trace, reason)`.
- `_build_per_tick_straightened_band(..., include_candidate_states=False)` returns its existing `(band, traces)` by default; when requested returns `(band, traces, candidate_states)`.

- [ ] **Step 1: Write a failing status-coverage test**

```python
def test_per_tick_diagnostics_keep_an_entry_for_every_formal_candidate():
    band = np.zeros((40, 40), dtype=np.uint8)
    band[:, 8] = 255

    _corrected, traces, states = _build_per_tick_straightened_band(
        band, [8, 28], observed_period=12.0, include_candidate_states=True
    )

    assert len(states) == 2
    assert len(traces) == 1
    assert [state['status'] for state in states] == ['traced', 'untraced']
    assert states[1]['reason'] is not None
```

- [ ] **Step 2: Run the test and verify expected failure**

Run: `python -m pytest -q tests/test_vernier_per_tick_correction.py::test_per_tick_diagnostics_keep_an_entry_for_every_formal_candidate`

Expected: FAIL because the current function lacks `include_candidate_states` and silently omits untraced candidates.

- [ ] **Step 3: Implement optional trace reasons and candidate states**

```python
if include_candidate_states:
    return corrected, traces, candidate_states
return corrected, traces
```

For each input candidate append exactly one state before continuing. Only `traced` states contribute pixels to `corrected`.

- [ ] **Step 4: Store and show counts in detailed diagnostics**

Use `candidate_states` in `per_tick_correction`, expose `untraced_count`, and change the diagnostic header to show the complete accounting. Mark untraced candidate anchors in a separate warning color on the raw-band overlay.

- [ ] **Step 5: Verify focused and regression tests**

Run: `python -m pytest -q tests/test_vernier_per_tick_correction.py tests/test_vernier_debug_panel.py tests/test_vernier_valley_regressions.py tests/test_vernier_top_stroke_split.py tests/test_alignment_ambiguity.py`

Expected: all tests pass.
