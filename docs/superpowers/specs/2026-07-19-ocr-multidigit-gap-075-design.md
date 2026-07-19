# OCR Multi-Digit Label Gap 0.75 Design

## Goal

Recover multi-digit main-scale labels `10` through `15` when both characters
are recognized but their bounding-box gap is larger than the previous grouping
limit. The target samples are `100.00.jpg`, `100.74.jpg`, `110.00.jpg`, and
`110.50.jpg`.

## Evidence

The template recognizer already identifies both characters. The failures occur
only in label grouping:

- `100.00`: gap 27 px, main gap 48 px
- `100.74`: gap 26 px, main gap 47 px
- `110.00`: gap 33 px, main gap 47 px
- `110.50`: gap 33 px, main gap 48 px

The current ratio of 0.55 accepts at most 25.85 to 26.4 px, so each pair is
rejected before label binding and reading derivation.

## Change

Change `OCRConfig.main_label_group_gap_ratio` from `0.55` to `0.75`.
Keep the existing grouping guards unchanged:

- the left character must be `1`;
- the combined label must be between `10` and `15`;
- label-to-main-tick binding and nearest-left-of-zero selection remain
  unchanged.

At a 48 px main gap, the allowed character gap becomes 36 px and includes the
observed 33 px maximum. Adjacent centimeter labels remain separated by roughly
ten main gaps, so this change cannot combine neighboring labels under the
existing `10`-to-`15` guard.

## Scope

The change is a single OCR configuration adjustment. It does not modify
template matching, connected components, OCR crop expansion, main tick
detection, vernier detection, or readout merging.

## Verification

- Target samples produce OCR text `10`, `10`, `11`, and `11` respectively.
- Their main-scale readings become 100, 100, 110, and 110 mm respectively.
- `120.60.jpg` continues to produce grouped text `12`.
- Single-digit samples such as `50.98.jpg` and `90.28.jpg` remain unchanged.
- Run the numeric filename dataset and report any reading regression.
- Run Python syntax checks and `git diff --check`.
