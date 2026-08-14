# Standardization Review Shared X-Domain Design

## Problem

The review figure already stored equal source spans for the rotated crop and
the normalized curve, but the two panels computed their marker columns in
separate rendering functions. A reviewer therefore had no visible proof that
the upper and lower annotations came from one horizontal coordinate frame.

## Design

The exporter keeps one display-only half-open domain `[start, end)`.
`image_x1:image_x2` is the corresponding rotated-image slice and
`curve[start:end]` is the corresponding curve slice. `_shared_marker_geometry`
converts accepted local tick positions and the optional zero position to screen
columns once. Both `_draw_image_content` and `_curve_panel` receive those
columns and retain the old metadata fields for compatibility. A muted guide is
drawn only across the separator labels so a marker can be visually followed
from the upper image to the lower curve without obscuring the source data.

## Invariants

- `image_x2 - image_x1 == end - start`.
- `image_content_x == curve_content_x == shared_content_x`.
- Tick marker columns are identical in the image, curve, and shared metadata.
- Zero-line columns are identical whenever the zero line is inside the domain.
- The exporter does not mutate formal ticks, standardization arrays, or reading
  results.

## Verification

`tests/test_standardization_review_figures.py` checks the shared marker
metadata. The focused standardization suite checks the existing crop, curve,
placeholder, and export contracts. Five sample pairs are re-exported under
`debug_tupian_standardization_review_20260814_shared_x/` and their JSON
metadata is audited for equal content bounds, marker columns, and source spans.
