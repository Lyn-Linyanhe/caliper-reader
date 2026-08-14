"""Export standalone rotated-ROI standardization review figures.

The figures are audit artifacts only.  They consume the detailed pipeline
results, and do not participate in formal reading or modify any pipeline data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caliper.pipeline import CaliperPipeline


_BACKGROUND = (28, 28, 32)
_TEXT = (225, 225, 225)
_MUTED = (150, 155, 165)
_CURVE = (60, 190, 255)
_TICK = (90, 220, 110)
_ZERO = (70, 75, 255)
_PANEL_WIDTH = 1200
_CONTENT_LEFT = 48
_CONTENT_RIGHT = _PANEL_WIDTH - 18
_CURVE_Y_MAX = 1.62


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f'Unable to read image: {path}')
    return image


def write_image(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode('.png', image)
    if not ok:
        raise RuntimeError(f'Unable to encode image: {path}')
    encoded.tofile(str(path))


def _as_curve(value, width: int) -> np.ndarray:
    if value is None:
        return np.zeros(max(0, int(width)), dtype=float)
    curve = np.asarray(value, dtype=float).reshape(-1)
    if curve.size < width:
        curve = np.pad(curve, (0, width - curve.size))
    elif curve.size > width:
        curve = curve[:width]
    return np.nan_to_num(curve, nan=0.0, posinf=0.0, neginf=0.0)


def _standardization(result: dict) -> dict | None:
    value = result.get('standardization') if result else None
    return value if isinstance(value, dict) else None


def _tick_curve_x(tick: dict, x_offset: int) -> float | None:
    """Return a tick position in the standardization curve's local domain."""
    if not isinstance(tick, dict):
        return None
    for key in ('x_local', 'x_projection', 'x'):
        value = tick.get(key)
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if key != 'x_local' and key == 'x_projection':
            value -= float(x_offset)
        elif key == 'x' and 'x_local' not in tick and 'x_projection' not in tick:
            value -= float(x_offset)
        if np.isfinite(value):
            return value
    return None


def _curve_crop_range(scale: str,
                      standardization: dict | None,
                      result: dict,
                      rotated_width: int) -> dict:
    """Return one shared half-open local x-domain for both review panels.

    ``start``/``end`` index the standardization arrays.  ``image_x1`` and
    ``image_x2`` index the rotated ROI with the same half-open convention.
    Keeping this mapping in one object prevents the image and curve panels
    from silently acquiring different spans as crops are refined.
    """
    width = int((standardization or {}).get('width', rotated_width) or 0)
    width = max(0, min(width, rotated_width))
    x_offset = int((standardization or {}).get('x_offset', 0) or 0)
    x_offset = max(0, min(x_offset, max(0, rotated_width - width)))
    records = (standardization or {}).get('ticks', [])
    tick_xs = [
        x for x in (_tick_curve_x(tick, x_offset) for tick in records)
        if x is not None and 0 <= x < max(1, width)
    ]
    tick_selection = _select_contiguous_tick_run(tick_xs)

    if scale == 'vernier':
        detection = result.get('vernier_band_detection') or {}
        roi = detection.get('vernier_tick_roi')
        if roi is not None and len(roi) == 2:
            try:
                start = int(round(float(roi[0]))) - x_offset
                end = int(round(float(roi[1]))) - x_offset
            except (TypeError, ValueError):
                start, end = 0, width
            # A detector ROI can include a hardware stroke or a missed-tick
            # gap.  Keep the ROI as the outer guard, but use the longest
            # observed periodic run to remove an isolated tail candidate.
            if tick_selection['run']:
                run_start, run_end = _bounded_tick_extent(
                    tick_selection['run'], width
                )
                start = max(start, run_start)
                end = min(end, run_end)
        elif tick_xs:
            start, end = _bounded_tick_extent(tick_xs, width)
        else:
            start, end = 0, width
    elif tick_xs:
        start, end = _bounded_tick_extent(tick_xs, width)
    else:
        start, end = 0, width

    if width:
        start = min(max(int(start), 0), width - 1)
        end = min(max(int(end), start + 1), width)
    else:
        start = end = 0
    image_x1 = max(0, min(rotated_width, x_offset + start))
    image_x2 = max(image_x1 + 1, min(rotated_width, x_offset + end)) if rotated_width else 0
    return {
        'start': int(start),
        'end': int(end),
        'image_x1': int(image_x1),
        'image_x2': int(image_x2),
        'x_offset': int(x_offset),
        'width': int(width),
        'tick_run': {
            'count': int(len(tick_selection['run'])),
            'total_count': int(len(tick_selection['ordered'])),
            'excluded_count': int(tick_selection['excluded_count']),
            'median_gap': float(tick_selection['median_gap']),
            'gap_threshold': float(tick_selection['gap_threshold']),
            'largest_gap': float(tick_selection['largest_gap']),
            'run_x': [
                float(tick_selection['run'][0]),
                float(tick_selection['run'][-1]),
            ] if tick_selection['run'] else [],
        },
    }


