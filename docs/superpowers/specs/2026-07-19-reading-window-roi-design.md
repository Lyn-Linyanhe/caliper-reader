# Reading-Window ROI and Main-Scale Fallback Design

## Goal

Produce a compact reading-window ROI that contains the complete functional
reading area: the main-scale label immediately left of the vernier zero, its
main tick, the full vernier tick range, and the lower edge of the vernier
body. Exclude jaws, upper slider material, and unrelated ruler tail whenever
the image evidence permits.

The ROI must preserve measured scale evidence. It must not assume 51 vernier
ticks, synthesize ticks, or use image-specific coordinates.

## Current Failure

`_refine_roi_to_reading_window()` applies a horizontal crop based on a dark
vernier-body estimate. Its left boundary is irreversible. On `11.00`,
`30.00`, `33.00`, `60.96`, `80.80`, `80.90`, and `100.60`, the preceding ROI
detects 49 to 52 real vernier ticks, while the narrowed ROI detects none.

`40.30` fails earlier: `_proj_find_x_range()` accepts a long periodic segment
on the ruler tail that does not contain the actual vernier body or zero line.

`40.20` shows an unsafe vertical refinement: the refined upper edge removes
the main-scale band needed to split and read both scales.

## ROI Candidate Selection

ROI extraction will retain three candidates rather than destructively
replacing the previous crop:

1. Projection candidate: broad recall-oriented box from the existing x/y
   projections.
2. Caliper-body candidate: existing y/right-edge refinement applied to the
   projection candidate.
3. Compact reading candidate: a tight box derived from scale and body
   structure.

The compact candidate must include these observed structures:

- a main-scale tick band;
- a vernier tick band and its measured valley-bounded range;
- the vernier body below the scale bands;
- the main-scale integer label immediately left of the detected zero line.

The first two candidates remain available as fallbacks. A compact candidate is
accepted only when it preserves both scale bands and a reliable measured
vernier range. Otherwise the body candidate is used. If the body candidate is
also invalid, the projection candidate is used.

The existing `_refine_roi_to_reading_window()` output will no longer become
the final ROI merely because its geometry is valid. Its body estimate may be
reused as a compact-candidate cue after structural validation.

## Initial X-Range Guard

The periodic main-scale projection is evidence for a ruler but is insufficient
by itself. The x-range chooser will validate its selected segment against a
vernier-body candidate found over the full projected y band. A selected ruler
tail that does not cover the body and its left-side zero/label area is
rejected. The fallback range is centered on the observed body plus
measurement-derived margins.

## Vertical Guard

The y/right-edge refinement may tighten the ROI only if the refined candidate
still has both scale bands separated by a viable seam. A refinement that
removes the main-scale band, such as `40.20`, is rejected and falls back to
the preceding y range.

## Main-Scale Integer Fallback

Normal reading continues to use the OCR integer nearest to and left of the
vernier zero. Add a guarded fallback for an OCR integer `N` that is bound to
its corresponding main tick:

1. The normal left-of-zero selection has no usable integer.
2. The zero line is left of `N`'s bound tick.
3. The zero-to-bound-tick distance is no more than one measured main-scale
   gap, with the existing positional tolerance.

When all conditions hold, use `N - 1` as the main-scale integer. This handles
the case where OCR sees the next integer to the right of the zero line, while
rejecting distant or unbound labels.

## Observability and Tests

- ROI diagnostics will retain and visualize projection, body, compact, and
  selected boxes with the chosen/fallback reason.
- Add focused unit tests for the guarded `N - 1` main-scale fallback.
- Add an ROI regression runner over `40.20`, `40.30`, `100.60`, `80.80`, and
  normal controls `50.98`, `100.00`, and `120.60`.
- Each regression reports selected ROI bounds, fallback reason, main/vernier
  tick counts, zero position, OCR text, and final reading.
