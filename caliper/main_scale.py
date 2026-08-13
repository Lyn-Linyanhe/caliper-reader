"""Step 3: main-scale tick detection and OCR geometry.

This module detects real main-scale ticks, recovers connected upper extents,
and refines x positions.  Main-scale OCR is deliberately performed later in
``merger.py`` because it needs the vernier zero position; this module returns
the tick geometry and an empty ``main_digits`` list.
"""

import cv2
import numpy as np
from typing import List
from .utils import (
    _tick_row_threshold,
    contiguous_segments,
    dedupe_ticks_by_relative_gap,
    extract_ticks_from_binary,
    refine_tick_x_subpixel,
)
from .config import config
from .standardization import build_standardization_result


def recognize_main_scale(region: dict,
                          color_region: np.ndarray = None,
                          make_debug: bool = True) -> dict:
    """
    主尺识别主函数

    Args:
        region:       主尺区域 dict {image, binary, y_offset, height}
        color_region: 对应的彩色区域（用于 OCR）

    Returns:
        dict with keys:
            'main_ticks':   刻度线列表
            'main_gap':     主尺间距（像素）
            'main_digits':  空列表（正式 OCR 在 merger.py 定向执行）
            'main_reading': 0.0 占位（正式整数在 merger.py 合并阶段计算）
            'vis_ticks':    刻度线可视化
    """
    img = region['image']
    h, w = img.shape

    # ── 1. 自适应二值化（比 OTSU 更鲁棒，避免低对比度时全部消失）──
    binary = _foreground_binary_from_region(region.get('binary'), img)
    if binary is None:
        binary = cv2.adaptiveThreshold(
            img, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=config.main_scale.adaptive_block_size,
            C=config.main_scale.adaptive_C
        )
    # 回退：自适应阈值得到的前景太少（全部淹没），改用 OTSU
    if np.sum(binary > 0) < w * h * 0.03:
        _, binary = cv2.threshold(img, 0, 255,
                                   cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    region['binary'] = binary

    band_y1, band_y2 = region.get('tick_band', (0, h))
    band_y1 = max(0, min(h - 1, int(band_y1)))
    band_y2 = max(band_y1 + 1, min(h, int(band_y2)))
    vproj = np.sum(binary[band_y1:band_y2, :] > 0, axis=0).astype(float)
    if np.max(vproj) > 0:
        vproj_norm = vproj / np.max(vproj)
    else:
        vproj_norm = vproj

    coarse_main_xs = _find_threshold_segments(
        vproj_norm,
        threshold_factor=config.main_scale.peak_threshold_factor,
    )
    if len(coarse_main_xs) < config.main_scale.min_tick_count:
        return _empty_main_result()

    # ── 2.5 等间距补全 & 校验 ──
    # ── 3. 精密提取刻线 ──
    tick_band_binary = binary[band_y1:band_y2, :]
    main_ticks = extract_ticks_from_binary(
        tick_band_binary, coarse_main_xs,
        long_tick_factor=config.main_scale.long_tick_factor,
        recover_short_ticks=config.main_scale.short_tick_recovery_enabled,
        short_tick_min_contiguous_ratio=(
            config.main_scale.short_tick_min_contiguous_ratio),
        short_tick_min_foreground_factor=(
            config.main_scale.short_tick_min_foreground_factor),
        short_tick_period_tolerance=config.main_scale.short_tick_period_tolerance)
    if len(main_ticks) < config.main_scale.min_tick_count:
        return _empty_main_result()
    ref_y2 = max(1, band_y2 - 2)
    ref_y1 = max(band_y1, ref_y2 - 10)
    for tick in main_ticks:
        projection_x = min(coarse_main_xs, key=lambda x: abs(int(x) - int(tick['x'])))
        tick['x_projection'] = int(projection_x)
        tick['x_precise'] = refine_tick_x_subpixel(
            img, tick['x_projection'], ref_y1, ref_y2
        )
        tick['x'] = int(round(tick['x_precise']))
        tick['y_start'] += band_y1
        tick['y_end'] += band_y1
        tick['y_mid'] += band_y1

    # Keep the split-adjacent band for x-position detection, then recover the
    # connected upper extent from the full main region for length/OCR geometry.
    main_ticks = _recover_main_tick_extents_from_full_binary(binary, main_ticks)
    main_ticks = dedupe_ticks_by_relative_gap(main_ticks, gap_ratio=0.45)
    main_ticks.sort(key=lambda t: t['x'])
    main_xs = np.array([t['x'] for t in main_ticks], dtype=int)
    main_gap = float(np.median(np.diff([t['x'] for t in main_ticks])))

    # v6.5: OCR 数字识别已迁移到 merger（在拿到 zero_x 后定向识别）
    # OCR is handled later in merger after zero_x is known. Keep main_digits empty.
    # 避免 pipeline.py 报错。
    region['main_ticks'] = main_ticks

    # ── 4. 主尺读数（合并阶段计算）──
    main_reading = 0.0

    # ── 可视化 ──
    standardization = None
    if make_debug:
        support = _seam_anchored_support(binary, band_y1, band_y2)
        standardization = _build_main_standardization(
            w, vproj_norm, support, main_ticks
        )
    vis_ticks = _draw_main_ticks(
        region, binary, main_ticks, vproj_norm,
        coarse_main_xs, main_xs, standardization=standardization
    ) if make_debug else None

    return {
        'main_ticks': main_ticks,
        'main_gap': main_gap,
        'main_digits': [],  # v6.5: 留空，由 merger 定向填充
        'main_reading': main_reading,
        'vis_ticks': vis_ticks,
        'standardization': standardization,
    }


# ═══════════════════════════ 内部函数 ═══════════════════════════

def find_nearest_cm_digit_region(main_ticks: List[dict],
                                      main_gap: float,
                                      zero_x: float,
                                      binary: np.ndarray,
                                      vertical_expand_gaps: float = 0.0,
                                      prefer_long_ticks: bool = False) -> tuple:
    if not main_ticks or main_gap <= 0 or zero_x <= 0 or binary is None:
        return None, 0, 0

    H, W = binary.shape[:2]

    y_top_tick = _select_ocr_anchor_tick_top(
        main_ticks, prefer_long_ticks=prefer_long_ticks
    )
    if y_top_tick is None:
        return None, 0, 0

    expand_y = max(0, int(round(main_gap * vertical_expand_gaps)))
    y_top = max(0, y_top_tick - int(4 * main_gap) - expand_y)
    y_bottom = max(y_top + 8, y_top_tick - int(1 * main_gap) + expand_y)
    y_bottom = min(H, y_bottom)

    cm_px = int(main_gap * 10)
    x_left = max(0, int(zero_x - 1.7 * cm_px))
    x_right = min(W, int(zero_x + 0.4 * cm_px))
    if x_right - x_left < 8:
        return None, 0, 0

    binary_crop = binary[y_top:y_bottom, x_left:x_right].copy()
    return binary_crop, x_left, y_top


def _recover_main_tick_extents_from_full_binary(binary: np.ndarray,
                                                 ticks: List[dict]) -> List[dict]:
    """Recover connected tick height outside the narrow split-adjacent band."""
    if binary is None or binary.ndim != 2 or not ticks:
        return ticks
    h, w = binary.shape[:2]
    recovered = []
    for tick in ticks:
        out = dict(tick)
        x = int(round(float(out.get('x', 0))))
        y_start = int(out.get('y_start', 0))
        y_end = int(out.get('y_end', y_start))
        if not (0 <= x < w and 0 <= y_start <= y_end < h):
            recovered.append(out)
            continue

        strip = binary[:, max(0, x - 3):min(w, x + 4)]
        col = np.sum(strip, axis=1)
        foreground_rows = np.flatnonzero(col > _tick_row_threshold(col))
        segments = contiguous_segments(foreground_rows, min_len=5)
        connected = [
            segment for segment in segments
            if segment[1] >= y_start and segment[0] <= y_end
        ]
        if connected:
            top, bottom = max(connected, key=lambda segment: segment[1] - segment[0])
            if bottom - top > y_end - y_start:
                out['y_start'] = int(top)
                out['y_end'] = int(bottom)
                out['y_mid'] = int((top + bottom) / 2)
                out['length'] = int(bottom - top)
        recovered.append(out)

    lengths = [float(tick.get('length', 0)) for tick in recovered]
    if lengths:
        median_length = float(np.median(lengths))
        for tick in recovered:
            tick['is_long'] = bool(
                tick.get('length', 0) > median_length * config.main_scale.long_tick_factor
            )
    return recovered


def _select_ocr_anchor_tick_top(main_ticks: List[dict],
                                prefer_long_ticks: bool = False) -> int:
    y_starts = [tick['y_start'] for tick in main_ticks if 'y_start' in tick]
    if len(y_starts) < 3:
        return None
    long_starts = [
        tick['y_start'] for tick in main_ticks
        if tick.get('is_long') and 'y_start' in tick
    ]
    if prefer_long_ticks and len(long_starts) >= 3:
        # A lower quartile follows the upper edge of major ticks while
        # resisting isolated short/partially recovered marks.
        return int(round(float(np.percentile(long_starts, 25))))
    return int(round(float(np.percentile(y_starts, 85))))


def _find_threshold_segments(signal: np.ndarray,
                             threshold_factor: float = 0.3) -> np.ndarray:
    if signal is None or len(signal) == 0:
        return np.array([], dtype=int)
    mu = float(np.mean(signal))
    sigma = float(np.std(signal))
    threshold = max(mu + threshold_factor * sigma, 0.02)
    mask = np.asarray(signal) > threshold
    xs = []
    start = None
    for i, value in enumerate(mask):
        if value and start is None:
            start = i
        elif not value and start is not None:
            xs.append((start + i - 1) // 2)
            start = None
    if start is not None:
        xs.append((start + len(mask) - 1) // 2)
    return np.array(xs, dtype=int)


def _foreground_binary_from_region(binary: np.ndarray, gray: np.ndarray) -> np.ndarray:
    if binary is None or binary.size == 0:
        return None
    if binary.shape[:2] != gray.shape[:2]:
        return None
    out = binary.copy()
    if out.dtype != np.uint8:
        out = out.astype(np.uint8)
    _, out = cv2.threshold(out, 127, 255, cv2.THRESH_BINARY)
    if float(np.mean(out > 0)) > 0.5:
        out = cv2.bitwise_not(out)
    if np.sum(out > 0) < gray.shape[0] * gray.shape[1] * 0.03:
        return None
    return out


def _seam_anchored_support(binary: np.ndarray,
                           band_y1: int,
                           band_y2: int) -> np.ndarray:
    band = binary[band_y1:band_y2, :] > 0
    h, w = band.shape[:2]
    support = np.zeros(w, dtype=float)
    near_edge = max(8, min(18, h // 4))
    for x in range(w):
        rows = np.mean(band[:, max(0, x - 1):min(w, x + 2)], axis=1) >= 0.20
        runs = []
        start = None
        gaps = 0
        for y, active in enumerate(rows):
            if active:
                if start is None:
                    start = y
                gaps = 0
            elif start is not None and gaps < 1:
                gaps += 1
            elif start is not None:
                runs.append((start, y - gaps))
                start = None
                gaps = 0
        if start is not None:
            runs.append((start, h - 1 - gaps))
        valid = [end - begin + 1 for begin, end in runs if end >= h - near_edge]
        if valid:
            support[x] = max(valid)
    return support


def _standardize_tick_response(width: int,
                               ticks: List[dict],
                               support: np.ndarray) -> np.ndarray:
    response = np.zeros(max(0, int(width)), dtype=float)
    if response.size == 0 or not ticks:
        return response
    values = []
    centers = []
    for tick in ticks:
        x = int(tick.get('x_projection', tick.get('x', 0)))
        if not 0 <= x < support.size:
            continue
        values.append(float(np.max(support[max(0, x - 2):min(support.size, x + 3)])))
        centers.append(x)
    if not values:
        return response
    long_threshold = (float(np.percentile(values, 75)) +
                      float(np.percentile(values, 85))) / 2.0
    for x, value in zip(centers, values):
        amplitude = 1.5 if value >= long_threshold else 1.0
        for offset in range(-3, 4):
            px = x + offset
            if 0 <= px < response.size:
                response[px] = max(
                    response[px],
                    amplitude * np.exp(-0.5 * (offset / 1.1) ** 2),
                )
    return response


def _build_main_standardization(width: int,
                                vproj_norm: np.ndarray,
                                support: np.ndarray,
                                ticks: List[dict]) -> dict:
    """Build display-only standardization evidence from accepted main ticks."""
    values = []
    for tick in ticks or []:
        x = int(round(float(tick.get('x_projection', tick.get('x', 0)))))
        if support is None or not 0 <= x < len(support):
            continue
        window = support[max(0, x - 2):min(len(support), x + 3)]
        value = float(np.max(window)) if len(window) else 0.0
        if np.isfinite(value):
            values.append((tick, value))

    positive = np.asarray(
        [value for _tick, value in values if value > 0.0],
        dtype=float,
    )
    classification = {
        'mode': 'unknown',
        'centers': [],
        'counts': [],
        'separation': 0.0,
        'threshold': None,
    }
    labels = np.zeros(len(values), dtype=int)
    if positive.size >= 3:
        low = float(np.percentile(positive, 25))
        high = float(np.percentile(positive, 75))
        median = float(np.median(positive))
        separation = (high - low) / max(median, 1.0)
        if high > low and separation >= 0.20:
            threshold = (float(np.percentile(positive, 75)) +
                         float(np.percentile(positive, 85))) / 2.0
            labels = np.asarray(
                [1 if value >= threshold else 0 for _tick, value in values],
                dtype=int,
            )
            counts = np.bincount(labels, minlength=2)
            if int(np.min(counts)) >= 2:
                centers = [
                    float(np.mean([value for (_tick, value), label
                                   in zip(values, labels) if label == index]))
                    for index in (0, 1)
                ]
                classification.update({
                    'mode': 'two_clusters',
                    'centers': centers,
                    'counts': [int(counts[0]), int(counts[1])],
                    'separation': float((centers[1] - centers[0]) /
                                        max(centers[0], 1.0)),
                    'threshold': float(threshold),
                })
        elif median > 0.0:
            classification.update({
                'mode': 'single',
                'centers': [median],
                'counts': [int(positive.size)],
            })

    response = _standardize_tick_response(width, ticks, support)
    median_support = float(np.median(positive)) if positive.size else 0.0
    records = []
    value_by_tick = {id(tick): value for tick, value in values}
    threshold = classification.get('threshold')
    for tick in ticks or []:
        value = float(value_by_tick.get(id(tick), 0.0))
        x_projection = float(tick.get('x_projection', tick.get('x', 0)))
        x = int(round(x_projection))
        normalized_value = float(response[x]) if 0 <= x < len(response) else 0.0
        tick_class = 'unknown'
        if classification['mode'] == 'two_clusters' and threshold is not None:
            tick_class = 'long' if value >= threshold else 'short'
        quality = (value / median_support) if median_support > 0.0 else 0.0
        records.append({
            'x': float(tick.get('x', x_projection)),
            'x_projection': x_projection,
            'measured_length': float(tick.get('length', 0.0)),
            'support_value': value,
            'normalized_value': normalized_value,
            'class': tick_class,
            'quality': float(np.clip(quality, 0.0, 2.0)),
        })
    return build_standardization_result(
        width, 0, vproj_norm, support, response, records, classification
    )


def _draw_projection_panel(signal: np.ndarray,
                           width: int,
                           title: str,
                           color: tuple,
                           candidates: List[int] = None,
                           height: int = 180) -> np.ndarray:
    plot = np.full((height, width, 3), (28, 28, 28), dtype=np.uint8)
    top = 28
    bottom = height - 18
    value = np.asarray(signal, dtype=float)
    if value.size:
        max_value = float(np.max(value))
        normalized = value / max_value if max_value > 0 else value
    else:
        normalized = value
    normalized = np.clip(normalized, 0.0, 1.5)
    if normalized.size > 1:
        points = np.column_stack((
            np.arange(min(width, normalized.size)),
            bottom - (normalized[:width] / 1.5 * (bottom - top)).astype(int),
        )).astype(np.int32)
        cv2.polylines(plot, [points], False, color, 2, cv2.LINE_AA)
    cv2.line(plot, (0, bottom), (width - 1, bottom), (70, 70, 75), 1)
    if candidates:
        for x in candidates:
            if 0 <= x < width:
                cv2.line(plot, (x, top), (x, bottom), (0, 220, 100), 1)
    cv2.putText(plot, title, (10, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
    cv2.putText(plot, '0', (3, bottom),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 145), 1)
    cv2.putText(plot, '1.0', (3, bottom - int((bottom - top) / 1.5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 145), 1)
    cv2.putText(plot, '1.5', (3, top + 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 145), 1)
    return plot


def find_digit_cc_candidates(binary_crop: np.ndarray,
                              x_offset: int, y_offset: int,
                              zero_x: float = None,
                              min_area: int = 700,
                              max_area: int = 3000,
                             min_aspect: float = 0.6,
                             max_aspect: float = 3.5) -> list:
    """Return all plausible digit connected components in the OCR crop."""
    if binary_crop is None or binary_crop.size == 0:
        return []

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(binary_crop, connectivity=8)
    if num_labels < 2:
        return []

    H, W = binary_crop.shape
    dynamic_min_area = max(250, int(H * H * 0.09))
    effective_min_area = min(min_area, dynamic_min_area)
    dynamic_max_area = max(max_area, int(H * H * 0.20))
    candidates = []
    for j in range(1, num_labels):
        x = int(stats[j, cv2.CC_STAT_LEFT])
        y = int(stats[j, cv2.CC_STAT_TOP])
        w = int(stats[j, cv2.CC_STAT_WIDTH])
        h = int(stats[j, cv2.CC_STAT_HEIGHT])
        area = int(stats[j, cv2.CC_STAT_AREA])
        if area < effective_min_area or area > dynamic_max_area:
            continue
        if w < 3 or h < 5:
            continue
        aspect = h / max(w, 1)
        if aspect < min_aspect or aspect > max_aspect:
            continue

        y_center_ratio = (y + h / 2) / H
        x_center_ratio = (x + w / 2) / W
        confidence = (
            0.4 * min(1.0, area / 200) +
            0.3 * (1.0 - abs(aspect - 1.5) / 2.0) +
            0.3 * y_center_ratio
        )
        confidence = max(0.0, min(1.0, confidence))

        pad = 2
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(W, x + w + pad)
        y2 = min(H, y + h + pad)
        bbox = (x1 + x_offset, y1 + y_offset, x2 + x_offset, y2 + y_offset)
        candidates.append({
            'idx': j,
            'x': x,
            'y': y,
            'w': w,
            'h': h,
            'area': area,
            'aspect': aspect,
            'y_ratio': y_center_ratio,
            'x_ratio': x_center_ratio,
            'center_x': x + w / 2 + x_offset,
            'bbox': bbox,
            'confidence': confidence,
            'digit_crop': binary_crop[y1:y2, x1:x2],
        })

    return sorted(candidates, key=lambda c: c['center_x'])






def _draw_main_ticks(region: dict,
                      binary: np.ndarray,
                      main_ticks: List[dict],
                      vproj: np.ndarray,
                      coarse_peaks: np.ndarray,
                      refined_peaks: np.ndarray,
                      standardization: dict = None) -> np.ndarray:
    """绘制主尺刻度线检测结果 — 灰度底图 + 右侧二值图小窗"""
    img = region['image']
    h, w = img.shape

    # 主图：增强灰度图上叠加刻线
    vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    band_y1, band_y2 = region.get('tick_band', (0, h))
    band_y1 = max(0, min(h - 1, int(band_y1)))
    band_y2 = max(band_y1 + 1, min(h, int(band_y2)))
    overlay = vis.copy()
    cv2.rectangle(overlay, (0, band_y1), (w - 1, band_y2 - 1), (0, 120, 60), -1)
    vis = cv2.addWeighted(vis, 0.86, overlay, 0.14, 0)
    cv2.line(vis, (0, band_y1), (w - 1, band_y1), (0, 180, 80), 1)
    cv2.line(vis, (0, band_y2 - 1), (w - 1, band_y2 - 1), (0, 180, 80), 1)

    # 画刻度线
    for t in main_ticks:
        if t.get('is_recovered_short', False):
            color = (0, 140, 255)
        else:
            color = (0, 255, 100) if t.get('is_long', False) else (0, 180, 80)
        thickness = 3 if t.get('is_long', False) else 2
        cv2.line(vis, (t['x'], t['y_start']), (t['x'], t['y_end']), color, thickness)
        if t.get('is_long', False):
            cv2.circle(vis, (t['x'], t['y_mid']), 5, (255, 255, 0), -1)
    if any(t.get('is_recovered_short', False) for t in main_ticks):
        cv2.putText(vis, "orange = recovered short tick", (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 140, 255), 1)

    # ── 右侧二值图小窗（显示检测器实际看到的二值图）──
    bin_thumb_w = max(50, w // 4)
    bin_thumb_h = int(h * bin_thumb_w / w)
    bin_thumb = cv2.resize(binary, (bin_thumb_w, bin_thumb_h), interpolation=cv2.INTER_AREA)
    bin_thumb_3ch = cv2.cvtColor(bin_thumb, cv2.COLOR_GRAY2BGR)
    # 放在右下角
    bx, by = w - bin_thumb_w, h - bin_thumb_h
    vis[by:by + bin_thumb_h, bx:bx + bin_thumb_w] = bin_thumb_3ch
    cv2.rectangle(vis, (bx, by), (bx + bin_thumb_w, by + bin_thumb_h), (255, 255, 255), 1)
    cv2.putText(vis, "BIN", (bx + 3, by + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

    # 下方追加投影图
    curves = (standardization or {}).get('curves', {})
    support = curves.get('support')
    if support is None:
        support = _seam_anchored_support(binary, band_y1, band_y2)
    response = curves.get('normalized_response')
    if response is None:
        response = _standardize_tick_response(w, main_ticks, support)
    candidates = [int(t.get('x_projection', t.get('x', 0))) for t in main_ticks]
    raw_panel = _draw_projection_panel(
        vproj, w, 'Raw vertical projection', (110, 100, 70)
    )
    support_panel = _draw_projection_panel(
        support, w, 'Seam-anchored vertical support', (80, 220, 255), candidates
    )
    classification = (standardization or {}).get('classification', {})
    mode = classification.get('mode', 'unknown')
    response_title = (
        'Standardized tick response '
        f'(mode={mode}; short=1.0, long=1.5)'
    )
    response_panel = _draw_projection_panel(
        response, w, response_title, (255, 190, 60)
    )
    panel_gap = 10
    panels_h = raw_panel.shape[0] + support_panel.shape[0] + response_panel.shape[0] + panel_gap * 2
    out = np.zeros((h + panels_h + panel_gap, w, 3), dtype=np.uint8)
    out[:] = (30, 30, 35)
    out[:h, :w] = vis
    y0 = h + panel_gap
    out[y0:y0 + raw_panel.shape[0], :w] = raw_panel
    y0 += raw_panel.shape[0] + panel_gap
    out[y0:y0 + support_panel.shape[0], :w] = support_panel
    y0 += support_panel.shape[0] + panel_gap
    out[y0:y0 + response_panel.shape[0], :w] = response_panel

    cv2.putText(out, "STEP 3: Main Scale Ticks (gray + binary overlay)", (5, out.shape[0] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 125), 1)

    return out


def _empty_main_result() -> dict:
    empty_img = np.zeros((100, 300, 3), dtype=np.uint8)
    return {
        'main_ticks': [],
        'main_gap': 0.0,
        'main_digits': [],
        'main_reading': 0.0,
        'vis_ticks': empty_img,
        'standardization': None,
    }