def _select_contiguous_tick_run(xs: list[float]) -> dict:
    """Select the longest periodic tick run for review-domain cropping.

    Standardization records can contain a distant hardware candidate.  Using
    the raw min/max of all records makes the upper crop and lower curve share
    a mathematically equal span, but not the actual scale span.  A robust
    median-gap split removes only large discontinuities and keeps the longest
    observed run; it is display-only and never changes recognition candidates.
    """
    ordered = []
    for value in sorted(xs or []):
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(value):
            continue
        if not ordered or abs(value - ordered[-1]) > 0.5:
            ordered.append(value)
    if not ordered:
        return {
            'ordered': [],
            'run': [],
            'excluded_count': 0,
            'median_gap': 0.0,
            'gap_threshold': 0.0,
            'largest_gap': 0.0,
        }
    if len(ordered) < 2:
        return {
            'ordered': ordered,
            'run': ordered,
            'excluded_count': 0,
            'median_gap': 0.0,
            'gap_threshold': 0.0,
            'largest_gap': 0.0,
        }
    gaps = np.diff(np.asarray(ordered, dtype=float))
    positive_gaps = gaps[np.isfinite(gaps) & (gaps > 0)]
    median_gap = (
        float(np.median(positive_gaps))
        if positive_gaps.size else 0.0
    )
    if median_gap <= 0.0:
        return {
            'ordered': ordered,
            'run': ordered,
            'excluded_count': 0,
            'median_gap': 0.0,
            'gap_threshold': 0.0,
            'largest_gap': float(np.max(gaps)) if gaps.size else 0.0,
        }
    # The additive term prevents a small number of pixels of perspective or
    # refinement noise from splitting a valid run; 2.5x rejects hardware gaps.
    gap_threshold = max(2.5 * median_gap, median_gap + 12.0)
    runs = []
    run = [ordered[0]]
    for previous, current in zip(ordered, ordered[1:]):
        if current - previous <= gap_threshold:
            run.append(current)
        else:
            runs.append(run)
            run = [current]
    runs.append(run)
    selected = max(
        runs,
        key=lambda candidate: (
            len(candidate),
            candidate[-1] - candidate[0] if len(candidate) > 1 else 0.0,
        ),
    )
    return {
        'ordered': ordered,
        'run': selected,
        'excluded_count': len(ordered) - len(selected),
        'median_gap': median_gap,
        'gap_threshold': gap_threshold,
        'largest_gap': float(np.max(gaps)) if gaps.size else 0.0,
    }


def _bounded_tick_extent(xs: list[float], width: int) -> tuple[int, int]:
    if not xs or width <= 0:
        return 0, width
    selection = _select_contiguous_tick_run(xs)
    ordered = selection['run'] or selection['ordered']
    if not ordered:
        return 0, width
    gap = float(selection['median_gap'])
    if gap <= 0.0:
        gap = max(8.0, width * 0.03)
    margin = max(8, int(round(2.0 * gap)))
    return int(np.floor(ordered[0] - margin)), int(np.ceil(ordered[-1] + margin))


