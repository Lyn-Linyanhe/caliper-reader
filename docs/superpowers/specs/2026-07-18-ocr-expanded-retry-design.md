# OCR Expanded Retry Design

## Goal

When the normal main-scale OCR crop produces no usable digit, retry once with
the same horizontal range and a vertical range expanded by one measured main
tick gap above and below. This specifically addresses digits clipped by the
normal vertical crop, including `120.60.jpg`.

## Behavior

1. Run the existing OCR crop, connected-component extraction, template
   recognition, digit grouping, and candidate selection unchanged.
2. Trigger one expanded retry when either:
   - the normal crop contains no accepted digit connected component; or
   - connected components exist but template recognition and grouping produce
     no digit candidate.
3. Keep the normal crop horizontal bounds unchanged.
4. Expand the normal crop vertically by `1 * main_gap` above and below, clipped
   to the main-scale image bounds.
5. Re-run the complete connected-component and OCR path on the expanded crop.
6. Do not retry `no_ocr_digit_left_of_zero`, because that failure indicates a
   zero-anchor or candidate-side problem rather than a clipped digit.
7. If the retry succeeds, use its result. If it fails, return the retry failure
   reason without further expansion.

## Diagnostics

The main-reading derivation records whether the expanded retry was used and
the vertical expansion amount. The OCR debug visualization uses the crop from
the successful or final attempt so its rectangle matches the data actually
processed.

## Scope

The change is limited to main-scale OCR crop selection and retry orchestration.
It does not change ROI extraction, vernier zero detection, template images,
connected-component thresholds, or main/vernier tick detection.

## Verification

- `120.60.jpg`: verify that the expanded crop contains complete `1` and `2`
  glyphs and report the resulting OCR text and full reading.
- Representative normal first-pass samples: verify that their OCR result and
  reading remain unchanged and that no retry is reported.
- A missing-zero sample such as `100.60.jpg`: verify that expansion is not
  attempted because required OCR inputs are absent.
- Run Python syntax checks and `git diff --check` on the edited modules.
