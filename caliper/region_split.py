"""Step 2: split the main-scale and vernier-scale regions.

The active path keeps thin vertical foreground components with a vertical
opening, builds row support from those components, and first estimates the
seam from component endpoints.  A valley bounded by two supported tick bands
is the fallback; a physical height ratio is the final fallback.  The old
gradient/closing/candidate-scan descriptions are historical configuration
notes, not executable branches.
"""

import cv2
import numpy as np

from .config import config


def split_scales(rotated_gray: np.ndarray,
                  rotated_binary: np.ndarray = None,
                  rotated_color: np.ndarray = None,
                  make_debug: bool = True) -> dict:
    """沿 y 轴切分主尺和游标尺区域"""
    h, w = rotated_gray.shape

    # 准备二值图（验证刻线密度用）
    if rotated_binary is None:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(rotated_gray)
        _, binary = cv2.threshold(enhanced, 0, 255,
                                  cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        binary = rotated_binary

    band_info = _analyze_horizontal_tick_bands(rotated_gray, binary)
    split_y, seam_info = (( _find_component_endpoint_seam(band_info, h))
                          if config.region_split.seam_use_component_endpoints else (None, {}))
    seam_source = 'component_endpoints'
    if split_y is None:
        split_y = _split_from_tick_band_valley(band_info)
        seam_source = 'projection_valley'

    # ── 最终回退（基于物理先验：主尺约占ROI高度的60%）──
    if split_y is None:
        split_y = int(h * config.region_split.fallback_split_ratio)
        seam_source = 'physical_ratio'

    # ── 游标区域高度校验：不能太小（至少占ROI的 min_ratio）──
    min_vernier_h = int(h * config.region_split.min_vernier_height_ratio)
    if h - split_y < min_vernier_h:
        split_y = h - min_vernier_h

    band_info = _analyze_horizontal_tick_bands(
        rotated_gray, binary, split_y, projection=band_info
    )
    endpoint_bands = _tick_bands_from_component_endpoints(band_info, split_y, h, seam_info)
    main_band = endpoint_bands.get('main_tick_band') or band_info.get(
        'main_tick_band', (max(0, split_y - max(24, h // 3)), split_y)
    )
    vernier_band = endpoint_bands.get('vernier_tick_band') or band_info.get(
        'vernier_tick_band', (split_y, min(h, split_y + max(24, h // 4)))
    )
    band_info.update(seam_info)
    band_info.update(endpoint_bands)

    # ── 切分 ──
    img_upper = rotated_gray[:split_y, :]
    img_lower = rotated_gray[split_y:, :]
    bin_upper = binary[:split_y, :]
    bin_lower = binary[split_y:, :]

    main_band_local = (max(0, main_band[0]), min(split_y, main_band[1]))
    vernier_band_local = (
        max(0, vernier_band[0] - split_y),
        min(h - split_y, vernier_band[1] - split_y),
    )
    region_main = {
        'image': img_upper, 'binary': bin_upper,
        'y_offset': 0, 'height': split_y,
        'tick_band': main_band_local,
        'tick_band_global': main_band,
    }
    region_vernier = {
        'image': img_lower, 'binary': bin_lower,
        'y_offset': split_y, 'height': h - split_y,
        'tick_band': vernier_band_local,
        'tick_band_global': vernier_band,
    }

    split_vis = None
    if make_debug:
        split_vis = _make_split_vis(rotated_color if rotated_color is not None
                                      else rotated_gray,
                                      rotated_gray, binary, split_y, band_info)

    return {
        'region_main': region_main,
        'region_vernier': region_vernier,
        'split_y': split_y,
        'seam_source': seam_source,
        'tick_bands': band_info,
        'split_vis': split_vis,
    }


def _foreground_binary(binary: np.ndarray, gray: np.ndarray = None) -> np.ndarray:
    if binary is None:
        if gray is None:
            return None
        _, fg = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return fg
    fg = binary.copy()
    if float(np.mean(fg > 0)) > 0.5:
        fg = cv2.bitwise_not(fg)
    return fg


def _split_from_tick_band_valley(band_info: dict):
    valley = band_info.get('tick_band_valley') if band_info else None
    response = band_info.get('row_projection_smooth') if band_info else None
    if response is None or not valley:
        return None

    valley_y1, valley_y2 = int(valley[0]), int(valley[1])
    y1 = max(0, valley_y1)
    y2 = min(len(response), valley_y2)
    if y2 <= y1:
        return None
    return y1 + int(np.argmin(response[y1:y2]))


def _find_component_endpoint_seam(band_info: dict, full_h: int):
    if not band_info:
        return None, {}
    starts = band_info.get('component_start_response')
    ends = band_info.get('component_end_response')
    if starts is None or ends is None:
        return None, {}

    lo = max(0, int(full_h * 0.34))
    hi = min(full_h, int(full_h * 0.75))
    if hi - lo < 20:
        return None, {}

    peak_distance = max(12, min(28, int(full_h * 0.025)))
    # Consecutive scale bands can be separated by a short physical gap after
    # rotation.  At 957 px high, the former 2.5% rule produced 23 px and
    # rejected an observed 24 px main-end/vernier-start pair.  Keep the
    # distance bounded so unrelated component groups remain ineligible.
    max_gap = max(24, min(36, int(round(full_h * 0.035))))
    end_peaks = _profile_peaks(ends, lo, hi, peak_distance)
    start_peaks = _profile_peaks(starts, lo, hi, peak_distance)
    if not end_peaks or not start_peaks:
        return None, {}

    end_max = max(float(ends[y]) for y in end_peaks)
    start_max = max(float(starts[y]) for y in start_peaks)
    best = None
    for end_y in end_peaks:
        for start_y in start_peaks:
            gap = abs(start_y - end_y)
            if gap > max_gap:
                continue
            end_score = float(ends[end_y]) / max(end_max, 1e-6)
            start_score = float(starts[start_y]) / max(start_max, 1e-6)
            score = end_score * start_score * (1.0 - 0.12 * gap / max_gap)
            if best is None or score > best[0]:
                best = (score, end_y, start_y)

    if best is None:
        return None, {}
    score, end_y, start_y = best
    if score < 0.18:
        return None, {}
    return int(end_y), {
        'endpoint_score': float(score),
        'main_end_y': int(end_y),
        'vernier_start_y': int(start_y),
    }


def _profile_peaks(profile: np.ndarray, lo: int, hi: int, min_distance: int):
    values = np.asarray(profile, dtype=float)
    if values.size == 0 or hi <= lo:
        return []
    threshold = max(0.5, float(np.max(values[lo:hi])) * 0.22)
    order = np.argsort(values[lo:hi])[::-1] + lo
    peaks = []
    for y in order:
        if values[y] < threshold:
            break
        if any(abs(int(y) - other) < min_distance for other in peaks):
            continue
        peaks.append(int(y))
    return peaks


def _tick_bands_from_component_endpoints(band_info: dict,
                                         split_y: int,
                                         full_h: int,
                                         seam_info: dict):
    components = band_info.get('tick_components') if band_info else None
    if components is None or len(components) == 0 or not seam_info:
        return {}
    main_end_y = seam_info.get('main_end_y')
    vernier_start_y = seam_info.get('vernier_start_y')
    if main_end_y is None or vernier_start_y is None:
        return {}

    tolerance = max(12, min(30, int(full_h * 0.022)))
    main_components = [component for component in components
                       if abs(int(component[1] + component[3] - 1) - main_end_y) <= tolerance]
    vernier_components = [component for component in components
                          if abs(int(component[1]) - vernier_start_y) <= tolerance]
    result = {}
    if len(main_components) >= 5:
        result['main_tick_band'] = (
            max(0, min(int(component[1]) for component in main_components)),
            split_y,
        )
    if len(vernier_components) >= 5:
        result['vernier_tick_band'] = (
            split_y,
            min(full_h, max(int(component[1] + component[3]) for component in vernier_components)),
        )
    return result


def _find_tick_band_pair(row_score: np.ndarray, full_h: int):
    values = np.asarray(row_score, dtype=float)
    if values.size < 16:
        return None
    vmax = float(np.max(values))
    positive = values[values > 0]
    if vmax <= 0 or positive.size == 0:
        return None

    min_len = max(7, min(30, int(full_h * 0.025)))
    threshold = max(float(np.percentile(positive, 62)), vmax * 0.18)
    segments = _contiguous_segments_1d(values >= threshold, min_len=min_len)
    if len(segments) < 2:
        segments = _contiguous_segments_1d(
            values >= vmax * 0.12, min_len=max(5, min_len // 2)
        )
    if len(segments) < 2:
        return None

    min_gap = max(3, int(full_h * 0.008))
    max_gap = max(20, int(full_h * 0.22))
    candidates = []
    for upper, lower in zip(segments, segments[1:]):
        gap = lower[0] - upper[1]
        if gap < min_gap or gap > max_gap:
            continue
        split = (upper[1] + lower[0]) / 2.0
        if not (full_h * 0.30 <= split <= full_h * 0.82):
            continue
        response = float(np.mean(values[upper[0]:upper[1]]))
        response += float(np.mean(values[lower[0]:lower[1]]))
        center_bias = 1.0 - min(1.0, abs(split / full_h - 0.62) / 0.40)
        upper_mean = float(np.mean(values[upper[0]:upper[1]]))
        lower_mean = float(np.mean(values[lower[0]:lower[1]]))
        response_ratio = min(upper_mean, lower_mean) / max(upper_mean, lower_mean, 1e-6)
        min_band_height = max(min_len, int(full_h * 0.04))
        candidates.append({
            'score': response + 0.12 * center_bias,
            'upper': upper,
            'lower': lower,
            'valid': (
                upper[1] - upper[0] >= min_band_height and
                lower[1] - lower[0] >= min_band_height and
                response_ratio >= 0.35
            ),
        })

    valid_candidates = [candidate for candidate in candidates if candidate['valid']]
    if valid_candidates:
        best = max(valid_candidates, key=lambda item: item['score'])
        return best['upper'], best['lower'], (best['upper'][1], best['lower'][0])

    internal = _find_internal_tick_band_valley(values, segments, full_h, min_len)
    if internal is None:
        return None
    return internal


def _find_internal_tick_band_valley(values: np.ndarray,
                                    segments: list,
                                    full_h: int,
                                    min_len: int):
    if not segments:
        return None

    best = None
    global_peak = float(np.max(values))
    if global_peak <= 0:
        return None

    for start, end in segments:
        segment_height = end - start
        guard = max(12, int(segment_height * 0.15))
        if segment_height < max(min_len * 3, guard * 2 + 3):
            continue

        local_window = max(18, min(45, segment_height // 5))
        valley_radius = max(4, min(10, segment_height // 18))
        search_lo = start + guard
        search_hi = end - guard
        for y in range(search_lo, search_hi):
            valley_lo = max(start, y - valley_radius)
            valley_hi = min(end, y + valley_radius + 1)
            value = float(values[y])
            if value > float(np.min(values[valley_lo:valley_hi])):
                continue

            left_peak = float(np.max(values[max(start, y - local_window):y]))
            right_peak = float(np.max(values[y + 1:min(end, y + local_window + 1)]))
            lower_peak = min(left_peak, right_peak)
            if lower_peak < global_peak * 0.35:
                continue
            if value > lower_peak * 0.65:
                continue

            upper = (start, y)
            lower = (y, end)
            min_band_height = max(min_len, int(full_h * 0.04))
            if upper[1] - upper[0] < min_band_height or lower[1] - lower[0] < min_band_height:
                continue

            score = lower_peak - value
            if best is None or score > best[0]:
                best = (score, upper, lower)

    if best is None:
        return None
    _, upper, lower = best
    return upper, lower, (upper[1], lower[0])


def _analyze_horizontal_tick_bands(gray: np.ndarray,
                                   binary: np.ndarray,
                                   split_y: int = None,
                                   projection: dict = None) -> dict:
    h, w = gray.shape[:2]
    if projection is None:
        fg = _foreground_binary(binary, gray)
        if fg is None or fg.size == 0:
            return {}
        kernel_h = int(round(h * config.region_split.vertical_open_height_ratio))
        kernel_h = max(config.region_split.vertical_open_min_height,
                       min(config.region_split.vertical_open_max_height, kernel_h))
        if kernel_h % 2 == 0:
            kernel_h += 1
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_h))
        vertical = cv2.morphologyEx(fg, cv2.MORPH_OPEN, vertical_kernel)
        if np.count_nonzero(vertical) < max(20, fg.size * 0.0004):
            vertical = fg
        raw_row_score = np.mean(vertical > 0, axis=1).astype(float)
        tick_components = _select_tick_components(vertical, kernel_h)
        row_score = (_component_tick_support_from_components(tick_components, h)
                     if config.region_split.projection_use_components else raw_row_score)
        start_response, end_response = _component_endpoint_responses(tick_components, h)
        row_coverage = _row_horizontal_coverage(vertical)
        win = int(round(h * config.region_split.projection_smooth_height_ratio))
        win = max(config.region_split.projection_smooth_min,
                  min(config.region_split.projection_smooth_max, win))
        if win % 2 == 0:
            win += 1
        smooth = np.convolve(row_score, np.ones(win, dtype=float) / win, mode='same')
        coverage_smooth = np.convolve(row_coverage, np.ones(win, dtype=float) / win, mode='same')
    else:
        vertical = projection.get('vertical_binary')
        row_score = projection.get('row_projection')
        row_coverage = projection.get('row_coverage')
        smooth = projection.get('row_projection_smooth')
        coverage_smooth = projection.get('row_coverage_smooth')
        if any(value is None for value in (vertical, row_score, row_coverage, smooth, coverage_smooth)):
            return {}

    base = {
        'row_projection_raw': raw_row_score if projection is None else projection.get('row_projection_raw'),
        'row_projection': row_score,
        'row_projection_smooth': smooth,
        'row_coverage': row_coverage,
        'row_coverage_smooth': coverage_smooth,
        'vertical_binary': vertical,
        'tick_components': tick_components if projection is None else projection.get('tick_components'),
        'component_start_response': start_response if projection is None else projection.get('component_start_response'),
        'component_end_response': end_response if projection is None else projection.get('component_end_response'),
    }
    if split_y is None:
        pair = _find_tick_band_pair(smooth, h)
        if pair is None:
            return base
        main_band, vernier_band, valley = pair
        base.update({
            'main_tick_band': main_band,
            'vernier_tick_band': vernier_band,
            'tick_band_valley': valley,
            'candidate_split_y': int(round((valley[0] + valley[1]) / 2.0)),
        })
        return base

    main_band = _find_tick_band_from_rows(
        smooth, 0, split_y, 'main', h, coverage_smooth)
    vernier_band = _find_tick_band_from_rows(
        smooth, split_y, h, 'vernier', h, coverage_smooth)

    if main_band is None:
        main_band = (max(0, split_y - max(24, int(h * 0.28))), split_y)
    if vernier_band is None:
        vernier_band = (split_y, min(h, split_y + max(24, int(h * 0.22))))
    main_band = (
        _find_outer_tick_band_valley(smooth, main_band[0], -1, h),
        main_band[1],
    )
    vernier_band = (
        vernier_band[0],
        _find_outer_tick_band_valley(smooth, vernier_band[1], 1, h),
    )

    base.update({
        'main_tick_band': main_band,
        'vernier_tick_band': vernier_band,
    })
    return base


def _select_tick_components(vertical: np.ndarray, min_height: int) -> np.ndarray:
    h, w = vertical.shape[:2]
    if h <= 0 or w <= 0:
        return np.empty((0, 5), dtype=np.int32)

    count, _, stats, _ = cv2.connectedComponentsWithStats(vertical, connectivity=8)
    if count <= 1:
        return np.empty((0, 5), dtype=np.int32)

    max_width = int(round(w * config.region_split.projection_component_max_width_ratio))
    max_width = max(config.region_split.projection_component_max_width_min,
                    min(config.region_split.projection_component_max_width_max, max_width))
    max_height = max(min_height, int(round(h * config.region_split.projection_component_max_height_ratio)))
    mask = ((stats[1:, cv2.CC_STAT_WIDTH] <= max_width) &
            (stats[1:, cv2.CC_STAT_HEIGHT] >= min_height) &
            (stats[1:, cv2.CC_STAT_HEIGHT] <= max_height))
    return stats[1:][mask].astype(np.int32, copy=False)


def _component_tick_support_from_components(components: np.ndarray, h: int) -> np.ndarray:
    support_delta = np.zeros(h + 1, dtype=np.int32)
    for _, y, _, component_h, _ in components:
        y1 = max(0, int(y))
        y2 = min(h, int(y + component_h))
        support_delta[y1] += 1
        support_delta[y2] -= 1
    support = np.cumsum(support_delta[:-1]).astype(float)
    max_support = float(np.max(support))
    return support / max_support if max_support > 0 else support


def _component_endpoint_responses(components: np.ndarray, h: int):
    starts = np.zeros(h, dtype=float)
    ends = np.zeros(h, dtype=float)
    for _, y, _, component_h, _ in components:
        starts[max(0, min(h - 1, int(y)))] += 1.0
        ends[max(0, min(h - 1, int(y + component_h - 1)))] += 1.0
    kernel = np.ones(9, dtype=float) / 9.0
    return np.convolve(starts, kernel, mode='same'), np.convolve(ends, kernel, mode='same')


def _find_outer_tick_band_valley(signal: np.ndarray,
                                 boundary: int,
                                 direction: int,
                                 full_h: int) -> int:
    values = np.asarray(signal, dtype=float)
    boundary = max(0, min(len(values) - 1, int(boundary)))
    if values.size < 3 or direction not in (-1, 1):
        return boundary

    max_distance = max(12, min(56, int(full_h * 0.15)))
    boundary_value = float(values[boundary])
    for distance in range(2, max_distance + 1):
        y = boundary + direction * distance
        if not 1 <= y < len(values) - 1:
            break
        if values[y] <= values[y - 1] and values[y] < values[y + 1]:
            if float(values[y]) <= boundary_value * 0.85:
                return y
    return boundary


def _row_horizontal_coverage(binary: np.ndarray) -> np.ndarray:
    h, w = binary.shape[:2]
    if h <= 0 or w <= 0:
        return np.array([], dtype=float)
    block_w = max(12, w // 120)
    n_blocks = max(1, w // block_w)
    trimmed = binary[:, :n_blocks * block_w] > 0
    if trimmed.size == 0:
        return np.zeros(h, dtype=float)
    blocks = trimmed.reshape(h, n_blocks, block_w)
    block_density = np.mean(blocks, axis=2)
    return np.mean(block_density > 0.01, axis=1).astype(float)


def _find_tick_band_from_rows(row_score: np.ndarray,
                              lo: int,
                              hi: int,
                              side: str,
                              full_h: int,
                              row_coverage: np.ndarray = None):
    lo = max(0, int(lo))
    hi = min(len(row_score), int(hi))
    if hi - lo < 8:
        return None

    values = row_score[lo:hi]
    vmax = float(np.max(values)) if values.size else 0.0
    if vmax <= 0:
        return None

    positive = values[values > 0]
    base = float(np.percentile(positive, 62)) if positive.size else 0.0
    th = max(base, vmax * 0.18)
    min_len = max(7, min(30, int(full_h * 0.025)))
    segments = _contiguous_segments_1d(values >= th, min_len=min_len)
    if not segments:
        th = vmax * 0.12
        segments = _contiguous_segments_1d(values >= th, min_len=max(5, min_len // 2))
    if not segments:
        return None

    scored = []
    for s, e in segments:
        gs, ge = lo + s, lo + e
        length = max(1, ge - gs)
        mean_score = float(np.mean(row_score[gs:ge]))
        length_score = min(1.0, length / max(12.0, full_h * 0.18))
        if side == 'main':
            proximity = 1.0 - min(1.0, abs(hi - ge) / max(12.0, full_h * 0.30))
        else:
            proximity = 1.0 - min(1.0, abs(gs - lo) / max(12.0, full_h * 0.22))
        score = 0.62 * (mean_score / vmax) + 0.23 * length_score + 0.15 * proximity
        scored.append((score, gs, ge))

    _, y1, y2 = max(scored, key=lambda item: item[0])
    pad = max(3, min(12, full_h // 80))
    y1 = max(lo, y1 - pad)
    y2 = min(hi, y2 + pad)
    min_h = max(12, min(48, int(full_h * 0.06)))
    if y2 - y1 < min_h:
        extra = min_h - (y2 - y1)
        y1 = max(lo, y1 - extra // 2)
        y2 = min(hi, y2 + extra - extra // 2)
    if side == 'main':
        y1 = _extend_main_band_to_long_ticks(row_score, row_coverage, y1, y2, lo, hi, vmax, full_h)
    return int(y1), int(max(y1 + 1, y2))


def _extend_main_band_to_long_ticks(row_score: np.ndarray,
                                    row_coverage: np.ndarray,
                                    y1: int,
                                    y2: int,
                                    lo: int,
                                    hi: int,
                                    vmax: float,
                                    full_h: int) -> int:
    if y2 <= y1 or vmax <= 0:
        return y1
    if row_coverage is None or len(row_coverage) != len(row_score):
        row_coverage = np.ones_like(row_score, dtype=float)

    search_lo = max(lo, hi - max(50, int(full_h * 0.45)))
    positive = row_score[search_lo:y2][row_score[search_lo:y2] > 0]
    if positive.size == 0:
        return y1

    low_th = max(vmax * 0.11, float(np.percentile(positive, 28)) * 0.75)
    cov_positive = row_coverage[search_lo:y2][row_coverage[search_lo:y2] > 0]
    cov_th = max(0.22, float(np.percentile(cov_positive, 45)) * 0.85) if cov_positive.size else 0.22
    max_gap = max(8, min(28, int(full_h * 0.055)))
    candidate = y1
    gap = 0
    seen = False

    for y in range(y1 - 1, search_lo - 1, -1):
        if float(row_score[y]) >= low_th and float(row_coverage[y]) >= cov_th:
            candidate = y
            gap = 0
            seen = True
        elif seen:
            gap += 1
            if gap > max_gap:
                break

    if y1 - candidate < max(6, int(full_h * 0.025)):
        return y1
    return max(lo, candidate - max(4, min(12, full_h // 45)))


def _contiguous_segments_1d(mask: np.ndarray, min_len: int = 1):
    segments = []
    start = None
    for idx, val in enumerate(mask.astype(bool)):
        if val and start is None:
            start = idx
        elif not val and start is not None:
            if idx - start >= min_len:
                segments.append((start, idx))
            start = None
    if start is not None and len(mask) - start >= min_len:
        segments.append((start, len(mask)))
    return segments


def _make_split_vis(color_bg: np.ndarray,
                    gray: np.ndarray,
                    binary: np.ndarray,
                    split_y: int,
                    band_info: dict = None) -> np.ndarray:
    """Draw the scale and its aligned horizontal projection side by side."""
    h, w = gray.shape
    scale_vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    foreground = band_info.get('vertical_binary') if band_info else None
    if foreground is None:
        foreground = _foreground_binary(binary, gray)
    hproj = band_info.get('row_projection_smooth') if band_info else None
    if hproj is None:
        hproj = np.sum(foreground > 0, axis=1).astype(float)
    else:
        hproj = np.asarray(hproj, dtype=float).copy()
    if hproj.size and np.max(hproj) > 0:
        hproj /= np.max(hproj)

    projection_w = max(160, min(360, w // 5))
    projection = np.full((h, projection_w, 3), 245, dtype=np.uint8)
    for y, value in enumerate(hproj):
        x_end = int(round(float(value) * (projection_w - 1)))
        if x_end > 0:
            cv2.line(projection, (0, y), (x_end, y), (20, 20, 20), 1)

    main_band = band_info.get('main_tick_band') if band_info else None
    vernier_band = band_info.get('vernier_tick_band') if band_info else None
    for band, color in ((main_band, (0, 180, 80)), (vernier_band, (255, 160, 40))):
        if not band:
            continue
        y1 = max(0, min(h - 1, int(band[0])))
        y2 = max(0, min(h - 1, int(band[1])))
        overlay = scale_vis.copy()
        cv2.rectangle(overlay, (0, y1), (w - 1, y2), color, -1)
        scale_vis = cv2.addWeighted(overlay, 0.16, scale_vis, 0.84, 0)
        cv2.line(scale_vis, (0, y1), (w - 1, y1), color, 1, cv2.LINE_AA)
        cv2.line(scale_vis, (0, y2), (w - 1, y2), color, 1, cv2.LINE_AA)
        cv2.line(projection, (0, y1), (projection_w - 1, y1), color, 1, cv2.LINE_AA)
        cv2.line(projection, (0, y2), (projection_w - 1, y2), color, 1, cv2.LINE_AA)

    split_y = max(0, min(h - 1, int(split_y)))
    seam_color = (40, 40, 240)
    cv2.line(scale_vis, (0, split_y), (w - 1, split_y), seam_color, 2, cv2.LINE_AA)
    cv2.line(projection, (0, split_y), (projection_w - 1, split_y), seam_color, 2, cv2.LINE_AA)

    gap = 8
    vis = np.full((h, w + gap + projection_w, 3), 30, dtype=np.uint8)
    vis[:, :w] = scale_vis
    vis[:, w + gap:] = projection
    return vis