def _spacing_metrics(xs: list[float]) -> dict:
    ordered = sorted({round(float(value), 4) for value in xs
                      if value is not None and np.isfinite(float(value))})
    gaps = np.diff(np.asarray(ordered, dtype=float))
    gaps = gaps[np.isfinite(gaps) & (gaps > 0.0)]
    if not gaps.size:
        return {
            'count': int(len(ordered)),
            'median': 0.0,
            'min': 0.0,
            'max': 0.0,
            'max_ratio': 0.0,
            'consistency': 1.0,
        }
    median = float(np.median(gaps))
    deviation = float(np.median(np.abs(gaps - median))) if median > 0 else 0.0
    return {
        'count': int(len(ordered)),
        'median': median,
        'min': float(np.min(gaps)),
        'max': float(np.max(gaps)),
        'max_ratio': float(np.max(gaps) / median) if median > 0 else 0.0,
        'consistency': float(np.clip(
            1.0 - deviation / median if median > 0 else 0.0,
            0.0,
            1.0,
        )),
    }


def _crop_y_range(scale: str,
                  split_result: dict,
                  result: dict,
                  rotated_height: int) -> tuple[int, int]:
    if scale == 'main':
        region = split_result.get('region_main', {})
        band = region.get('tick_band_global') or region.get('tick_band')
        y_offset = 0
    else:
        detection = result.get('vernier_band_detection') or {}
        y_offset = int(split_result.get('split_y', 0) or 0)
        band = None
        if detection.get('band_y1') is not None and detection.get('band_y2') is not None:
            band = (detection['band_y1'], detection['band_y2'])
        if band is None:
            region = split_result.get('region_vernier', {})
            band = region.get('tick_band_global') or region.get('tick_band')
            if region.get('tick_band_global') is not None:
                y_offset = 0
    if not band or len(band) != 2:
        return 0, rotated_height
    y1, y2 = int(round(float(band[0]))) + y_offset, int(round(float(band[1]))) + y_offset
    y1 = max(0, min(rotated_height, y1))
    y2 = max(y1 + 1, min(rotated_height, y2)) if rotated_height else 0
    if scale == 'vernier':
        # The detector's band may include the entire slider body on difficult
        # samples.  Review figures should expose the stroke-bearing portion,
        # not hardware below the scale.  Keep the seam-adjacent cap and bound
        # the displayed height relative to the accepted tick geometry.
        tick_ys = []
        for tick in result.get('vernier_ticks', []) or []:
            for key in ('y_start', 'y_end', 'y_mid'):
                try:
                    value = float(tick.get(key)) + y_offset
                except (TypeError, ValueError):
                    continue
                if np.isfinite(value):
                    tick_ys.append(value)
        if tick_ys:
            tick_top = max(0, int(np.floor(min(tick_ys))))
            tick_bottom = min(rotated_height, int(np.ceil(max(tick_ys))) + 8)
            y1 = max(y1, tick_top)
            y2 = min(y2, tick_bottom)
        max_height = max(120, int(round(rotated_height * 0.16)))
        if y2 - y1 > max_height:
            y2 = min(rotated_height, y1 + max_height)
    return y1, y2


def _draw_label(image: np.ndarray, text: str, origin: tuple[int, int], color=_TEXT) -> None:
    cv2.putText(image, str(text), origin, cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                color, 1, cv2.LINE_AA)


