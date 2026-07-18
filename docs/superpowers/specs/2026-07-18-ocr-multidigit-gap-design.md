# OCR Multi-Digit Label Gap Design

## Goal

Allow valid main-scale labels from `10` through `15` to be grouped when small
capture and bounding-box variations make the gap between their two characters
slightly larger than the current limit. The motivating sample is
`120.60.jpg`, whose recognized `1` and `2` have a `23 px` gap while
`main_gap` is `48 px`.

## Change

- Add `main_label_group_gap_ratio` to `OCRConfig` with a default of `0.55`.
- In `_group_main_ocr_labels`, calculate the allowed two-character label gap
  as `max(6 px, main_gap * main_label_group_gap_ratio)`.
- Keep the existing grouping guard unchanged: the first character must be `1`
  and the combined value must be between `10` and `15`.
- Do not change connected-component merging, OCR crop expansion, template
  matching, single-character selection, or label-to-tick binding.

For `120.60.jpg`, the new limit is `26.4 px`, so its `23 px` character gap is
accepted. The previous limit was `21.6 px`.

## Diagnostics

Existing OCR candidate diagnostics remain sufficient. A successfully grouped
candidate reports `source=grouped_2digit` and text `12`.

## Verification

- `120.60.jpg`: expanded retry is used and OCR text becomes `12`.
- Existing multi-digit samples: verify grouping remains limited to `10`-`15`.
- Representative single-digit samples: verify OCR text and reading are
  unchanged.
- Missing-input and zero-anchor failures: verify no behavior change.
- Run Python syntax checks and `git diff --check`.
