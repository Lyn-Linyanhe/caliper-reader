# Discrete Vernier Reading and Ambiguity Plan

**Goal:** Keep the formal 0.02 mm reading discrete and expose a close adjacent observed tick as a review-only reference.

## Constraints

- Formal value is `best_idx * 0.02`, never an interpolated decimal.
- Reference must be an observed tick adjacent to the primary tick.
- Reference never changes `CaliperResult.total`.
- ROI, split, valley, zero-line, OCR, and tick detection remain unchanged.

## Tasks

1. Add unit tests and a full-image diagnostic report for best-vs-adjacent error margins. Configure a bounded threshold based on main tick gap.
2. Keep parabolic interpolation as diagnostic data, but calculate official vernier reading from the discrete best index. Propagate optional primary/reference totals through merger extra info.
3. Add an orange GUI reference row and detailed alignment marker. Update README and run the full test/image regression.
