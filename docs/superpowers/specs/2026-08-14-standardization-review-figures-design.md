# Standardization Review Figures Design

## Goal

Export ten standalone review figures from the rotated ROI without changing
the recognition path or adding them to the paper: five main-scale figures and
five vernier-scale figures.

## Layout

Each PNG contains two vertically stacked sections:

1. The rotated ROI crop for the selected scale. The crop is derived from the
   pipeline's `orient.rotated_color` and the split result's scale coordinates;
   it is not cropped from the original input image.
2. One normalized standard-response plot built from the corresponding
   `standardization['curves']['normalized_response']` array. Accepted tick
   centers are marked on the plot; the vernier zero line is marked separately.

The figure contains no valley, connected-component, per-tick correction, OCR,
or alignment panels. The source crop and curve share the same local x-axis.

## Samples

Use five representative images covering normal, two-cluster, single-cluster,
and known difficult cases. The first run uses `30.00.jpg`, `72.52.jpg`,
`90.14.jpg`, `120.60.jpg`, and `140.00.jpg`, producing ten files.

## Boundaries

- Run `CaliperPipeline(fast_mode=False)` only for diagnostics.
- Do not read filename values as algorithm input.
- Do not alter `main_ticks`, `vernier_ticks`, `zero_x`, alignment, or total.
- If a scale has no standardization result, write a labeled placeholder figure
  instead of fabricating a curve.
- Keep the existing merged debug exports unchanged.
