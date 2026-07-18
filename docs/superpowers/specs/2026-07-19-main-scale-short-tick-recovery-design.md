# Main Scale Short Tick Recovery Design

## Goal

Recover real main-scale ticks that already have a vertical-projection candidate
but are rejected only because their longest continuous binary segment is shorter
than the global hard minimum. Do not synthesize ticks from an ideal grid.

The motivating sample is `120.60.jpg`. Its candidates at x=1342, 1390, and
1440 have projection peaks and local 48 px spacing, but their continuous
segments are 28, 21, and 32 px. The current 138 px tick band requires 34 px.

## Detection Policy

The existing minimum continuous-length filter remains the strong path. A
candidate rejected only for a short continuous segment may be recovered when
all of these image-derived conditions hold:

1. It is an existing `coarse_main_xs` projection candidate.
2. Its longest continuous segment is at least 60 percent of the normal
   minimum length.
3. Its total foreground-row count is at least twice the normal minimum length.
4. Both adjacent coarse candidates are within 30 percent of the median coarse
   candidate period for the current image.

The recovered tick keeps its measured x and segment geometry and is marked
`is_recovered_short=True`. No x position is interpolated or inserted when a
projection candidate is absent.

## Configuration

Add the following main-scale configuration values:

- `short_tick_recovery_enabled=True`
- `short_tick_min_contiguous_ratio=0.60`
- `short_tick_min_foreground_factor=2.00`
- `short_tick_period_tolerance=0.30`

## Visualization

Recovered short ticks use a distinct orange overlay in the main-scale tick
visualization. Normal short ticks remain green and long ticks remain bright
green with a cyan marker. This exposes all recovered evidence to inspection.

## Scope

The change is limited to `extract_ticks_from_binary` and its main-scale
configuration and visualization. It does not change threshold-segment
generation, ROI extraction, vernier detection, digit OCR, or readout merging.

## Verification

- `120.60.jpg`: recover x=1342, 1390, and 1440 from existing projection
  candidates; do not recover x=1195 or 1247.
- Confirm the 1294-to-1489 gap is replaced by locally regular tick spacing.
- Check the main-scale visualization identifies recovered ticks distinctly.
- Run representative normal images and verify no new recovered ticks or
  reading changes unless they satisfy all recovery evidence.
- Run Python syntax checks and `git diff --check`.