def _resize_crop(crop: np.ndarray, width: int, max_height: int = 220) -> np.ndarray:
    if crop is None or crop.size == 0:
        return np.zeros((max_height, width, 3), dtype=np.uint8)
    height, source_width = crop.shape[:2]
    target_width = max(1, int(width))
    natural_height = max(1, int(round(height * target_width / max(1, source_width))))
    # The scale bands are intentionally narrow.  A mild vertical display
    # enlargement keeps individual strokes inspectable without changing the
    # x-domain used by the curve panel below.
    target_height = min(max_height, max(120, natural_height))
    resized = cv2.resize(crop, (target_width, target_height), interpolation=cv2.INTER_AREA)
    canvas = np.full((target_height, width, 3), _BACKGROUND, dtype=np.uint8)
    x = max(0, (width - target_width) // 2)
    canvas[:target_height, x:x + target_width] = resized
    return canvas


def _map_content_x(x_local: float,
                   start: int,
                   end: int,
                   left: int = _CONTENT_LEFT,
                   right: int = _CONTENT_RIGHT) -> int:
    """Map one local curve x to the shared displayed content rectangle."""
    if end <= start:
        return int(left)
    ratio = (float(x_local) - float(start)) / max(1.0, float(end - start - 1))
    return int(round(left + float(np.clip(ratio, 0.0, 1.0)) * (right - left)))


def _shared_marker_geometry(start: int,
                            end: int,
                            tick_xs: list[float],
                            zero_x: float | None) -> tuple[list[int], int | None]:
    """Convert accepted local x positions to one shared screen geometry.

    The image and curve panels are different renderings of the same source
    interval.  Computing marker columns once prevents the two renderers from
    drifting when either panel's internal representation changes.
    """
    visible_ticks = []
    for value in tick_xs or []:
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(value) and start <= value < end:
            visible_ticks.append(value)
    screen_ticks = [
        _map_content_x(value, start, end)
        for value in visible_ticks
    ]
    screen_zero = None
    try:
        zero_value = float(zero_x) if zero_x is not None else None
    except (TypeError, ValueError):
        zero_value = None
    if zero_value is not None and np.isfinite(zero_value) and start <= zero_value < end:
        screen_zero = _map_content_x(zero_value, start, end)
    return screen_ticks, screen_zero


def _draw_image_content(crop: np.ndarray,
                        panel_width: int,
                        start: int,
                        end: int,
                        tick_xs: list[float],
                        zero_x: float | None,
                        shared_tick_screen_x: list[int] | None = None,
                        shared_zero_screen_x: int | None = None) -> tuple[np.ndarray, dict]:
    """Place image and accepted x markers in the same x-domain as the curve."""
    content_width = _CONTENT_RIGHT - _CONTENT_LEFT + 1
    crop_panel = _resize_crop(crop, content_width)
    panel = np.full((crop_panel.shape[0], panel_width, 3), _BACKGROUND, dtype=np.uint8)
    panel[:, _CONTENT_LEFT:_CONTENT_RIGHT + 1] = crop_panel
    if shared_tick_screen_x is None:
        shared_tick_screen_x, shared_zero_screen_x = _shared_marker_geometry(
            start, end, tick_xs, zero_x
        )
    tick_screen_x = list(shared_tick_screen_x)
    for px in tick_screen_x:
        cv2.line(panel, (px, 30), (px, panel.shape[0] - 1), _TICK, 1, cv2.LINE_AA)
    zero_in_panel = False
    zero_screen_x = shared_zero_screen_x
    if zero_screen_x is not None:
        cv2.line(panel, (zero_screen_x, 30),
                 (zero_screen_x, panel.shape[0] - 1), _ZERO, 2, cv2.LINE_AA)
        zero_in_panel = True
    return panel, {
        'image_content_x': [_CONTENT_LEFT, _CONTENT_RIGHT],
        'tick_screen_x_image': tick_screen_x,
        'zero_screen_x_image': zero_screen_x,
        'zero_in_image': zero_in_panel,
    }


def _curve_panel(curve: np.ndarray,
                 start: int,
                 end: int,
                 tick_xs: list[float],
                 zero_x: float | None,
                 width: int,
                 height: int,
                 shared_tick_screen_x: list[int] | None = None,
                 shared_zero_screen_x: int | None = None) -> tuple[np.ndarray, dict]:
    panel = np.full((height, width, 3), _BACKGROUND, dtype=np.uint8)
    left, right, top, bottom = _CONTENT_LEFT, _CONTENT_RIGHT, 30, height - 32
    cv2.rectangle(panel, (left, top), (right, bottom), (95, 95, 100), 1)
    start = max(0, min(start, len(curve)))
    end = max(start + 1, min(end, len(curve))) if len(curve) else 0
    view = curve[start:end] if end > start else np.zeros(1, dtype=float)
    max_value = _CURVE_Y_MAX
    points = []
    for index, value in enumerate(view):
        local_x = start + index
        x = _map_content_x(local_x, start, end, left, right)
        y = bottom - int(round(float(np.clip(value, 0.0, max_value)) / max_value * (bottom - top)))
        points.append((x, y))
    if len(points) > 1:
        cv2.polylines(panel, [np.asarray(points, dtype=np.int32)], False,
                      _CURVE, 1, cv2.LINE_AA)
    if shared_tick_screen_x is None:
        shared_tick_screen_x, shared_zero_screen_x = _shared_marker_geometry(
            start, end, tick_xs, zero_x
        )
    tick_screen_x = list(shared_tick_screen_x)
    for px in tick_screen_x:
        cv2.line(panel, (px, top), (px, bottom), _TICK, 1, cv2.LINE_AA)
    zero_in_panel = False
    zero_screen_x = shared_zero_screen_x
    if zero_screen_x is not None:
        cv2.line(panel, (zero_screen_x, top - 8),
                 (zero_screen_x, bottom), _ZERO, 2, cv2.LINE_AA)
        _draw_label(panel, 'ZERO line', (right - 96, 18), _ZERO)
        zero_in_panel = True
    _draw_label(panel, 'normalized response', (left, 18), _TEXT)
    _draw_label(panel, f'x={start}..{max(start, end - 1)}', (right - 130, height - 10), _MUTED)
    _draw_label(panel, '0', (28, bottom + 4), _MUTED)
    _draw_label(panel, f'{max_value:.1f}', (4, top + 4), _MUTED)
    return panel, {
        'curve_content_x': [left, right],
        'tick_screen_x_curve': tick_screen_x,
        'zero_screen_x_curve': zero_screen_x,
        'zero_in_curve': zero_in_panel,
        'curve_max': max_value,
        'curve_span': int(max(0, end - start)),
        'curve_line_thickness': 1,
    }


def _draw_shared_guides(output: np.ndarray,
                        image_height: int,
                        tick_screen_x: list[int],
                        zero_screen_x: int | None) -> None:
    """Connect the two panel coordinate frames across the separator labels."""
    if output is None or output.size == 0:
        return
    curve_label_top = min(output.shape[0] - 1, image_height + 30)
    guide_start = max(0, image_height - 1)
    for px in tick_screen_x or []:
        cv2.line(output, (int(px), guide_start), (int(px), curve_label_top),
                 (70, 105, 78), 1, cv2.LINE_AA)
    if zero_screen_x is not None:
        cv2.line(output, (int(zero_screen_x), guide_start),
                 (int(zero_screen_x), curve_label_top), _ZERO, 2, cv2.LINE_AA)


def render_review_figure(rotated_color: np.ndarray,
                         split_result: dict,
                         scale: str,
                         result: dict,
                         filename: str) -> tuple[np.ndarray, dict]:
    """Render one crop/curve audit figure from the rotated ROI."""
    if scale not in {'main', 'vernier'}:
        raise ValueError(f'Unsupported scale: {scale}')
    rotated = np.asarray(rotated_color)
    if rotated.ndim == 2:
        rotated = cv2.cvtColor(rotated, cv2.COLOR_GRAY2BGR)
    height, image_width = rotated.shape[:2]
    standardization = _standardization(result)
    width = int((standardization or {}).get('width', image_width) or image_width)
    x_offset = int((standardization or {}).get('x_offset', 0) or 0)
    domain = _curve_crop_range(
        scale, standardization, result, image_width
    )
    curve_start = int(domain['start'])
    curve_end = int(domain['end'])
    image_x1 = int(domain['image_x1'])
    image_x2 = int(domain['image_x2'])
    y1, y2 = _crop_y_range(scale, split_result, result, height)
    crop = rotated[y1:y2, image_x1:image_x2]

    standard_curves = (standardization or {}).get('curves', {})
    curve = _as_curve(standard_curves.get('normalized_response'), width)
    records = (standardization or {}).get('ticks', [])
    tick_xs = [
        x for x in (_tick_curve_x(tick, x_offset) for tick in records)
        if x is not None
    ]
    zero_x = None
    if scale == 'vernier':
        try:
            zero_x = float(result.get('zero_x')) - float(x_offset)
        except (TypeError, ValueError):
            zero_x = None
    shared_tick_screen_x, shared_zero_screen_x = _shared_marker_geometry(
        curve_start, curve_end, tick_xs, zero_x
    )
    panel_width = _PANEL_WIDTH
    image_panel, image_metadata = _draw_image_content(
        crop, panel_width, curve_start, curve_end, tick_xs, zero_x,
        shared_tick_screen_x, shared_zero_screen_x
    )
    title = f'{Path(filename).stem} | {scale} scale | rotated ROI crop'
    _draw_label(image_panel, title, (_CONTENT_LEFT, 22), _TEXT)
    curve_panel, curve_metadata = _curve_panel(
        curve, curve_start, curve_end, tick_xs, zero_x, panel_width, 250,
        shared_tick_screen_x, shared_zero_screen_x
    )
    if standardization is None:
        _draw_label(curve_panel, 'STANDARDIZATION UNAVAILABLE', (panel_width // 2 - 150, 145), _ZERO)
        _draw_label(curve_panel, 'No display-only curve was produced; no curve was fabricated.',
                    (panel_width // 2 - 285, 170), _MUTED)

    output = np.vstack([image_panel, curve_panel])
    _draw_shared_guides(
        output, image_panel.shape[0], shared_tick_screen_x,
        shared_zero_screen_x
    )
    source_span = int(image_x2 - image_x1)
    curve_span = int(curve_end - curve_start)
    if source_span != curve_span:
        raise ValueError(
            'review image/curve source spans differ: '
            f'image={source_span}, curve={curve_span}'
        )
    metadata = {
        'filename': filename,
        'scale': scale,
        'source': 'orient.rotated_color',
        'crop_x': [int(image_x1), int(image_x2)],
        'crop_y': [int(y1), int(y2)],
        # Both serialized source intervals use the same half-open [start,end)
        # convention.  ``curve_x_local`` is intentionally no longer an
        # inclusive endpoint pair.
        'curve_x_local': [int(curve_start), int(curve_end)],
        'display_domain': {'start': curve_start, 'end': curve_end},
        'tick_run': domain.get('tick_run', {}),
        'image_source_x': [image_x1, image_x2],
        'curve_source_x': [curve_start, curve_end],
        'source_span': source_span,
        'curve_span': curve_span,
        'display_crop_size': [int(image_panel.shape[1]), int(image_panel.shape[0])],
        'content_x': [_CONTENT_LEFT, _CONTENT_RIGHT],
        'shared_content_x': [_CONTENT_LEFT, _CONTENT_RIGHT],
        'x_offset': int(x_offset),
        'standardization_present': standardization is not None,
        'tick_count': len(records),
        'zero_x': zero_x,
        'zero_in_crop': bool(zero_x is not None and curve_start <= zero_x < curve_end),
        **image_metadata,
        **curve_metadata,
        'shared_tick_screen_x': list(shared_tick_screen_x),
        'shared_zero_screen_x': shared_zero_screen_x,
    }
    if standardization is None:
        metadata['error'] = 'standardization_unavailable'
    classification = (standardization or {}).get('classification', {})
    formal_tick_count = int(
        classification.get('formal_tick_count', len(result.get('vernier_ticks', []) or []))
        or 0
    )
    display_tick_count = int(
        classification.get('display_tick_count', len(records))
        or 0
    )
    if formal_tick_count > 0:
        display_coverage = float(display_tick_count) / float(formal_tick_count)
    else:
        display_coverage = 0.0
    if standardization is None or display_tick_count == 0:
        standardization_status = 'unavailable'
    elif display_tick_count < 0.90 * max(1, formal_tick_count):
        standardization_status = 'partial'
    else:
        standardization_status = 'observed_complete'
    formal_records = (
        result.get('vernier_ticks')
        or result.get('main_ticks')
        or result.get('ticks')
        or []
    )
    if formal_tick_count == 0 and formal_records:
        formal_tick_count = len(formal_records)
        display_coverage = (
            float(display_tick_count) / float(formal_tick_count)
            if formal_tick_count else 0.0
        )
    raw_acceptance_status = str(
        classification.get('acceptance_status')
        or ('unavailable' if standardization is None else standardization_status)
    )
    visible_tick_xs = [
        float(x) for x in tick_xs if curve_start <= float(x) < curve_end
    ]
    domain_spacing = _spacing_metrics(visible_tick_xs)
    if standardization is None or not visible_tick_xs:
        acceptance_status = 'unavailable'
    # A single missed main-scale tick produces roughly 2x the median gap;
    # accept that as a partial observation, while retaining larger blanks as
    # an irregular-spacing warning.
    elif domain_spacing['max_ratio'] > 2.25:
        acceptance_status = 'irregular_spacing'
    elif (
        scale == 'main'
        and domain_spacing['count'] >= max(
            6, int(round(0.50 * max(1, formal_tick_count)))
        )
        and domain_spacing['max_ratio'] <= 2.25
    ):
        # The raw candidate list may contain a distant hardware/blank-tail
        # tick or one missed line.  Assess the visible periodic run separately
        # while preserving the raw warning.
        acceptance_status = 'complete'
    elif len(visible_tick_xs) < 0.90 * max(1, formal_tick_count):
        acceptance_status = 'partial'
    else:
        acceptance_status = raw_acceptance_status
    metadata.update({
        'formal_tick_count': formal_tick_count,
        'display_tick_count': display_tick_count,
        'display_coverage': float(display_coverage),
        'display_spacing_median': float(
            classification.get('display_spacing_median', 0.0) or 0.0
        ),
        'display_min_gap': float(
            classification.get('display_min_gap', 0.0) or 0.0
        ),
        'display_max_gap': float(
            classification.get('display_max_gap', 0.0) or 0.0
        ),
        'standardization_status': standardization_status,
        'acceptance_status': acceptance_status,
        'raw_acceptance_status': raw_acceptance_status,
        'domain_tick_count': domain_spacing['count'],
        'domain_spacing_median': domain_spacing['median'],
        'domain_spacing_min': domain_spacing['min'],
        'domain_spacing_max': domain_spacing['max'],
        'domain_spacing_max_ratio': domain_spacing['max_ratio'],
        'domain_spacing_consistency': domain_spacing['consistency'],
        'binary_evidence_available': bool(
            classification.get('binary_evidence_available', False)
        ),
        'direction_trace_coverage': float(
            classification.get('direction_trace_coverage', 0.0) or 0.0
        ),
        'trace_support_coverage': float(
            classification.get('trace_support_coverage', 0.0) or 0.0
        ),
        'binary_support_coverage': float(
            classification.get('binary_support_coverage', 0.0) or 0.0
        ),
        'spacing_consistency': float(
            classification.get('spacing_consistency', 0.0) or 0.0
        ),
        'spacing_max_ratio': float(
            classification.get('spacing_max_ratio', 0.0) or 0.0
        ),
        'cluster_balance': float(
            classification.get('cluster_balance', 0.0) or 0.0
        ),
        'untraced_fallback_count': int(
            classification.get('untraced_fallback_count', 0) or 0
        ),
        'untraced_fallback_ratio': float(
            classification.get('untraced_fallback_ratio', 0.0) or 0.0
        ),
        'response_kernel': str(
            classification.get('response_kernel', 'unknown')
        ),
    })
    return output, metadata


def export_review_figures(input_dir: Path,
                          output_dir: Path,
                          filenames: list[str]) -> dict:
    """Run detailed mode and export one main and one vernier audit PNG per file."""
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    for index, filename in enumerate(filenames, start=1):
        sample = {'filename': filename, 'reading_mm': None, 'error': None, 'figures': {}}
        try:
            pipeline = CaliperPipeline(fast_mode=False)
            result = pipeline.run(read_image(input_dir / filename))
            rotated = pipeline.step_results['orient']['rotated_color']
            split = pipeline.step_results['split']
            for scale, result_key in (('main', 'main'), ('vernier', 'vernier')):
                scale_result = pipeline.step_results.get(result_key, {})
                figure, metadata = render_review_figure(
                    rotated, split, scale, scale_result, filename
                )
                output_name = f'{index:02d}_{Path(filename).stem}_{scale}_review.png'
                write_image(output_dir / output_name, figure)
                sample['figures'][scale] = {'file': output_name, **metadata}
            sample['reading_mm'] = result.total
        except Exception as exc:
            sample['error'] = str(exc)
        samples.append(sample)
    report = {'samples': samples}
    (output_dir / 'standardization_review_summary.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'tupian')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--image', dest='filenames', action='append', required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    report = export_review_figures(args.input_dir, args.output_dir, args.filenames)
    print(f'Exported {len(report["samples"])} samples to {args.output_dir}')


if __name__ == '__main__':
    main()
