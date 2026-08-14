"""
步骤 4 — 游标尺识别（刻度线检测 + 固定 0.02mm 精度 + 对齐查找）

流程:
  1. 水平投影得到游标刻线带
  2. 垂直投影找两段大谷底，确定完整游标刻线窗口
  3. 高于阈值的连续峰段作为刻线，第一条为零线
  4. 固定使用 0.02mm 精度并查找最佳对齐线
"""

import cv2
import numpy as np
from typing import List, Tuple

from .utils import dedupe_ticks_by_relative_gap, draw_projection_plot, refine_tick_x_subpixel
from .config import config
from .standardization import build_standardization_result


def find_best_alignment(vernier_ticks: List[dict],
                          precision: float,
                          main_ticks: List[dict],
                          main_gap: float = None) -> Tuple[float, dict, float, dict]:
    """
    找到与主尺刻度线最对齐的游标刻线（游标读数）。

    物理原理:
      游标尺有 N 条等距刻线，对应主尺 (N-1) 条刻线跨度。
      游标第 i 条线与主尺某条线对齐时，小数读数 = i * precision。

    Args:
        vernier_ticks: 游标刻线列表
        precision:     卡尺精度，当前固定为 0.02
        main_ticks:    主尺刻线列表

    Returns:
        (vernier_reading, aligned_tick, confidence)
    """
    v_sorted = sorted(vernier_ticks, key=lambda t: t['x'])
    n_all = len(v_sorted)
    expected_lines = int(round(1.0 / precision)) if precision and precision > 0 else n_all
    n = min(n_all, max(2, expected_lines))
    v_sorted = v_sorted[:n]
    if n < 2:
        return 0.0, None, 0.0, {
            'best_index': None,
            'best_error_px': None,
            'continuous_index': None,
            'ambiguity': None,
        }

    # 计算游标区域 y 范围（用于 Y 方向过滤）
    vy_range = None
    if v_sorted:
        vy_all_start = min(t.get('y_start', 0) for t in v_sorted)
        vy_all_end = max(t.get('y_end', 0) for t in v_sorted)
        vy_range = (vy_all_start, vy_all_end)

    # 对每条游标刻线，计算与最近主尺刻线的像素误差
    errors = np.zeros(n)
    for i, vt in enumerate(v_sorted):
        errors[i] = _compute_alignment_error(vt.get('x_precise', vt['x']), main_ticks, None)

    # ── 找误差最小的游标线 ──
    best_idx = int(np.argmin(errors))

    # ── 亚像素抛物线插值 ──
    # 在 best_idx 附近拟合抛物线，得到更精确的零点
    sub_idx = float(best_idx)
    if 0 < best_idx < n - 1:
        e0, e1, e2 = errors[best_idx - 1], errors[best_idx], errors[best_idx + 1]
        denom = e0 - 2 * e1 + e2
        if abs(denom) > 1e-9:
            sub_idx = best_idx + 0.5 * (e0 - e2) / denom
    sub_idx = max(0.0, min(float(n - 1), sub_idx))

    vernier_reading = round(best_idx * precision, 2)
    alignment_info = {
        'best_index': int(best_idx),
        'best_error_px': float(errors[best_idx]),
        'continuous_index': float(sub_idx),
        'ambiguity': _make_alignment_ambiguity(
            errors, best_idx, precision, main_gap
        ),
    }

    # ── 置信度评分 ──
    confidence = _alignment_confidence(errors, best_idx, n)

    return vernier_reading, v_sorted[best_idx], confidence, alignment_info


def _compute_alignment_error(vx: float,
                             main_ticks: List[dict],
                             vernier_region_y_range: tuple = None) -> float:
    """计算游标线 vx 与最近主尺刻度线的像素距离。只在 y 方向有重叠的线对之间计算。"""
    best = float('inf')
    for mt in main_ticks:
        # Y 方向过滤：游标刻线必须与主尺刻线有垂直重叠才可能物理对齐
        if vernier_region_y_range is not None:
            vy_min, vy_max = vernier_region_y_range
            mt_ymin = mt.get('y_start', 0)
            mt_ymax = mt.get('y_end', 0)
            # 两条线 y 区间有交集才算
            if mt_ymax < vy_min or mt_ymin > vy_max:
                continue
        d = abs(vx - mt.get('x_precise', mt['x']))
        if d < best:
            best = d
    # 若无重叠刻线，回退到不过滤
    if best == float('inf'):
        for mt in main_ticks:
            d = abs(vx - mt.get('x_precise', mt['x']))
            if d < best:
                best = d
    return best


def _alignment_ambiguity_threshold(main_gap: float) -> float:
    cfg = config.vernier_scale
    raw = float(main_gap or 0.0) * float(cfg.align_ambiguity_margin_gap_ratio)
    return max(
        float(cfg.align_ambiguity_margin_min_px),
        min(float(cfg.align_ambiguity_margin_max_px), raw),
    )


def _make_alignment_ambiguity(errors: np.ndarray,
                              best_idx: int,
                              precision: float,
                              main_gap: float) -> dict:
    values = np.asarray(errors, dtype=float)
    if values.size < 2 or not (0 <= int(best_idx) < values.size):
        return None
    neighbor_indices = [
        index for index in (int(best_idx) - 1, int(best_idx) + 1)
        if 0 <= index < values.size and np.isfinite(values[index])
    ]
    if not neighbor_indices or not np.isfinite(values[int(best_idx)]):
        return None
    reference_idx = min(neighbor_indices, key=lambda index: float(values[index]))
    primary_error = float(values[int(best_idx)])
    reference_error = float(values[reference_idx])
    margin = reference_error - primary_error
    threshold = _alignment_ambiguity_threshold(main_gap)
    if margin < 0.0 or margin > threshold:
        return None
    return {
        'primary_index': int(best_idx),
        'reference_index': int(reference_idx),
        'primary_reading': round(int(best_idx) * float(precision), 2),
        'reference_reading': round(int(reference_idx) * float(precision), 2),
        'primary_error_px': primary_error,
        'reference_error_px': reference_error,
        'margin_px': float(margin),
        'threshold_px': float(threshold),
    }


def _alignment_confidence(errors: np.ndarray,
                           best_idx: int, n: int) -> float:
    """
    评估对齐结果的置信度。

    好的对齐 = 最小误差显著低于邻居（尖锐谷）。
    差的   = 多条线误差相近（平底谷 = 模糊）。

    Returns: 0~1
    """
    best_err = errors[best_idx]
    if best_err <= 0.5:
        return config.vernier_scale.align_conf_perfect  # 几乎完美对齐

    # 检查邻居
    neighbor_errs = []
    for offset in [-2, -1, 1, 2]:
        ni = best_idx + offset
        if 0 <= ni < n:
            neighbor_errs.append(errors[ni])

    if not neighbor_errs:
        return 0.5

    median_neighbor = float(np.median(neighbor_errs))
    if median_neighbor < 0.5:
        return 0.5

    # 信号比值：邻居误差 / 最优误差，越大说明最优越突出
    ratio = median_neighbor / max(best_err, 0.5)
    if ratio >= 3.0:
        return config.vernier_scale.align_conf_strong
    elif ratio >= 2.0:
        return config.vernier_scale.align_conf_moderate
    elif ratio >= 1.5:
        return config.vernier_scale.align_conf_weak
    return config.vernier_scale.align_conf_bad


# ═══════════════════════════ 可视化 ═══════════════════════════

def _draw_vernier_ticks(region: dict,
                         binary: np.ndarray,
                         vernier_ticks: List[dict],
                         vproj: np.ndarray,
                         peaks: np.ndarray,
                         zero_x: float = 0,
                         band_detection: dict = None,
                         standardization: dict = None) -> np.ndarray:
    if band_detection:
        return _draw_vernier_ticks_on_band(
            region, vernier_ticks, zero_x, band_detection,
            standardization=standardization,
        )

    """绘制游标尺刻度线检测 — 灰度底图 + 右下角二值图小窗"""
    img = region['image']
    h, w = img.shape

    vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    for t in vernier_ticks:
        is_long = t.get('is_long', False)
        color = (255, 200, 50) if is_long else (200, 160, 40)
        thickness = 3 if is_long else 2
        cv2.line(vis, (t['x'], t['y_start']), (t['x'], t['y_end']), color, thickness)
        if is_long:
            cv2.circle(vis, (t['x'], t['y_mid']), 4, (255, 255, 100), -1)

    # 零线高亮
    zx = int(zero_x) if zero_x > 0 else vernier_ticks[0]['x']
    cv2.line(vis, (zx, 0), (zx, h - 1), (50, 150, 255), 3)
    cv2.putText(vis, "ZERO", (zx + 4, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 150, 255), 1)

    # ── 右下角二值图小窗（显示检测器实际看到的图像）──
    bnw = max(50, w // 4)
    bnh = int(h * bnw / w)
    bthumb = cv2.resize(binary, (bnw, bnh), interpolation=cv2.INTER_AREA)
    bthumb_3 = cv2.cvtColor(bthumb, cv2.COLOR_GRAY2BGR)
    bx2, by2 = w - bnw, h - bnh
    vis[by2:by2 + bnh, bx2:bx2 + bnw] = bthumb_3
    cv2.rectangle(vis, (bx2, by2), (bx2 + bnw, by2 + bnh), (255, 255, 255), 1)
    cv2.putText(vis, "BIN", (bx2 + 3, by2 + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

    # 投影图
    proj_vis = draw_projection_plot(vproj, peaks, width=w,
                                     title=f"Vertical Projection ({len(vernier_ticks)} ticks)")
    ph = proj_vis.shape[0]

    gap = 2
    out = np.zeros((h + ph + gap, w, 3), dtype=np.uint8)
    out[:] = (30, 30, 35)
    out[:h, :w] = vis
    out[h + gap:h + gap + ph, :w] = proj_vis

    cv2.putText(out, "STEP 4: Vernier Scale Ticks (gray + binary overlay)", (5, out.shape[0] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 125), 1)

    return out


def _build_length_clustered_standard_response(width: int,
                                              ticks: List[dict],
                                              x_offset: int) -> Tuple[np.ndarray, dict]:
    """Build a display-only tick response from clustered observed lengths."""
    response = np.zeros(max(0, int(width)), dtype=float)
    valid = []
    for tick in ticks:
        try:
            # Display-only callers may provide a length measured from the
            # straightened binary trace.  Formal tick geometry remains in
            # ``length`` and is never overwritten.
            length = float(tick.get(
                'standardization_length', tick.get('length', 0.0)
            ))
            local_x = int(round(
                float(tick.get('x_precise', tick.get('x', tick.get('x_projection', 0)))) - x_offset
            ))
        except (TypeError, ValueError):
            continue
        if np.isfinite(length) and length > 0.0:
            valid.append((local_x, length))

    info = {
        'mode': 'single_length_cluster',
        'cluster_centers': [],
        'cluster_counts': [],
        'classification_mode': 'unknown',
        'centers': [],
        'counts': [],
        'separation': 0.0,
        'threshold': None,
        # The response is a position stem; amplitude encodes the length
        # cluster.  A broad rendering kernel would make horizontal width look
        # like another measured feature in the review figure.
        'response_kernel': 'center_stem',
    }
    labels = np.zeros(len(valid), dtype=int)
    if len(valid) >= 6:
        lengths = np.asarray([length for _x, length in valid], dtype=float)
        lo, hi = np.percentile(lengths, [5, 95])
        clipped = np.clip(lengths, lo, hi)
        centers = np.percentile(clipped, [25, 75]).astype(float)
        if abs(float(centers[1] - centers[0])) > 1e-9:
            for _ in range(20):
                labels = (np.abs(clipped - centers[1]) <
                          np.abs(clipped - centers[0])).astype(int)
                counts = np.bincount(labels, minlength=2)
                if np.any(counts == 0):
                    break
                updated = np.asarray([
                    np.mean(clipped[labels == 0]),
                    np.mean(clipped[labels == 1]),
                ])
                if float(np.max(np.abs(updated - centers))) < 1e-3:
                    centers = updated
                    break
                centers = updated

            labels = (np.abs(clipped - centers[1]) <
                      np.abs(clipped - centers[0])).astype(int)
            counts = np.bincount(labels, minlength=2)
            order = np.argsort(centers)
            centers = centers[order]
            labels = np.where(labels == order[0], 0, 1)
            counts = np.bincount(labels, minlength=2)
            if (
                min(counts) >= 3
                and centers[1] - centers[0] >= max(2.0, 0.20 * np.median(clipped))
            ):
                info = {
                    'mode': 'two_length_clusters',
                    'cluster_centers': [float(centers[0]), float(centers[1])],
                    'cluster_counts': [int(counts[0]), int(counts[1])],
                    'classification_mode': 'two_clusters',
                    'centers': [float(centers[0]), float(centers[1])],
                    'counts': [int(counts[0]), int(counts[1])],
                    'separation': float(
                        (centers[1] - centers[0]) / max(centers[0], 1.0)
                    ),
                    'threshold': None,
                    'response_kernel': 'center_stem',
                }
            else:
                labels = np.zeros(len(valid), dtype=int)

    if info['mode'] == 'single_length_cluster' and valid:
        lengths = np.asarray([length for _x, length in valid], dtype=float)
        median = float(np.median(lengths)) if lengths.size else 0.0
        if np.isfinite(median) and median > 0.0:
            info.update({
                'classification_mode': 'single',
                'centers': [median],
                'counts': [int(len(valid))],
            })

    for (local_x, _length), label in zip(valid, labels):
        amplitude = 1.5 if info['mode'] == 'two_length_clusters' and label == 1 else 1.0
        if 0 <= local_x < response.size:
            response[local_x] = max(response[local_x], amplitude)
    return response, info


def _build_display_binary_evidence(
    band_detection: dict,
    observed_ticks: List[dict],
    x_offset: int,
    width: int,
) -> dict:
    """Measure display ticks from the binary mask, one stroke at a time.

    This helper is intentionally restricted to the debug standardization
    path.  It traces the already observed display candidates on ``band`` and
    returns binary-only lengths/support.  It never edits ``gray_band`` and it
    never feeds candidates back into formal detection or alignment.
    """
    detection = band_detection or {}
    band_value = detection.get('band')
    band = np.asarray(band_value) if band_value is not None else None
    if band is None or band.ndim != 2 or band.size == 0:
        return {
            'corrected_band': np.zeros((0, max(0, int(width))), dtype=np.uint8),
            'corrected_projection': np.zeros(max(0, int(width)), dtype=float),
            'top_projection': np.zeros(max(0, int(width)), dtype=float),
            'trace_by_x': {},
            'states': [],
            'trace_count': 0,
            'candidate_count': int(len(observed_ticks or [])),
            'output_kind': 'binary_tick_mask',
        }

    try:
        period = float(detection.get('expected_gap', 0.0))
    except (TypeError, ValueError):
        period = 0.0
    if period <= 2.0:
        period = 10.0
    local_xs = []
    for tick in observed_ticks or []:
        try:
            local_x = int(round(float(
                tick.get('x_projection', tick.get('x', 0))
            ) - float(x_offset)))
        except (TypeError, ValueError):
            continue
        if 0 <= local_x < band.shape[1]:
            local_xs.append(local_x)

    # Reuse component evidence where an observed display x is close to a
    # formal component.  Evidence-only x positions can still be traced by
    # the thin-stroke path without a component.
    candidate_components = {}
    formal_components = []
    for candidate in detection.get('tick_candidates', []) or []:
        component = candidate.get('component')
        if component is None:
            continue
        try:
            candidate_x = float(candidate.get('x_projection'))
        except (TypeError, ValueError):
            continue
        formal_components.append((candidate_x, component))
    for local_x in sorted(set(local_xs)):
        nearby = [
            (abs(local_x - candidate_x), component)
            for candidate_x, component in formal_components
            if abs(local_x - candidate_x) <= max(4.0, period * 0.35)
        ]
        if nearby:
            candidate_components[local_x] = min(
                nearby, key=lambda item: item[0]
            )[1]

    relaxed_candidate_xs = set()
    for tick in observed_ticks or []:
        source = str(tick.get('source', ''))
        if source in {'binary_top_evidence', 'formal_tick_binary_evidence'}:
            try:
                local_value = float(
                    tick.get('x_projection', tick.get('x', 0))
                ) - float(x_offset)
                relaxed_candidate_xs.add(int(round(local_value)))
            except (TypeError, ValueError):
                continue

    corrected, traces, states = _build_per_tick_straightened_band(
        band,
        local_xs,
        period,
        include_candidate_states=True,
        candidate_components=candidate_components,
        relaxed_candidate_xs=relaxed_candidate_xs,
    )
    corrected_projection = np.sum(corrected > 0, axis=0).astype(float)

    top_projection = np.zeros(band.shape[1], dtype=float)
    roi = detection.get('vernier_tick_roi')
    if roi is not None and len(roi) == 2:
        try:
            roi_start = max(0, min(
                band.shape[1], int(round(float(roi[0])))
            ))
            roi_end = max(roi_start + 1, min(
                band.shape[1], int(round(float(roi[1])))
            ))
        except (TypeError, ValueError):
            roi_start, roi_end = 0, band.shape[1]
    else:
        roi_start, roi_end = 0, band.shape[1]
    top_height = max(24, min(
        band.shape[0], int(round(period * 1.6))
    ))
    if roi_end > roi_start:
        top_projection[roi_start:roi_end] = np.sum(
            band[:top_height, roi_start:roi_end] > 0,
            axis=0,
        ).astype(float)

    trace_by_x = {}
    for trace in traces:
        try:
            approx_x = int(round(float(trace.get('approx_x'))))
            trace_length = int(trace['y_end']) - int(trace['y_start']) + 1
        except (TypeError, ValueError, KeyError):
            continue
        component = candidate_components.get(approx_x)
        component_bottom_y = None
        if component is not None:
            try:
                component_bottom_y = float(component.get('y_end'))
            except (TypeError, ValueError):
                component_bottom_y = None
        trace_by_x[approx_x] = {
            'length': max(0, trace_length),
            'reference_x': float(trace.get('reference_x', approx_x)),
            'y_start': int(trace.get('y_start', 0)),
            'y_end': int(trace.get('y_end', 0)),
            'component_bottom_y': component_bottom_y,
        }
    return {
        'corrected_band': corrected,
        'corrected_projection': corrected_projection,
        'top_projection': top_projection,
        'trace_by_x': trace_by_x,
        'states': states,
        'trace_count': int(len(traces)),
        'candidate_count': int(len(local_xs)),
        'output_kind': 'binary_tick_mask',
    }


def _build_vernier_standardization(band_detection: dict,
                                   ticks: List[dict]) -> dict:
    """Build display-only standardization evidence in band coordinates."""
    detection = band_detection or {}
    x_offset = int(detection.get('x1', 0))
    raw_projection = detection.get('proj_norm')
    if raw_projection is None:
        raw_projection = np.zeros(
            max(0, int(detection.get('x2', 0)) - x_offset), dtype=float
        )
    raw_projection = np.asarray(raw_projection, dtype=float).reshape(-1)
    width = max(
        0,
        int(detection.get('x2', x_offset + raw_projection.size)) - x_offset,
        int(raw_projection.size),
    )
    observed_ticks = _recover_binary_top_evidence_ticks(
        detection, ticks or [], x_offset, width
    )
    binary_evidence = _build_display_binary_evidence(
        detection, observed_ticks, x_offset, width
    )
    trace_by_x = binary_evidence.get('trace_by_x', {})
    trace_lengths = [
        float(item.get('length', 0.0))
        for item in trace_by_x.values()
        if float(item.get('length', 0.0)) > 0.0
    ]
    trace_length_fallback = (
        float(np.median(np.asarray(trace_lengths, dtype=float)))
        if trace_lengths else 0.0
    )
    display_ticks = []
    for tick in observed_ticks:
        record = dict(tick)
        try:
            local_x = int(round(float(
                record.get('x_projection', record.get('x', 0))
            ) - float(x_offset)))
        except (TypeError, ValueError):
            local_x = -1
        trace = trace_by_x.get(local_x)
        if trace is None and trace_by_x:
            nearby = [
                (abs(local_x - int(candidate_x)), value)
                for candidate_x, value in trace_by_x.items()
                if abs(local_x - int(candidate_x)) <= max(4.0, float(
                    detection.get('expected_gap', 0.0) or 0.0
                ) * 0.35)
            ]
            if nearby:
                trace = min(nearby, key=lambda item: item[0])[1]
        if trace is not None and trace.get('length', 0) > 0:
            trace_length = float(trace['length'])
            component_length = 0.0
            if trace.get('component_bottom_y') is not None:
                try:
                    component_length = float(trace['component_bottom_y']) + 1.0
                except (TypeError, ValueError):
                    component_length = 0.0
            record['standardization_length'] = max(
                trace_length, component_length
            )
            record['_binary_length_source'] = 'binary_trace'
            record['binary_length'] = trace_length
            record['component_length'] = component_length
            record['length_evidence'] = (
                'binary_trace_plus_component_bottom'
                if component_length > trace_length else
                'binary_trace'
            )
            # A long formal stroke can be split before the lower end of the
            # binary trace.  Use its measured length only when it is close to
            # the observed trace scale; very large values are usually digit
            # contamination and must not enter the display clustering.
            try:
                formal_length = float(record.get('length', 0.0) or 0.0)
            except (TypeError, ValueError):
                formal_length = 0.0
            formal_long = (
                bool(record.get('is_long', False))
                or str(record.get('long_state', '')).startswith('long')
            )
            if (
                formal_long
                and component_length <= trace_length
                and trace_length_fallback > 0.0
                and formal_length >= 1.10 * trace_length
                and formal_length <= 1.75 * trace_length_fallback
            ):
                record['standardization_length'] = max(
                    trace_length, formal_length
                )
                record['length_evidence'] = 'binary_trace_plus_formal_length'
            record['binary_trace_y'] = [
                int(trace.get('y_start', 0)), int(trace.get('y_end', 0))
            ]
        elif trace_length_fallback > 0.0:
            # Keep an observed but untraced candidate in the display curve,
            # while preventing a digit-sized formal length from distorting
            # the long/short clusters.
            record['standardization_length'] = trace_length_fallback
            record['_binary_length_source'] = 'untraced_fallback'
            record['binary_length'] = 0.0
        display_ticks.append(record)

    component_support = _component_bottom_response(
        width, ticks or [], x_offset
    )
    corrected_support = np.asarray(
        binary_evidence.get('corrected_projection'), dtype=float
    ).reshape(-1)
    top_support = np.asarray(
        binary_evidence.get('top_projection'), dtype=float
    ).reshape(-1)
    direction_support = np.zeros(width, dtype=float)
    for source in (component_support, corrected_support, top_support):
        if source.size:
            direction_support[:min(width, source.size)] = np.maximum(
                direction_support[:min(width, source.size)],
                source[:min(width, source.size)],
            )
    support = direction_support
    response, cluster_info = _build_length_clustered_standard_response(
        width, display_ticks, x_offset
    )
    classification = {
        'mode': cluster_info.get('classification_mode', 'unknown'),
        'centers': list(cluster_info.get('centers', [])),
        'counts': list(cluster_info.get('counts', [])),
        'separation': float(cluster_info.get('separation', 0.0) or 0.0),
        'threshold': cluster_info.get('threshold'),
        # Candidate positions still come from the top-projection evidence;
        # direction correction is recorded separately as a support/length
        # source so existing display contracts remain readable.
        'evidence_source': (
            'binary_top_projection'
            if binary_evidence.get('candidate_count', 0) else
            'formal_tick_geometry'
        ),
        'direction_source': (
            'per_tick_straightened_binary'
            if binary_evidence.get('trace_count', 0) else
            'none'
        ),
        'formal_tick_count': int(len(ticks or [])),
        'display_tick_count': int(len(display_ticks)),
        'direction_trace_count': int(binary_evidence.get('trace_count', 0)),
        'direction_candidate_count': int(
            binary_evidence.get('candidate_count', len(display_ticks))
        ),
        'direction_trace_coverage': float(
            binary_evidence.get('trace_count', 0)
            / max(1, len(display_ticks))
        ),
        'length_source': (
            'binary_trace' if trace_lengths else 'formal_tick_geometry'
        ),
    }
    display_xs = []
    for tick in display_ticks:
        try:
            value = float(
                tick.get('x_projection', tick.get('x', 0))
            ) - float(x_offset)
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            display_xs.append(value)
    display_gaps = np.diff(np.asarray(sorted(display_xs), dtype=float))
    display_gaps = display_gaps[np.isfinite(display_gaps) & (display_gaps > 0)]
    classification['display_spacing_median'] = (
        float(np.median(display_gaps)) if display_gaps.size else 0.0
    )
    classification['display_max_gap'] = (
        float(np.max(display_gaps)) if display_gaps.size else 0.0
    )
    classification['display_min_gap'] = (
        float(np.min(display_gaps)) if display_gaps.size else 0.0
    )
    spacing_median = float(classification['display_spacing_median'])
    if display_gaps.size and spacing_median > 0.0:
        spacing_deviation = float(np.median(
            np.abs(display_gaps - spacing_median)
        ))
        spacing_consistency = float(np.clip(
            1.0 - spacing_deviation / spacing_median,
            0.0,
            1.0,
        ))
        spacing_max_ratio = float(
            classification['display_max_gap'] / spacing_median
        )
    else:
        spacing_consistency = 0.0 if display_gaps.size else 1.0
        spacing_max_ratio = 0.0
    fallback_count = sum(
        str(tick.get('_binary_length_source', '')) == 'untraced_fallback'
        for tick in display_ticks
    )
    trace_count = int(binary_evidence.get('trace_count', 0) or 0)
    display_count = int(len(display_ticks))
    binary_value = detection.get('band')
    binary_evidence_available = bool(
        binary_value is not None
        and np.asarray(binary_value).ndim == 2
        and np.asarray(binary_value).size > 0
    )
    if classification['mode'] == 'two_clusters':
        cluster_counts = [
            int(value) for value in classification.get('counts', [])
            if int(value) > 0
        ]
        cluster_balance = float(
            min(cluster_counts) / max(cluster_counts)
        ) if len(cluster_counts) >= 2 else 0.0
    else:
        cluster_balance = 1.0
    classification.update({
        'binary_evidence_available': binary_evidence_available,
        'response_kernel': cluster_info.get(
            'response_kernel', 'center_stem'
        ),
        'untraced_fallback_count': int(fallback_count),
        'untraced_fallback_ratio': float(
            fallback_count / max(1, display_count)
        ),
        'trace_support_count': int(sum(
            str(tick.get('_binary_length_source', '')) == 'binary_trace'
            for tick in display_ticks
        )),
        'trace_support_coverage': float(
            trace_count / max(1, display_count)
        ),
        'spacing_consistency': spacing_consistency,
        'spacing_max_ratio': spacing_max_ratio,
        'cluster_balance': cluster_balance,
    })
    positive_support = support[np.isfinite(support) & (support > 0.0)]
    median_support = float(np.median(positive_support)) if positive_support.size else 0.0
    threshold = classification.get('threshold')
    if threshold is None and classification['mode'] == 'two_clusters':
        centers = classification.get('centers', [])
        if len(centers) >= 2:
            threshold = (float(centers[0]) + float(centers[1])) / 2.0
            classification['threshold'] = float(threshold)
    records = []
    support_values = []
    binary_support_count = 0
    component_support_count = 0
    for tick in display_ticks:
        try:
            projection_x = int(round(
                float(tick.get('x_projection', tick.get('x', 0))) - x_offset
            ))
            local_projection = int(round(
                float(tick.get('x_precise', tick.get('x', tick.get('x_projection', 0)))) - x_offset
            ))
        except (TypeError, ValueError):
            continue
        if 0 <= local_projection < width:
            nearby = support[max(0, projection_x - 2):projection_x + 3]
            support_value = float(np.max(nearby)) if nearby.size else 0.0
            binary_nearby = direction_support[
                max(0, projection_x - 2):projection_x + 3
            ]
            binary_support_value = (
                float(np.max(binary_nearby)) if binary_nearby.size else 0.0
            )
            component_nearby = component_support[
                max(0, projection_x - 2):projection_x + 3
            ]
            component_support_value = (
                float(np.max(component_nearby))
                if component_nearby.size else 0.0
            )
            normalized_value = float(response[local_projection])
        else:
            support_value = 0.0
            binary_support_value = 0.0
            component_support_value = 0.0
            normalized_value = 0.0
        measured_length = float(tick.get('length', 0.0) or 0.0)
        binary_length = float(tick.get('binary_length', 0.0) or 0.0)
        length_source = str(
            tick.get('_binary_length_source', 'formal_tick_geometry')
        )
        tick_class = 'unknown'
        cluster_length = float(tick.get(
            'standardization_length', measured_length
        ) or 0.0)
        if classification['mode'] == 'two_clusters' and threshold is not None:
            if length_source != 'untraced_fallback':
                tick_class = (
                    'long' if cluster_length >= float(threshold) else 'short'
                )
        else:
            state = str(tick.get('long_state', ''))
            if length_source == 'untraced_fallback':
                state = ''
            if state.startswith('long') or bool(tick.get('is_long', False)):
                tick_class = 'long'
            elif state.startswith('short'):
                tick_class = 'short'
        support_values.append(support_value)
        if binary_support_value > 0.0:
            binary_support_count += 1
        if component_support_value > 0.0:
            component_support_count += 1
        quality = support_value / median_support if median_support > 0.0 else 0.0
        records.append({
            'x': float(tick.get('x', local_projection + x_offset)),
            'x_local': float(local_projection),
            'x_projection': float(tick.get('x_projection', local_projection + x_offset)),
            'measured_length': measured_length,
            'binary_length': binary_length,
            'length_source': length_source,
            'support_source': (
                'per_tick_straightened_binary'
                if binary_support_value > 0.0 and length_source == 'binary_trace'
                else 'binary_top_projection'
                if binary_support_value > 0.0
                else 'component_bottom'
                if component_support_value > 0.0
                else 'none'
            ),
            'support_value': support_value,
            'binary_support_value': binary_support_value,
            'component_support_value': component_support_value,
            'normalized_value': normalized_value,
            'class': tick_class,
            'quality': float(np.clip(quality, 0.0, 2.0)),
            'source': str(tick.get('source', 'formal_tick')),
        })
    classification['binary_support_count'] = int(binary_support_count)
    classification['binary_support_coverage'] = float(
        binary_support_count / max(1, len(records))
    )
    classification['component_support_count'] = int(component_support_count)
    classification['component_support_coverage'] = float(
        component_support_count / max(1, len(records))
    )
    classification['support_median'] = float(
        np.median(np.asarray(support_values, dtype=float))
        if support_values else 0.0
    )
    # Quality is an audit label for the display-only evidence.  It never
    # gates formal tick detection or changes the reading/alignment result.
    if display_count == 0:
        acceptance_status = 'unavailable'
    elif binary_evidence_available and classification['trace_support_coverage'] < 0.50:
        acceptance_status = 'low_binary_evidence'
    elif spacing_max_ratio > 1.75:
        acceptance_status = 'irregular_spacing'
    elif display_count < 0.90 * max(1, len(ticks or [])):
        acceptance_status = 'partial'
    elif classification['untraced_fallback_ratio'] > 0.25:
        acceptance_status = 'partial'
    # Vernier scales may contain only a small number of long strokes.  Do
    # not require balanced clusters or a theoretical 51-line pattern; flag
    # only an extreme one-sided split while retaining the measured ratio.
    elif classification['mode'] == 'two_clusters' and cluster_balance < 0.10:
        acceptance_status = 'unbalanced_clusters'
    else:
        acceptance_status = 'complete'
    classification['acceptance_status'] = acceptance_status
    return build_standardization_result(
        width, x_offset, raw_projection, support, response, records, classification
    )


def _recover_binary_top_evidence_ticks(
    band_detection: dict,
    formal_ticks: List[dict],
    x_offset: int,
    width: int,
) -> List[dict]:
    """Merge formal ticks with strong, periodic strokes visible in the binary band.

    This is display-only evidence recovery.  It never changes the formal
    candidates used for zero-line detection or reading.
    """
    detection = band_detection or {}
    band = np.asarray(detection.get('band')) if detection.get('band') is not None else None
    roi = detection.get('vernier_tick_roi')
    try:
        expected_gap = float(detection.get('expected_gap', 0.0))
    except (TypeError, ValueError):
        expected_gap = 0.0
    if band is None or band.ndim != 2 or band.size == 0 or expected_gap <= 2.0:
        return [dict(tick) for tick in formal_ticks]
    if roi is None or len(roi) != 2:
        return [dict(tick) for tick in formal_ticks]
    start = max(0, min(int(band.shape[1]), int(round(float(roi[0])))))
    end = max(start + 1, min(int(band.shape[1]), int(round(float(roi[1])))))
    if end <= start:
        return [dict(tick) for tick in formal_ticks]
    top_height = max(24, min(band.shape[0], int(round(expected_gap * 1.6))))
    projection = np.sum(
        band[:top_height, start:end] > 0,
        axis=0,
    ).astype(float)
    if projection.size == 0 or float(np.max(projection)) <= 0:
        return [dict(tick) for tick in formal_ticks]
    kernel = np.ones(3, dtype=float) / 3.0
    projection = np.convolve(projection, kernel, mode='same')
    threshold = max(3.0, float(np.max(projection)) * 0.12)
    min_separation = max(8, int(round(expected_gap * 0.65)))
    order = np.argsort(projection)[::-1]
    evidence_xs = []
    for local_index in order:
        if float(projection[local_index]) < threshold:
            break
        candidate_x = start + int(local_index)
        if all(abs(candidate_x - previous) >= min_separation
               for previous in evidence_xs):
            evidence_xs.append(candidate_x)
    evidence_xs.sort()
    # A top projection can include a separate hardware/number stroke before
    # the actual vernier run. Keep the longest near-period run; this bounds
    # display evidence without fabricating missing ticks.
    if len(evidence_xs) >= 4:
        runs = []
        run = [evidence_xs[0]]
        for previous, current in zip(evidence_xs, evidence_xs[1:]):
            if current - previous <= expected_gap * 1.35:
                run.append(current)
            else:
                runs.append(run)
                run = [current]
        runs.append(run)
        evidence_xs = max(
            runs,
            key=lambda candidate_run: (
                len(candidate_run),
                -abs(float(np.median(np.diff(candidate_run))) - expected_gap)
                if len(candidate_run) > 1 else -expected_gap,
            ),
        )
    if len(evidence_xs) < 3:
        return [dict(tick) for tick in formal_ticks]

    formal_local_xs = []
    for tick in formal_ticks:
        try:
            local_x = float(
                tick.get('x_projection', tick.get('x', 0))
            ) - float(x_offset)
        except (TypeError, ValueError):
            continue
        if np.isfinite(local_x):
            formal_local_xs.append(local_x)
    formal_local_xs = np.asarray(formal_local_xs, dtype=float)
    # A short sparse formal result should not be replaced by a broad display
    # run unless the binary evidence is genuinely continuous and covers the
    # existing formal region.
    if formal_local_xs.size and len(evidence_xs) < 0.55 * len(formal_local_xs):
        return [dict(tick) for tick in formal_ticks]

    by_x = {}
    for tick in formal_ticks:
        try:
            local_x = int(round(
                float(tick.get('x_projection', tick.get('x', 0))) - x_offset
            ))
        except (TypeError, ValueError):
            continue
        if start <= local_x < end:
            by_x[local_x] = dict(tick)

    merged = []
    matched_formal_xs = set()
    match_radius = max(4, int(round(expected_gap * 0.35)))
    for local_x in evidence_xs:
        nearby = [
            (abs(local_x - formal_x), formal_x, tick)
            for formal_x, tick in by_x.items()
            if abs(local_x - formal_x) <= match_radius
        ]
        if nearby:
            _, formal_x, tick = min(nearby, key=lambda item: item[0])
            matched_formal_xs.add(formal_x)
            record = dict(tick)
            record['formal_x_projection'] = float(formal_x + x_offset)
            record['formal_x'] = float(record.get('x', formal_x + x_offset))
            # The review curve must be placed at the binary image evidence,
            # not at a nearby formal candidate that may be several pixels off.
            evidence_global_x = float(local_x + x_offset)
            record['x_projection'] = evidence_global_x
            record['x'] = evidence_global_x
            record['x_precise'] = evidence_global_x
            record['source'] = 'formal_tick_binary_evidence'
        else:
            record = {
                'x': float(local_x + x_offset),
                'x_projection': float(local_x + x_offset),
                'x_precise': float(local_x + x_offset),
                'length': float(np.max(projection[max(0, local_x - start - 2):
                                                   min(projection.size, local_x - start + 3)])),
                'source': 'binary_top_evidence',
            }
        merged.append(record)
    # Keep every formal candidate visible in the diagnostic result even when
    # its top rows contain no binary evidence.  It is not a recovered line:
    # retaining it with an explicit source lets the per-tick tracer report a
    # meaningful failure (or use its connected-component evidence) instead of
    # silently dropping the candidate.
    for formal_x, tick in sorted(by_x.items()):
        if formal_x in matched_formal_xs:
            continue
        record = dict(tick)
        record['formal_x_projection'] = float(formal_x + x_offset)
        record['formal_x'] = float(record.get('x', formal_x + x_offset))
        record['source'] = 'formal_projection_unmatched'
        merged.append(record)
    merged.sort(key=lambda record: float(
        record.get('x_projection', record.get('x', 0.0))
    ))
    return merged


def _draw_vernier_ticks_on_band(region: dict,
                                vernier_ticks: List[dict],
                                zero_x: float,
                                band_detection: dict,
                                standardization: dict = None) -> np.ndarray:
    """Draw vernier tick labels on the same narrow band used for detection."""
    img = region['image']
    x1 = int(band_detection['x1'])
    x2 = int(band_detection['x2'])
    y1 = int(band_detection['band_y1'])
    y2 = int(band_detection['band_y2'])
    gray_band = img[y1:y2, x1:x2]
    if gray_band.size == 0:
        return np.zeros((100, 300, 3), dtype=np.uint8)

    band_h, band_w = gray_band.shape[:2]
    scale_y = max(2, min(4, int(np.ceil(150 / max(1, band_h)))))
    disp_h = band_h * scale_y
    vis = cv2.cvtColor(
        cv2.resize(gray_band, (band_w, disp_h), interpolation=cv2.INTER_LINEAR),
        cv2.COLOR_GRAY2BGR
    )

    face_left = int(band_detection.get('face_left_x', 0))
    if 0 < face_left < band_w:
        cv2.line(vis, (face_left, 0), (face_left, disp_h - 1),
                 (120, 120, 120), 1, cv2.LINE_AA)
        cv2.putText(vis, "EDGE", (face_left + 3, 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 160, 160), 1)

    for t in vernier_ticks:
        lx = int(round(t['x'] - x1))
        if not (0 <= lx < band_w):
            continue
        is_zero = abs(float(t['x']) - float(zero_x)) <= 3.0
        is_long = t.get('is_long', False)
        color = (50, 150, 255) if is_zero else ((255, 220, 80) if is_long else (80, 230, 255))
        thickness = 3 if is_zero or is_long else 2
        cv2.line(vis, (lx, 0), (lx, disp_h - 1), color, thickness, cv2.LINE_AA)
        if is_long:
            cv2.circle(vis, (lx, disp_h // 2), 4, (255, 255, 120), -1)

    zx = int(round(zero_x - x1))
    if 0 <= zx < band_w:
        cv2.line(vis, (zx, 0), (zx, disp_h - 1), (50, 150, 255), 3, cv2.LINE_AA)
        cv2.putText(vis, "ZERO", (min(zx + 4, band_w - 60), 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (50, 150, 255), 2)

    cv2.putText(vis, "Zero = first tick in valley-bounded band", (5, disp_h - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100, 180, 255), 1)
    cv2.putText(vis, "STEP 4: Vernier ticks on detected narrow band", (5, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1)

    candidates = [
        int(round(float(t['x']) - x1))
        for t in vernier_ticks
        if 0 <= int(round(float(t['x']) - x1)) < band_w
    ]
    standardization = standardization or band_detection.get('standardization')
    curves = (standardization or {}).get('curves', {})
    raw_signal = curves.get('raw_projection', band_detection.get('proj_norm', np.array([])))
    support = curves.get('support', np.zeros(band_w, dtype=float))
    standard_response = curves.get('normalized_response', np.zeros(band_w, dtype=float))
    raw_panel = _draw_vernier_projection_panel(
        raw_signal,
        band_w,
        f"Raw vertical projection ({len(vernier_ticks)} ticks)",
        (110, 100, 70),
    )
    support_panel = _draw_vernier_projection_panel(
        support,
        band_w,
        "Seam-near component bottom position",
        (80, 220, 255),
        candidates,
    )
    classification = (standardization or {}).get('classification', {})
    if classification.get('mode') == 'two_clusters':
        centers = classification.get('centers', [])
        counts = classification.get('counts', [])
        standard_title = (
            'Length-normalized standard response '
            f'(two length clusters: {centers[0]:.1f}/{centers[1]:.1f}px, '
            f'n={counts[0]}/{counts[1]}, '
            f'separation={float(classification.get("separation", 0.0)):.2f}; '
            'short=1.0, long=1.5)'
        )
    elif classification.get('mode') == 'single':
        centers = classification.get('centers', [])
        standard_title = (
            'Length-normalized standard response '
            f'(single length cluster: {centers[0]:.1f}px; short=1.0, long=1.5)'
        )
    else:
        standard_title = (
            'Length-normalized standard response '
            '(unknown length cluster; short=1.0, long=1.5)'
        )
    standard_panel = _draw_vernier_projection_panel(
        standard_response,
        band_w,
        standard_title,
        (255, 190, 60),
        candidates,
        value_max=1.5,
    )
    per_tick_panel = _draw_per_tick_correction_diagnostics(
        band_detection, band_w, candidates
    )
    gap = 10
    out_h = (disp_h + raw_panel.shape[0] + support_panel.shape[0]
              + standard_panel.shape[0] + per_tick_panel.shape[0] + gap * 4)
    out = np.zeros((out_h, band_w, 3), dtype=np.uint8)
    out[:] = (30, 30, 35)
    out[:disp_h, :band_w] = vis
    out[disp_h + gap:disp_h + gap + raw_panel.shape[0], :band_w] = raw_panel
    y0 = disp_h + gap + raw_panel.shape[0] + gap
    out[y0:y0 + support_panel.shape[0], :band_w] = support_panel
    y0 += support_panel.shape[0] + gap
    out[y0:y0 + standard_panel.shape[0], :band_w] = standard_panel
    y0 += standard_panel.shape[0] + gap
    out[y0:y0 + per_tick_panel.shape[0], :band_w] = per_tick_panel
    return out


def _component_bottom_response(width: int,
                               ticks: List[dict],
                               x_offset: int) -> np.ndarray:
    response = np.zeros(max(0, int(width)), dtype=float)
    for tick in ticks:
        component_id = tick.get('component_id')
        if component_id is None:
            continue
        center = int(round(float(tick.get('x', 0)) - float(x_offset)))
        bottom = float(tick.get('component_bottom_y', 0))
        for offset in range(-3, 4):
            x = center + offset
            if 0 <= x < response.size:
                response[x] = max(
                    response[x],
                    bottom * float(np.exp(-0.5 * (offset / 1.1) ** 2)),
                )
    return response


def _draw_per_tick_correction_diagnostics(band_detection: dict,
                                          width: int,
                                          candidates: List[int]) -> np.ndarray:
    """Show real per-stroke traces and their independently straightened projection."""
    correction = (band_detection or {}).get('per_tick_correction') or {}
    raw_band = correction.get('raw_band')
    traces = correction.get('traces', [])
    candidate_states = correction.get('candidate_states', [])
    if raw_band is None or raw_band.size == 0:
        return np.zeros((100, width, 3), dtype=np.uint8)

    height = raw_band.shape[0]
    scale_y = max(2, min(4, int(np.ceil(150 / max(1, height)))))
    overlay = cv2.cvtColor(
        cv2.resize(raw_band, (width, height * scale_y), interpolation=cv2.INTER_NEAREST),
        cv2.COLOR_GRAY2BGR,
    )
    for trace in traces:
        points = [
            (int(round(center_x)), int(y) * scale_y)
            for y, center_x, _left, _right in trace['points']
        ]
        if len(points) > 1:
            cv2.polylines(overlay, [np.asarray(points, dtype=np.int32)], False,
                          (255, 220, 60), 1, cv2.LINE_AA)
        ref = (int(round(trace['reference_x'])), int(trace['y_start']) * scale_y)
        cv2.circle(overlay, ref, 3, (50, 150, 255), -1, cv2.LINE_AA)
    untraced = [
        state for state in candidate_states if state.get('status') == 'untraced'
    ]
    for state in untraced:
        candidate_x = int(round(float(state['approx_x'])))
        if 0 <= candidate_x < width:
            cv2.line(overlay, (candidate_x, 0), (candidate_x, min(14, overlay.shape[0] - 1)),
                     (50, 90, 255), 1, cv2.LINE_AA)
            cv2.putText(overlay, 'U', (candidate_x + 2, min(14, overlay.shape[0] - 2)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (50, 90, 255), 1, cv2.LINE_AA)
    reason_counts = {}
    for state in untraced:
        reason = str(state.get('reason') or 'unknown')
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    reason_text = ', '.join(
        f'{reason}={count}' for reason, count in sorted(reason_counts.items())
    ) or 'none'
    header = np.full((58, width, 3), (28, 28, 34), dtype=np.uint8)
    cv2.putText(
        header,
        f'Per-tick trace diagnostic: traced={len(traces)}, untraced={len(untraced)}, total={correction.get("candidate_count", 0)}',
        (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 235), 1, cv2.LINE_AA,
    )
    cv2.putText(
        header,
        'yellow=individual centreline; blue=seam reference; red U=untraced formal candidate',
        (8, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 195), 1, cv2.LINE_AA,
    )
    cv2.putText(
        header, f'untraced reasons: {reason_text}',
        (8, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (180, 180, 195), 1, cv2.LINE_AA,
    )
    raw_panel = _draw_vernier_projection_panel(
        correction.get('raw_projection', np.zeros(width)), width,
        'Raw vertical projection (green = raw candidates)',
        (150, 150, 160), correction.get('raw_candidate_xs', candidates),
    )
    corrected_panel = _draw_vernier_projection_panel(
        correction.get('straightened_projection', np.zeros(width)), width,
        'Per-tick straightened projection (orange = traced candidates)',
        (255, 190, 60), correction.get('straightened_candidate_xs', []),
        candidate_color=(0, 165, 255),
    )
    continuous_panel = _draw_vernier_projection_panel(
        correction.get('continuous_projection', np.zeros(width)), width,
        'Continuous display projection (yellow = synthetic gaps)',
        (100, 220, 140), correction.get('straightened_candidate_xs', []),
        candidate_color=(0, 220, 255),
    )
    return np.vstack((header, overlay, raw_panel, corrected_panel,
                      continuous_panel))


def _crop_per_tick_binary_output(
    band_detection: dict,
    output_key: str = 'straightened_band',
) -> np.ndarray:
    """Return a diagnostic binary tick mask over the accepted tick ROI."""
    correction = (band_detection or {}).get('per_tick_correction') or {}
    image = correction.get(output_key)
    if image is None and output_key != 'straightened_band':
        # Keep older serialized/debug records usable; current detailed runs
        # always provide the continuous display layer.
        image = correction.get('straightened_band')
    if image is None:
        return np.zeros((0, 0), dtype=np.uint8)
    image = np.asarray(image)
    if image.ndim != 2:
        return np.zeros((0, 0), dtype=np.uint8)
    start = max(0, int(correction.get('x_start', 0) or 0))
    end = min(image.shape[1], int(correction.get('x_end', image.shape[1])))
    if end <= start:
        return np.zeros((image.shape[0], 0), dtype=np.uint8)
    output = np.where(image[:, start:end] > 0, 255, 0).astype(np.uint8)
    return output


def _draw_vernier_component_view(band_detection: dict) -> np.ndarray:
    """Show the real narrow-band components used to support tick candidates."""
    band = band_detection.get('band') if band_detection else None
    if band is None or band.size == 0:
        return np.zeros((100, 300, 3), dtype=np.uint8)

    height, width = band.shape[:2]
    scale_y = max(2, min(4, int(np.ceil(150 / max(1, height)))))
    view = cv2.cvtColor(
        cv2.resize(band, (width, height * scale_y), interpolation=cv2.INTER_NEAREST),
        cv2.COLOR_GRAY2BGR,
    )
    period = float(band_detection.get('expected_gap', 0.0))
    components = _extract_vernier_tick_components(band, period)
    accepted = band_detection.get('tick_candidates', [])
    rejected = band_detection.get('rejected_candidates', [])
    accepted_ids = {
        int(candidate['component_id']) for candidate in accepted
        if candidate.get('component_id') is not None
    }
    rejected_ids = {
        int(candidate['component_id']) for candidate in rejected
        if candidate.get('component_id') is not None
    }

    for component in components:
        component_id = int(component['component_id'])
        if component_id in accepted_ids:
            color, label = (70, 230, 100), 'accepted'
        elif component_id in rejected_ids:
            color, label = (80, 140, 255), 'rejected'
        else:
            color, label = (220, 180, 70), 'unmatched'
        x1 = int(component['x_left'])
        x2 = int(component['x_right'])
        y1 = int(component['y_start']) * scale_y
        y2 = (int(component['y_end']) + 1) * scale_y - 1
        cv2.rectangle(view, (x1, y1), (x2, y2), color, 1, cv2.LINE_AA)
        cv2.putText(view, label[0].upper(), (x1, max(14, y1 + 13)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)

    header = np.full((34, width, 3), (28, 28, 34), dtype=np.uint8)
    cv2.putText(header, 'Vernier connected components: green=accepted, orange=rejected, cyan=unmatched',
                (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 235), 1, cv2.LINE_AA)
    return np.vstack((header, view))


def _stack_vernier_debug_views(views: List[np.ndarray]) -> np.ndarray:
    """Combine detailed vernier evidence into the existing UI image slot."""
    valid = [view for view in views if view is not None and view.size]
    if not valid:
        return np.zeros((100, 300, 3), dtype=np.uint8)
    width = max(view.shape[1] for view in valid)
    gap = 12
    stacked = []
    for view in valid:
        if view.shape[1] != width:
            height = max(1, int(round(view.shape[0] * width / view.shape[1])))
            view = cv2.resize(view, (width, height), interpolation=cv2.INTER_AREA)
        stacked.append(view)
    separator = np.full((gap, width, 3), (18, 18, 24), dtype=np.uint8)
    return np.vstack([item for view in stacked for item in (view, separator)][:-1])


def _draw_vernier_projection_panel(signal: np.ndarray,
                                   width: int,
                                   title: str,
                                    color: tuple,
                                    candidates: List[int] = None,
                                    height: int = 180,
                                    value_max: float = None,
                                    candidate_color: tuple = (0, 220, 100)) -> np.ndarray:
    plot = np.full((height, width, 3), (28, 28, 28), dtype=np.uint8)
    top = 28
    bottom = height - 18
    values = np.asarray(signal, dtype=float)
    if values.size and value_max is None:
        maximum = float(np.max(values))
        values = values / maximum if maximum > 0 else values
    scale_max = float(value_max) if value_max is not None else 1.0
    values = np.clip(values, 0.0, scale_max)
    if values.size > 1:
        points = np.column_stack((
            np.arange(min(width, values.size)),
            bottom - (values[:width] / scale_max * (bottom - top)).astype(int),
        )).astype(np.int32)
        cv2.polylines(plot, [points], False, color, 2, cv2.LINE_AA)
    cv2.line(plot, (0, bottom), (width - 1, bottom), (70, 70, 75), 1)
    if candidates:
        for x in candidates:
            if 0 <= x < width:
                cv2.line(plot, (x, top), (x, bottom), candidate_color, 1)
    cv2.putText(plot, title, (10, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
    cv2.putText(plot, '0', (3, bottom),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 145), 1)
    cv2.putText(plot, '1.0', (3, top + 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 145), 1)
    if scale_max > 1.0:
        y = bottom - int(round((bottom - top) / scale_max))
        cv2.line(plot, (0, y), (width - 1, y), (65, 65, 70), 1, cv2.LINE_AA)
        cv2.putText(plot, '1.0', (3, y + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 145), 1)
        cv2.putText(plot, '1.5', (3, top + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 145), 1)
    return plot


def _draw_alignment(region: dict,
                     color_region: np.ndarray,
                     vernier_ticks: List[dict],
                     main_gap: float,
                     zero_x: float,
                     aligned_tick: dict,
                     align_conf: float = 0.0,
                     alignment_ambiguity: dict = None,
                     full_color: np.ndarray = None,
                     split_y: int = 0,
                     main_ticks: List[dict] = None) -> np.ndarray:
    """绘制对齐检测可视化

    背景图优先级: full_color (整张 ROI + 主尺网格) > color_region > 灰度
    """
    y_off = region.get('y_offset', 0)

    if full_color is not None:
        vis = full_color.copy()
        use_full = True
    elif color_region is not None:
        vis = color_region.copy()
        use_full = False
    else:
        vis = cv2.cvtColor(region['image'], cv2.COLOR_GRAY2BGR)
        use_full = False

    h, w = vis.shape[:2]

    # ── 分割线（全图模式下画出主尺/游标分界）──
    if use_full and split_y > 0:
        cv2.line(vis, (0, split_y), (w, split_y), (255, 255, 100), 1, cv2.LINE_AA)
        cv2.putText(vis, "MAIN SCALE", (10, split_y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 100), 1)
        cv2.putText(vis, "VERNIER", (10, split_y + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

    # ── 主尺真实网格线（全图模式下画在主尺半区）──
    if use_full and main_ticks and split_y > 0:
        for mt in main_ticks:
            mx = mt['x']
            my1 = mt.get('y_start', 0)
            my2 = min(mt.get('y_end', split_y), split_y)
            if 0 <= mx < w and my1 < my2:
                cv2.line(vis, (mx, my1), (mx, my2), (80, 80, 90), 1, cv2.LINE_AA)
    elif main_gap > 0:
        # 回退：合成网格线
        grid_offset = zero_x % main_gap
        for gx in np.arange(grid_offset, w, main_gap):
            gx = int(gx)
            if 0 <= gx < w:
                cv2.line(vis, (gx, 0), (gx, h), (80, 80, 90), 1, cv2.LINE_AA)

    # 游标刻线（全图模式下加上 y_offset = split_y）
    for i, t in enumerate(vernier_ticks):
        dy = y_off if use_full else 0
        pt1 = (t['x'], t['y_start'] + dy)
        pt2 = (t['x'], t['y_end'] + dy)
        cv2.line(vis, pt1, pt2, (200, 160, 40), 1)

    # 零线（亮蓝粗线贯穿全图 + 标注 x 坐标）
    zx = int(zero_x)
    cv2.line(vis, (zx, 0), (zx, h - 1), (50, 150, 255), 3)
    cv2.putText(vis, f"ZERO (x={zx})", (zx + 4, 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 150, 255), 2)
    if use_full:
        cv2.putText(vis, f"x={zx}", (zx + 4, h - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (50, 150, 255), 1)

    # 对齐线高亮（全图模式下加上 y_offset，标注序号）
    if aligned_tick:
        ax = aligned_tick['x']
        dy = y_off if use_full else 0
        ay1 = aligned_tick['y_start'] + dy
        ay2 = aligned_tick['y_end'] + dy
        aym = aligned_tick['y_mid'] + dy
        cv2.line(vis, (ax, ay1), (ax, ay2), (0, 255, 80), 3)
        cv2.circle(vis, (ax, aym), 8, (0, 255, 80), 2)
        # 计算对齐线是第几条（序号）
        v_sorted = sorted(vernier_ticks, key=lambda t: t['x'])
        aligned_idx = next((i for i, t in enumerate(v_sorted) if t['x'] == ax), -1)
        label = f"ALIGNED! tick#{aligned_idx}" if aligned_idx >= 0 else "ALIGNED!"
        cv2.putText(vis, label, (ax + 5, aym),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 80), 2)

    if alignment_ambiguity:
        reference_idx = int(alignment_ambiguity.get('reference_index', -1))
        v_sorted = sorted(vernier_ticks, key=lambda t: t['x'])
        if 0 <= reference_idx < len(v_sorted):
            reference = v_sorted[reference_idx]
            rx = int(reference['x'])
            dy = y_off if use_full else 0
            ry1 = int(reference['y_start'] + dy)
            ry2 = int(reference['y_end'] + dy)
            rym = int(reference['y_mid'] + dy)
            cv2.line(vis, (rx, ry1), (rx, ry2), (0, 165, 255), 2)
            cv2.circle(vis, (rx, rym), 7, (0, 165, 255), 2)
            label = 'ALT {:.2f} err={:.2f}px'.format(
                float(alignment_ambiguity.get('reference_reading', 0.0)),
                float(alignment_ambiguity.get('reference_error_px', 0.0)),
            )
            cv2.putText(vis, label, (rx + 5, rym + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 2)

    # 对齐置信度
    if align_conf > 0:
        cc = (0, 255, 100) if align_conf > 0.7 else (255, 200, 50) if align_conf > 0.4 else (255, 120, 120)
        cv2.putText(vis, f"conf: {align_conf:.2f}", (w - 160, vis.shape[0] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, cc, 1)

    cv2.putText(vis, "STEP 4: Vernier Alignment v2", (5, vis.shape[0] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 125), 1)

    return vis


def _empty_vernier_result(reason: str = 'vernier_detection_failed') -> dict:
    empty_img = np.zeros((100, 300, 3), dtype=np.uint8)
    return {
        'vernier_ticks': [], 'precision': 0.02, 'vernier_reading': 0.0,
        'zero_x': 0.0, 'aligned_tick': None,
        'vis_ticks': empty_img, 'vis_alignment': empty_img,
        'vproj_norm': None, 'vernier_peaks': None,
        'standardization': None,
        'alignment_confidence': 0.0,
        'alignment_info': None,
        'alignment_ambiguity': None,
        'vis_valley': None,
        'vernier_band_detection': None,
        'error': reason,
    }


def _map_tick_to_original(tick: dict) -> dict:
    """Map a tick detected on the vernier body crop back to split ROI coords."""
    x_offset = int(tick.get('_x_offset', 0))
    mapped = dict(tick)
    mapped['x_local'] = int(round(tick['x']))
    mapped['x'] = int(round(tick['x'])) + x_offset
    if 'x_precise' in tick:
        mapped['x_precise'] = float(tick['x_precise']) + x_offset
    return mapped


def _map_ticks_to_original(ticks: List[dict], region: dict) -> List[dict]:
    x_offset = int(region.get('x_offset', 0)) if region else 0
    ticks_with_offset = []
    for t in ticks:
        tt = dict(t)
        tt['_x_offset'] = x_offset
        ticks_with_offset.append(tt)
    return sorted([_map_tick_to_original(t) for t in ticks_with_offset], key=lambda t: t['x'])


def _map_x_to_original(x: float, region: dict, y: float = None) -> float:
    x_offset = int(region.get('x_offset', 0)) if region else 0
    return float(x + x_offset)


def _contiguous_true_segments(mask: np.ndarray, min_len: int = 1) -> List[Tuple[int, int]]:
    """Return [start, end) segments for a 1-D boolean mask."""
    segments = []
    start = None
    for i, value in enumerate(mask.astype(bool)):
        if value and start is None:
            start = i
        elif not value and start is not None:
            if i - start >= min_len:
                segments.append((start, i))
            start = None
    if start is not None and len(mask) - start >= min_len:
        segments.append((start, len(mask)))
    return segments


def _find_vernier_tick_band(binary: np.ndarray, x1: int, x2: int) -> Tuple[int, int]:
    """Find the narrow row band containing downward vernier tick strokes."""
    h, w = binary.shape[:2]
    if h <= 0 or w <= 0:
        return 0, 0

    x1 = max(0, min(w - 1, int(x1)))
    x2 = max(x1 + 1, min(w, int(x2)))
    search_h = max(18, min(h, int(h * 0.62)))
    crop = binary[:search_h, x1:x2]
    if crop.size == 0:
        fallback_h = max(12, min(h, int(h * 0.30)))
        return 0, fallback_h

    kernel_h = max(5, min(21, search_h // 10))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_h))
    vertical = cv2.morphologyEx(crop, cv2.MORPH_OPEN, vertical_kernel)
    if np.count_nonzero(vertical) < max(20, crop.size * 0.0005):
        vertical = crop

    row_score = np.mean(vertical > 0, axis=1).astype(float)
    if np.max(row_score) <= 0:
        fallback_h = max(12, min(h, int(h * 0.30)))
        return 0, fallback_h

    win = max(3, min(15, search_h // 25))
    if win % 2 == 0:
        win += 1
    smooth = np.convolve(row_score, np.ones(win, dtype=float) / win, mode='same')
    th = max(float(np.median(smooth) + 0.45 * np.std(smooth)),
             float(np.max(smooth) * 0.22))
    segments = _contiguous_true_segments(smooth >= th,
                                         min_len=max(5, min(18, search_h // 18)))
    if not segments:
        fallback_h = max(12, min(h, int(h * 0.30)))
        return 0, fallback_h

    max_mean = max(float(np.mean(smooth[s:e])) for s, e in segments)
    strong = [(s, e) for s, e in segments
              if float(np.mean(smooth[s:e])) >= max_mean * 0.55]
    top_limit = int(search_h * 0.45)
    near_top = [(s, e) for s, e in strong if s <= top_limit]
    selected = min(near_top or strong, key=lambda seg: (seg[0], -(seg[1] - seg[0])))

    pad = max(3, min(8, kernel_h // 2))
    y1 = max(0, selected[0] - pad)
    y2 = min(search_h, selected[1] + pad)
    min_band_h = max(12, min(36, int(h * 0.12)))
    if y2 - y1 < min_band_h:
        extra = min_band_h - (y2 - y1)
        y1 = max(0, y1 - extra // 2)
        y2 = min(search_h, y2 + extra - extra // 2)
    return y1, max(y1 + 1, y2)


def _estimate_vernier_tick_gap(tick_xs: List[int], main_gap: float) -> float:
    if main_gap and main_gap > 3:
        return float(main_gap) * 0.98
    if len(tick_xs) < 3:
        return 0.0
    diffs = np.diff(sorted(tick_xs))
    diffs = diffs[diffs >= 3]
    if len(diffs) == 0:
        return 0.0
    lo, hi = np.percentile(diffs, [20, 80])
    core = diffs[(diffs >= lo) & (diffs <= hi)]
    return float(np.median(core if len(core) else diffs))


def _analyze_vernier_projection_band(band: np.ndarray,
                                     expected_gap: float) -> dict:
    """Run the existing observed-evidence detector on one tick-band image."""
    proj = np.sum(band > 0, axis=0).astype(float)
    if np.max(proj) <= 0:
        return None
    proj_norm = proj / np.max(proj)
    smooth = _smooth_projection_1d(proj_norm, expected_gap)
    valley_info = _select_vernier_roi_from_valleys(
        smooth, proj_norm, expected_gap, band
    )
    if valley_info is None:
        return None

    roi_x1, roi_x2 = valley_info['tick_roi']
    h_th = float(valley_info.get(
        'tick_h_th',
        _projection_segment_threshold(proj_norm[roi_x1:roi_x2], 0.80),
    ))
    tick_xs = list(valley_info.get('candidate_tick_xs') or [])
    if not tick_xs:
        tick_xs = _threshold_segments_from_projection(proj_norm, h_th, roi_x1, roi_x2)
    if len(tick_xs) < config.vernier_scale.min_tick_count:
        return None
    valley_segments = valley_info['valley_segments']
    return {
        'band': band,
        'proj': proj,
        'proj_norm': proj_norm,
        'smooth': smooth,
        'peaks': [(int(x), float(proj_norm[int(x)])) for x in tick_xs
                  if 0 <= int(x) < len(proj_norm)],
        'valleys': [
            (int(round((start + end) / 2.0)),
             float(np.min(smooth[max(0, start):min(len(smooth), end)])))
            for start, end in valley_segments if end > start
        ],
        'tick_xs': tick_xs,
        'tick_candidates': list(valley_info.get('tick_candidates') or []),
        'rejected_candidates': valley_info.get('rejected_candidates', []),
        'h_th': h_th,
        'A': float(np.percentile(proj_norm, 90)),
        'B': float(valley_info['valley_th']),
        'expected_gap': float(valley_info.get('observed_period', expected_gap)),
        'face_left_x': int(valley_segments[0][0]) if valley_segments else 0,
        'ignore_until': int(valley_segments[0][1]) if valley_segments else 0,
        'valley_segments': valley_segments,
        'selected_valley_pair': valley_info['selected_pair'],
        'all_valley_segments': valley_info['all_valley_segments'],
        'vernier_tick_roi': (int(roi_x1), int(roi_x2)),
        'pair_scores': valley_info.get('pair_scores', []),
        'selection_score': float(valley_info.get('selection_score', 0.0)),
        'period_clarity': float(valley_info.get('period_clarity', 0.0)),
        'spacing_score': float(valley_info.get('spacing_score', 0.0)),
        'component_support': float(valley_info.get('component_support', 0.0)),
        'tick_structure': float(valley_info.get('tick_structure', 0.0)),
    }


def _build_debug_correction_candidates(
    band: np.ndarray,
    raw_analysis: dict,
) -> tuple[list[int], list[dict]]:
    """Recover display-only binary candidates before per-tick tracing.

    Formal candidates remain the authority for reading.  This helper only
    supplies the correction diagnostic with additional positions that have a
    real top-projection signal inside the selected valley-bounded ROI.
    """
    formal_xs = sorted(set(
        int(candidate['x_projection'])
        for candidate in raw_analysis.get('tick_candidates', [])
        if candidate.get('x_projection') is not None
    ))
    if not formal_xs:
        formal_xs = sorted(set(
            int(value) for value in raw_analysis.get('tick_xs', [])
        ))
    formal_records = [
        {
            'x': float(value),
            'x_projection': float(value),
            'x_precise': float(value),
            'source': 'formal_projection',
        }
        for value in formal_xs
    ]
    recovery_detection = {
        'band': band,
        'x1': 0,
        'x2': int(band.shape[1]),
        'expected_gap': raw_analysis.get('expected_gap', 0.0),
        'vernier_tick_roi': raw_analysis.get('vernier_tick_roi'),
        'tick_candidates': raw_analysis.get('tick_candidates', []),
    }
    recovered = _recover_binary_top_evidence_ticks(
        recovery_detection,
        formal_records,
        0,
        int(band.shape[1]),
    )
    return formal_xs, recovered or formal_records


def _detect_vernier_band_projection(binary: np.ndarray,
                                     main_gap: float,
                                     gray: np.ndarray = None,
                                     tick_band: tuple = None,
                                     make_debug: bool = False) -> dict:
    """Detect vernier ticks from the complete horizontal tick band."""
    if binary is None or binary.size == 0:
        return None

    h, w = binary.shape[:2]
    x1 = 0
    x2 = w
    if tick_band is not None:
        band_y1 = max(0, min(h - 1, int(tick_band[0])))
        band_y2 = max(band_y1 + 1, min(h, int(tick_band[1])))
    else:
        band_y1, band_y2 = _find_vernier_tick_band(binary, x1, x2)
    band = binary[band_y1:band_y2, x1:x2]
    gray_band = gray[band_y1:band_y2, x1:x2] if gray is not None else None
    if band.size == 0:
        return None

    expected_gap = _estimate_vernier_tick_gap([], main_gap)
    if expected_gap <= 2.0:
        expected_gap = _estimate_vernier_tick_gap([], 25.0)
    raw_analysis = _analyze_vernier_projection_band(band, expected_gap)
    if raw_analysis is None:
        return None

    formal_candidate_xs = [
        int(candidate['x_projection'])
        for candidate in raw_analysis['tick_candidates']
    ] or list(raw_analysis['tick_xs'])
    correction_records = []
    candidate_xs = list(formal_candidate_xs)
    per_tick_correction = None
    if make_debug:
        formal_candidate_xs, correction_records = (
            _build_debug_correction_candidates(band, raw_analysis)
        )
        candidate_xs = sorted(set(
            int(round(float(record.get(
                'x_projection', record.get('x', 0)
            ))))
            for record in correction_records
        ))
        source_by_candidate = {
            int(round(float(record.get(
                'x_projection', record.get('x', 0)
            )))): str(record.get('source', 'formal_projection'))
            for record in correction_records
        }
        component_entries = [
            (float(candidate.get('x_projection')), candidate.get('component'))
            for candidate in raw_analysis.get('tick_candidates', [])
            if candidate.get('component') is not None
        ]
        component_by_candidate = {}
        for candidate_x in candidate_xs:
            nearby = [
                (abs(candidate_x - component_x), component)
                for component_x, component in component_entries
                if abs(candidate_x - component_x) <= max(
                    4.0, float(raw_analysis['expected_gap']) * 0.35
                )
            ]
            if nearby:
                component_by_candidate[candidate_x] = min(
                    nearby, key=lambda item: item[0]
                )[1]
        relaxed_candidate_xs = {
            candidate_x for candidate_x, source in source_by_candidate.items()
            if source in {'binary_top_evidence', 'formal_tick_binary_evidence'}
        }
        straightened_band, traces, candidate_states = _build_per_tick_straightened_band(
            band, candidate_xs, raw_analysis['expected_gap'],
            include_candidate_states=True,
            candidate_components=component_by_candidate,
            relaxed_candidate_xs=relaxed_candidate_xs,
            candidate_sources=source_by_candidate,
        )
        continuous_band, synthetic_gap_mask, display_traces = (
            _build_per_tick_continuous_display_band(
                band, traces, raw_analysis['expected_gap']
            )
        )
        roi_start, roi_end = raw_analysis['vernier_tick_roi']
        recovered_candidate_xs = [
            int(round(float(record.get(
                'x_projection', record.get('x', 0)
            ))))
            for record in correction_records
            if str(record.get('source', '')) == 'binary_top_evidence'
        ]
        per_tick_correction = {
            'raw_band': band,
            'straightened_band': straightened_band,
            'continuous_band': continuous_band,
            'synthetic_gap_mask': synthetic_gap_mask,
            'raw_projection': raw_analysis['proj_norm'],
            'straightened_projection': (
                np.sum(straightened_band > 0, axis=0).astype(float)
            ),
            'continuous_projection': (
                np.sum(continuous_band > 0, axis=0).astype(float)
            ),
            'raw_candidate_xs': candidate_xs,
            'straightened_candidate_xs': [
                int(round(trace['reference_x'])) for trace in traces
            ],
            'traces': traces,
            'display_traces': display_traces,
            'candidate_states': candidate_states,
            'trace_count': len(traces),
            'untraced_count': sum(
                state['status'] == 'untraced' for state in candidate_states
            ),
            'display_trace_count': len(display_traces),
            'display_filled_gap_rows': int(sum(
                item.get('filled_gap_rows', 0) for item in display_traces
            )),
            'display_synthetic_pixels': int(sum(
                item.get('synthetic_pixels', 0) for item in display_traces
            )),
            'candidate_count': len(candidate_xs),
            'formal_candidate_xs': formal_candidate_xs,
            'formal_candidate_count': len(formal_candidate_xs),
            'recovered_candidate_xs': recovered_candidate_xs,
            'recovered_candidate_count': len(recovered_candidate_xs),
            'candidate_source': (
                'binary_top_projection_periodic_run'
                if recovered_candidate_xs else 'formal_projection'
            ),
            'band_height': int(band.shape[0]),
            'band_y1': int(band_y1),
            'band_y2': int(band_y2),
            'x_start': int(roi_start),
            'x_end': int(roi_end),
            'roi_width': max(0, int(roi_end) - int(roi_start)),
            'output_kind': 'binary_tick_mask',
        }

    return {
        'x1': x1,
        'x2': x2,
        'band_y1': band_y1,
        'band_y2': band_y2,
        'band': band,
        'gray_band': gray_band,
        'proj': raw_analysis['proj'],
        'proj_norm': raw_analysis['proj_norm'],
        'smooth': raw_analysis['smooth'],
        'peaks': raw_analysis['peaks'],
        'valleys': raw_analysis['valleys'],
        'peak_tick_xs_local': raw_analysis['tick_xs'],
        'segment_tick_xs_local': raw_analysis['tick_xs'],
        'raw_tick_xs_local': raw_analysis['tick_xs'],
        'tick_xs_local': raw_analysis['tick_xs'],
        'tick_xs_global': [x1 + x for x in raw_analysis['tick_xs']],
        'tick_candidates': raw_analysis['tick_candidates'],
        'rejected_candidates': raw_analysis['rejected_candidates'],
        'h_th': raw_analysis['h_th'],
        'A': raw_analysis['A'],
        'B': raw_analysis['B'],
        'expected_gap': raw_analysis['expected_gap'],
        'main_gap_prior': expected_gap,
        'face_left_x': raw_analysis['face_left_x'],
        'ignore_until': raw_analysis['ignore_until'],
        'early_filter_until': raw_analysis['ignore_until'],
        'valley_segments': raw_analysis['valley_segments'],
        'selected_valley_pair': raw_analysis['selected_valley_pair'],
        'all_valley_segments': raw_analysis['all_valley_segments'],
        'vernier_tick_roi': raw_analysis['vernier_tick_roi'],
        'pair_scores': raw_analysis['pair_scores'],
        'selection_score': raw_analysis['selection_score'],
        'period_clarity': raw_analysis['period_clarity'],
        'spacing_score': raw_analysis['spacing_score'],
        'component_support': raw_analysis['component_support'],
        'tick_structure': raw_analysis['tick_structure'],
        'per_tick_correction': per_tick_correction,
    }


def _smooth_projection_1d(signal: np.ndarray, expected_gap: float) -> np.ndarray:
    if signal is None or len(signal) == 0:
        return np.asarray([], dtype=float)
    win = int(round(expected_gap * 0.25)) if expected_gap > 2.0 else 5
    win = max(3, min(21, win))
    if win % 2 == 0:
        win += 1
    if win >= len(signal):
        win = max(3, len(signal) | 1)
    return np.convolve(signal, np.ones(win, dtype=float) / win, mode='same')


def _valley_threshold(signal: np.ndarray) -> float:
    if signal is None or len(signal) == 0:
        return 0.08
    median_v = float(np.median(signal))
    return min(0.24, max(0.08, median_v * 0.95))


def _merge_close_segments(segments: List[Tuple[int, int]], max_gap: int) -> List[Tuple[int, int]]:
    if not segments:
        return []
    merged = [segments[0]]
    for s, e in segments[1:]:
        ps, pe = merged[-1]
        if s - pe <= max_gap:
            merged[-1] = (ps, e)
        else:
            merged.append((s, e))
    return merged


def _estimate_observed_tick_period(tick_xs: List[int], fallback: float = 0.0) -> float:
    if len(tick_xs) < 3:
        return float(fallback)
    diffs = np.diff(np.asarray(sorted(set(int(x) for x in tick_xs)), dtype=float))
    diffs = diffs[diffs >= 3.0]
    if diffs.size < 2:
        return float(fallback)
    median = float(np.median(diffs))
    core = diffs[(diffs >= median * 0.55) & (diffs <= median * 1.45)]
    period = float(np.median(core)) if core.size >= 2 else median
    return period if period >= 3.0 else float(fallback)


def _projection_period_clarity(signal: np.ndarray, period: float) -> float:
    values = np.asarray(signal, dtype=float)
    lag = int(round(period))
    if values.size < lag * 3 or lag < 3:
        return 0.0
    left = values[:-lag]
    right = values[lag:]
    left = left - float(np.mean(left))
    right = right - float(np.mean(right))
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom <= 1e-9:
        return 0.0
    return max(0.0, min(1.0, float(np.dot(left, right) / denom)))


def _spacing_consistency(tick_xs: List[int], period: float) -> float:
    if len(tick_xs) < 4 or period < 3.0:
        return 0.0
    diffs = np.diff(np.asarray(sorted(tick_xs), dtype=float))
    errors = np.abs(diffs - period) / period
    local = errors[errors <= 0.65]
    if local.size == 0:
        return 0.0
    coverage = float(local.size) / float(errors.size)
    stability = max(0.0, 1.0 - float(np.median(local)) / 0.35)
    return max(0.0, min(1.0, coverage * stability))


def _valley_segment_quality(signal: np.ndarray,
                             left: Tuple[int, int],
                             right: Tuple[int, int],
                            valley_th: float,
                            period: float) -> float:
    values = []
    for start, end in (left, right):
        segment = np.asarray(signal[max(0, start):min(len(signal), end)], dtype=float)
        if segment.size:
            depth = max(0.0, 1.0 - float(np.mean(segment)) / max(valley_th, 1e-6))
            width = min(1.0, float(end - start) / max(period, 1.0))
            values.append(0.75 * depth + 0.25 * width)
    return float(np.mean(values)) if values else 0.0


def _valley_has_two_sided_peak_support(proj_norm: np.ndarray,
                                       valley: Tuple[int, int],
                                       observed_period: float,
                                       tick_threshold: float,
                                       near_periods: float,
                                       far_periods: float) -> bool:
    """Require a valley to be bounded by observed peak response on both sides."""
    if proj_norm is None or observed_period < 3.0:
        return False
    values = np.asarray(proj_norm, dtype=float)
    start, end = int(valley[0]), int(valley[1])
    near = max(1, int(round(observed_period * near_periods)))
    far = max(near + 1, int(round(observed_period * far_periods)))
    left_start, left_end = start - far, start - near
    right_start, right_end = end + near, end + far
    if left_start < 0 or right_end > values.size:
        return False
    left_peak = float(np.max(values[left_start:left_end])) if left_end > left_start else 0.0
    right_peak = float(np.max(values[right_start:right_end])) if right_end > right_start else 0.0
    return left_peak >= tick_threshold and right_peak >= tick_threshold


def _pair_has_no_large_internal_valley(smooth: np.ndarray,
                                       left: Tuple[int, int],
                                       right: Tuple[int, int],
                                       valley_threshold: float,
                                       observed_period: float,
                                       max_break_periods: float) -> bool:
    """Reject a valley pair containing a low-response gap larger than a tick gap."""
    if smooth is None or observed_period < 3.0:
        return False
    start = max(0, int(left[1]))
    end = min(len(smooth), int(right[0]))
    if end <= start:
        return False
    low_segments = _contiguous_true_segments(
        np.asarray(smooth[start:end]) <= valley_threshold, min_len=1
    )
    max_break = max(1, int(round(observed_period * max_break_periods)))
    return all(segment_end - segment_start < max_break
               for segment_start, segment_end in low_segments)


def _component_length_structure(candidates: List[dict]) -> float:
    values = np.asarray([
        float(candidate['component']['y_end'])
        for candidate in candidates
        if candidate.get('component') is not None
    ], dtype=float)
    if values.size < 4:
        return 0.0
    low = float(np.percentile(values, 25))
    high = float(np.percentile(values, 75))
    if high <= low:
        return 0.0
    labels = np.zeros(len(values), dtype=bool)
    for _ in range(12):
        labels = np.abs(values - high) < np.abs(values - low)
        if not np.any(labels) or np.all(labels):
            return 0.0
        next_low = float(np.mean(values[~labels]))
        next_high = float(np.mean(values[labels]))
        if abs(next_low - low) < 0.01 and abs(next_high - high) < 0.01:
            low, high = next_low, next_high
            break
        low, high = next_low, next_high
    if int(np.sum(labels)) < 2 or int(np.sum(~labels)) < 2:
        return 0.0
    separation = (high - low) / max(low, 1.0)
    minimum = float(config.vernier_scale.long_cluster_min_separation_ratio)
    if separation < minimum:
        return 0.0
    return min(1.0, (separation - minimum) / max(0.30, minimum))


def _projection_strength_structure(candidates: List[dict]) -> float:
    values = np.asarray([
        float(candidate.get('projection_strength', 0.0))
        for candidate in candidates
        if float(candidate.get('projection_strength', 0.0)) > 0
    ], dtype=float)
    if values.size < 4:
        return 0.0
    low = float(np.percentile(values, 25))
    high = float(np.percentile(values, 75))
    if high <= low:
        return 0.0
    labels = np.zeros(len(values), dtype=bool)
    for _ in range(12):
        labels = np.abs(values - high) < np.abs(values - low)
        if not np.any(labels) or np.all(labels):
            return 0.0
        next_low = float(np.mean(values[~labels]))
        next_high = float(np.mean(values[labels]))
        if abs(next_low - low) < 1e-4 and abs(next_high - high) < 1e-4:
            low, high = next_low, next_high
            break
        low, high = next_low, next_high
    if int(np.sum(labels)) < 2 or int(np.sum(~labels)) < 2:
        return 0.0
    separation = (high - low) / max(low, 1e-6)
    minimum = 0.15
    if separation < minimum:
        return 0.0
    return min(1.0, (separation - minimum) / 0.35)


def _select_vernier_roi_from_valleys(signal: np.ndarray,
                                     proj_norm: np.ndarray,
                                     expected_gap: float,
                                     band: np.ndarray):
    if signal is None or len(signal) == 0 or expected_gap <= 2.0:
        return None
    valley_th = _valley_threshold(signal)
    min_len = max(12, int(round(expected_gap * 0.80)))
    merge_gap = max(4, int(round(expected_gap * 0.25)))
    valley_segments = _contiguous_true_segments(signal <= valley_th, min_len=1)
    valley_segments = _merge_close_segments(valley_segments, merge_gap)
    valley_segments = [(s, e) for s, e in valley_segments if e - s >= min_len]
    if len(valley_segments) < 2:
        return None

    # Require a measured run with several periods, but do not encode a target
    # number of vernier lines.  Internal valleys may split one real run.
    min_middle = max(int(round(expected_gap * 8.0)), int(round(len(signal) * 0.10)))
    max_middle = int(round(len(signal) * 0.92))
    pair_scores = []
    for i, left in enumerate(valley_segments[:-1]):
        for right in valley_segments[i + 1:]:
            middle = right[0] - left[1]
            if middle < min_middle or middle > max_middle:
                continue
            h_th = _projection_segment_threshold(proj_norm[left[1]:right[0]], 0.80)
            tick_xs = _threshold_segments_from_projection(proj_norm, h_th, left[1], right[0])
            if not tick_xs or len(tick_xs) < max(8, config.vernier_scale.min_tick_count):
                continue
            observed_period = _estimate_observed_tick_period(tick_xs, expected_gap)
            left_valley_supported = _valley_has_two_sided_peak_support(
                proj_norm, left, observed_period, h_th,
                config.vernier_scale.valley_peak_support_near_periods,
                config.vernier_scale.valley_peak_support_far_periods,
            )
            right_valley_supported = _valley_has_two_sided_peak_support(
                proj_norm, right, observed_period, h_th,
                config.vernier_scale.valley_peak_support_near_periods,
                config.vernier_scale.valley_peak_support_far_periods,
            )
            internal_continuity = _pair_has_no_large_internal_valley(
                signal, left, right, valley_th, observed_period,
                config.vernier_scale.valley_internal_break_periods,
            )
            if not (left_valley_supported and right_valley_supported
                    and internal_continuity):
                continue
            candidates = _build_tick_candidates(
                band, tick_xs, observed_period, proj_norm
            )
            accepted, rejected = _suppress_duplicate_candidates(
                candidates, observed_period
            )
            # A printed zero can create projection peaks immediately after the
            # left valley.  Only use top-edge stroke evidence to discard that
            # leading prefix: later peaks are still required for alignment and
            # need not themselves reach the top edge of the band.
            top_strokes = []
            first_top_supported_index = None
            for index, candidate in enumerate(accepted):
                top_stroke = _split_top_stroke_from_candidate(
                    band, int(candidate['x_projection']), observed_period,
                    # A real zero tick can merge with its printed digit and
                    # lose component support, while the first rows are blank.
                    # Probe the remaining top band before rejecting it.
                    retry_lower_seed=True,
                )
                component = candidate.get('component')
                component_height = (
                    int(component['y_end']) - int(component['y_start']) + 1
                    if component is not None else 0
                )
                if (top_stroke is None and component is not None
                        and component_height >= int(round(band.shape[0] * config.vernier_scale.component_fallback_min_height_ratio))):
                    # A vertically bridged component already proves that the
                    # stroke begins near the seam and continues through the
                    # tick band, even if its thin top segment reaches a digit
                    # before the pixel-only tracker meets its height target.
                    top_stroke = {
                        'component_backed': True,
                        'top_connected': True,
                    }
                top_strokes.append(top_stroke)
                if top_stroke is not None and first_top_supported_index is None:
                    first_top_supported_index = index

            top_supported = []
            for index, candidate in enumerate(accepted):
                top_stroke = top_strokes[index]
                if (first_top_supported_index is not None
                        and index < first_top_supported_index):
                    rejected_candidate = dict(candidate)
                    rejected_candidate['accepted'] = False
                    rejected_candidate['rejection_reason'] = 'leading_no_top_vertical_stroke'
                    rejected.append(rejected_candidate)
                    continue
                accepted_candidate = dict(candidate)
                if top_stroke is not None:
                    accepted_candidate['top_stroke'] = top_stroke
                top_supported.append(accepted_candidate)
            accepted = top_supported
            accepted_xs = [int(c['x_projection']) for c in accepted]
            if len(accepted_xs) < max(6, config.vernier_scale.min_tick_count):
                continue

            period_clarity = _projection_period_clarity(
                proj_norm[left[1]:right[0]], observed_period
            )
            spacing_score = _spacing_consistency(accepted_xs, observed_period)
            valley_score = _valley_segment_quality(
                signal, left, right, valley_th, observed_period
            )
            component_support = (
                sum(c.get('component_id') is not None for c in accepted) / float(len(accepted))
            )
            component_structure = _component_length_structure(accepted)
            projection_structure = _projection_strength_structure(accepted)
            tick_structure = max(component_structure, projection_structure)
            component_score = (
                0.35 * component_support
                + 0.50 * component_structure
                + 0.15 * projection_structure
            )
            total_score = (
                config.vernier_scale.valley_score_depth_weight * valley_score
                + config.vernier_scale.valley_score_period_weight * period_clarity
                + config.vernier_scale.valley_score_spacing_weight * spacing_score
                + config.vernier_scale.valley_score_component_weight * component_score
            )
            pair_scores.append({
                'left': left,
                'right': right,
                'middle': int(middle),
                'tick_h_th': float(h_th),
                'observed_period': float(observed_period),
                'period_clarity': float(period_clarity),
                'spacing_score': float(spacing_score),
                'valley_score': float(valley_score),
                'component_score': float(component_score),
                'component_support': float(component_support),
                'component_structure': float(component_structure),
                'projection_structure': float(projection_structure),
                'tick_structure': float(tick_structure),
                'left_valley_supported': bool(left_valley_supported),
                'right_valley_supported': bool(right_valley_supported),
                'internal_continuity': bool(internal_continuity),
                'structure_valid': True,
                'total_score': float(total_score),
                'accepted_candidates': accepted,
                'rejected_candidates': rejected,
            })

    if not pair_scores:
        return None
    valid_pairs = [
        item for item in pair_scores
        if (item['period_clarity'] >= config.vernier_scale.valley_min_period_clarity
                and item['tick_structure'] >= config.vernier_scale.valley_min_component_structure
                and item['total_score'] >= config.vernier_scale.valley_min_total_score)
    ]
    if not valid_pairs:
        # Some clear tick runs have uniform measured stroke lengths, so a
        # long/short cluster is absent.  Strong component support across the
        # observed periodic peaks is sufficient fallback evidence.
        valid_pairs = [
            item for item in pair_scores
            if (item['period_clarity'] >= config.vernier_scale.valley_min_period_clarity
                    and item['total_score'] >= config.vernier_scale.valley_min_total_score
                    and item['component_support'] >= 0.75)
        ]
    if not valid_pairs:
        return None
    best = _select_best_valley_pair(
        valid_pairs,
        tie_margin=config.vernier_scale.valley_score_tie_margin,
        preferred_tick_count=config.vernier_scale.valley_preferred_tick_count,
    )
    roi_x1 = int(best['left'][1])
    roi_x2 = int(best['right'][0])
    return {
        'tick_roi': (roi_x1, roi_x2),
        'selected_pair': (best['left'], best['right'], best['middle']),
        'valley_segments': [best['left'], best['right']],
        'all_valley_segments': valley_segments,
        'valley_th': valley_th,
        'tick_h_th': best['tick_h_th'],
        'candidate_tick_xs': [
            int(c['x_projection']) for c in best['accepted_candidates']
        ],
        'tick_candidates': best['accepted_candidates'],
        'rejected_candidates': best['rejected_candidates'],
        'observed_period': best['observed_period'],
        'pair_scores': pair_scores,
        'selection_score': best['total_score'],
        'period_clarity': best['period_clarity'],
        'spacing_score': best['spacing_score'],
        'component_support': best['component_support'],
        'tick_structure': best['tick_structure'],
    }


def _projection_segment_threshold(signal: np.ndarray,
                                  threshold_factor: float = 0.20) -> float:
    if signal is None or len(signal) == 0:
        return 0.02
    return max(
        float(np.mean(signal)) + threshold_factor * float(np.std(signal)),
        0.02,
    )


def _threshold_segments_from_projection(signal: np.ndarray,
                                        threshold: float,
                                        x1: int = 0,
                                        x2: int = None) -> List[int]:
    if signal is None or len(signal) == 0:
        return []
    n = len(signal)
    x1 = max(0, min(n, int(x1)))
    x2 = n if x2 is None else max(x1, min(n, int(x2)))
    mask = np.asarray(signal[x1:x2]) > float(threshold)
    xs = []
    start = None
    for i, value in enumerate(mask.astype(bool)):
        if value and start is None:
            start = i
        elif not value and start is not None:
            xs.append(int(round((x1 + start + x1 + i - 1) / 2.0)))
            start = None
    if start is not None:
        xs.append(int(round((x1 + start + x2 - 1) / 2.0)))
    return xs


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


def _extract_vernier_tick_components(band: np.ndarray,
                                     observed_period: float) -> List[dict]:
    if band is None or band.size == 0:
        return []

    foreground = _bridge_short_vertical_gaps(
        (band > 0).astype(np.uint8),
        config.vernier_scale.component_vertical_bridge_gap,
    )
    kernel_h = max(1, int(config.vernier_scale.component_vertical_open_height))
    if kernel_h % 2 == 0:
        kernel_h += 1
    if kernel_h > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_h))
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel)
    height, width = foreground.shape[:2]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground, connectivity=8)
    near_seam = max(8, min(18, height // 4))
    min_height = max(8, int(round(height * 0.35)))
    max_width = max(5, int(round(observed_period * 0.75))) if observed_period > 0 else 12

    components = []
    for label in range(1, count):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        w = int(stats[label, cv2.CC_STAT_WIDTH])
        h = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if y > near_seam or h < min_height or w > max_width:
            continue
        ys, xs = np.where(labels == label)
        seam_xs = xs[ys <= near_seam]
        if seam_xs.size == 0:
            continue
        bottom_y = int(np.max(ys))
        bottom_xs = xs[ys >= max(y, bottom_y - near_seam)]
        components.append({
            'component_id': int(label),
            'x_near_seam': float(np.median(seam_xs)),
            'x_bottom': float(np.median(bottom_xs)) if bottom_xs.size else float(np.median(xs)),
            'x_left': int(np.min(xs)),
            'x_right': int(np.max(xs)),
            'y_start': int(np.min(ys)),
            'y_end': bottom_y,
            'area': area,
        })
    return components


def _bridge_short_vertical_gaps(foreground: np.ndarray,
                                max_gap: int) -> np.ndarray:
    """Connect vertically aligned fragments separated by a small blank gap."""
    if foreground is None or foreground.size == 0 or max_gap < 1:
        return foreground
    bridged = np.asarray(foreground, dtype=np.uint8).copy()
    for x in range(bridged.shape[1]):
        segments = _contiguous_true_segments(bridged[:, x] > 0, min_len=1)
        for upper, lower in zip(segments, segments[1:]):
            if lower[0] - upper[1] <= max_gap:
                bridged[upper[1]:lower[0], x] = 1
    return bridged


def _select_best_valley_pair(valid_pairs: List[dict],
                             tie_margin: float,
                             preferred_tick_count: int) -> dict:
    """Use observed tick count only to resolve near-equal valley scores."""
    if not valid_pairs:
        return None
    best_score = max(float(item['total_score']) for item in valid_pairs)
    near_ties = [
        item for item in valid_pairs
        if best_score - float(item['total_score']) <= tie_margin
    ]
    return min(near_ties, key=lambda item: (
        abs(len(item.get('accepted_candidates', [])) - preferred_tick_count),
        -float(item['total_score']),
        -float(item.get('period_clarity', 0.0)),
        -float(item.get('spacing_score', 0.0)),
    ))


def _split_top_stroke_from_candidate(band: np.ndarray,
                                     approx_x: int,
                                     observed_period: float,
                                     retry_lower_seed: bool = True):
    """Keep the top thin stroke and stop before it widens into a digit."""
    if band is None or band.size == 0:
        return None
    h, w = band.shape[:2]
    if h < 12 or not (0 <= int(approx_x) < w):
        return None
    radius = max(6, min(12, int(round(max(3.0, observed_period) * 0.25))))
    x1 = max(0, int(approx_x) - radius)
    x2 = min(w, int(approx_x) + radius + 1)
    foreground = band[:, x1:x2] > 0
    top_limit = max(8, min(18, h // 4))
    max_width = max(4, min(8, int(round(max(3.0, observed_period) * 0.17))))

    min_height = max(12, int(round(h * 0.28)))
    max_blank_gap = max(1, min(4, int(round(observed_period * 0.08))))
    best = None
    for start_y in range(min(top_limit, h)):
        xs = np.flatnonzero(foreground[start_y])
        if xs.size == 0:
            continue
        segments = _contiguous_int_segments(xs)
        segment = min(
            segments,
            key=lambda item: abs((x1 + (item[0] + item[1]) / 2.0) - float(approx_x)),
        )
        width = segment[1] - segment[0] + 1
        center = x1 + (segment[0] + segment[1]) / 2.0
        if width > max_width or abs(center - float(approx_x)) > radius:
            continue

        widths = []
        centers = []
        blank_gap = 0
        last_y = None
        for y in range(start_y, h):
            xs = np.flatnonzero(foreground[y])
            if xs.size == 0:
                blank_gap += 1
                if blank_gap > max_blank_gap:
                    break
                continue
            segments = _contiguous_int_segments(xs)
            segment = min(
                segments,
                key=lambda item: abs((x1 + (item[0] + item[1]) / 2.0) - center),
            )
            row_width = segment[1] - segment[0] + 1
            row_center = x1 + (segment[0] + segment[1]) / 2.0
            if row_width > max_width or abs(row_center - center) > 3.0:
                break
            widths.append(row_width)
            centers.append(row_center)
            center = row_center
            blank_gap = 0
            last_y = y
        if len(widths) >= min_height and (best is None or len(widths) > len(best['widths'])):
            best = {
                'start_y': start_y,
                'widths': widths,
                'centers': centers,
                'last_y': last_y,
            }
        if not retry_lower_seed:
            break

    if best is None:
        return None
    return {
        'top_connected': best['start_y'] <= top_limit,
        'thin_run_height': len(best['widths']),
        'max_stroke_width': max(best['widths']),
        'x_drift': max(best['centers']) - min(best['centers']),
        'cut_y': best['last_y'],
    }


def _trace_vernier_tick_centerline(band: np.ndarray,
                                   approx_x: int,
                                   observed_period: float,
                                   return_failure_reason: bool = False,
                                   max_width: int = None,
                                   max_center_jump: float = None,
                                   min_height: int = None,
                                   seed_search_limit: int = None) -> dict:
    """Trace one seam-connected thin stroke without following a digit below it."""
    if band is None or band.size == 0:
        return (None, 'empty_band') if return_failure_reason else None
    height, width = band.shape[:2]
    if height < 12 or not (0 <= int(approx_x) < width):
        return (None, 'invalid_candidate_position') if return_failure_reason else None
    radius = max(6, min(20, int(round(max(3.0, observed_period) * 0.40))))
    x1 = max(0, int(approx_x) - radius)
    x2 = min(width, int(approx_x) + radius + 1)
    foreground = band[:, x1:x2] > 0
    top_limit = max(8, min(18, height // 4))
    base_max_width = max(4, min(8, int(round(max(3.0, observed_period) * 0.17))))
    max_width = base_max_width if max_width is None else max(
        base_max_width, int(max_width)
    )
    max_center_jump = (
        3.0 if max_center_jump is None else max(3.0, float(max_center_jump))
    )
    base_min_height = max(12, int(round(height * 0.28)))
    min_height = base_min_height if min_height is None else max(
        12, min(base_min_height, int(min_height))
    )
    max_blank_gap = max(1, min(4, int(round(observed_period * 0.08))))
    seed_limit = top_limit if seed_search_limit is None else min(
        height,
        max(top_limit, int(seed_search_limit)),
    )

    best = None
    has_top_thin_seed = False
    for start_y in range(min(seed_limit, height)):
        row_xs = np.flatnonzero(foreground[start_y])
        if row_xs.size == 0:
            continue
        segments = _contiguous_int_segments(row_xs)
        segment = min(
            segments,
            key=lambda item: abs((x1 + (item[0] + item[1]) / 2.0) - float(approx_x)),
        )
        center = x1 + (segment[0] + segment[1]) / 2.0
        if (segment[1] - segment[0] + 1 > max_width
                or abs(center - float(approx_x)) > radius):
            continue
        has_top_thin_seed = True

        points = []
        blank_gap = 0
        for y in range(start_y, height):
            row_xs = np.flatnonzero(foreground[y])
            if row_xs.size == 0:
                blank_gap += 1
                if blank_gap > max_blank_gap:
                    break
                continue
            segments = _contiguous_int_segments(row_xs)
            segment = min(
                segments,
                key=lambda item: abs((x1 + (item[0] + item[1]) / 2.0) - center),
            )
            left = x1 + int(segment[0])
            right = x1 + int(segment[1])
            row_center = (left + right) / 2.0
            if ((right - left + 1) > max_width
                    or abs(row_center - center) > max_center_jump):
                break
            points.append((int(y), float(row_center), int(left), int(right)))
            center = row_center
            blank_gap = 0

        if len(points) >= min_height and (best is None or len(points) > len(best)):
            best = points

    if best is None:
        reason = (
            'no_top_thin_seed'
            if not has_top_thin_seed
            else 'insufficient_continuous_thin_height'
        )
        return (None, reason) if return_failure_reason else None
    trace = {
        'approx_x': int(approx_x),
        'reference_x': float(best[0][1]),
        'y_start': int(best[0][0]),
        'y_end': int(best[-1][0]),
        'points': best,
    }
    return (trace, None) if return_failure_reason else trace


def _build_per_tick_straightened_band(band: np.ndarray,
                                      candidate_xs: List[int],
                                      observed_period: float,
                                      include_candidate_states: bool = False,
                                      candidate_components: dict = None,
                                      relaxed_candidate_xs: set[int] = None,
                                      candidate_sources: dict[int, str] = None) -> tuple:
    """Compose only independently traced thin strokes in seam-normalized columns."""
    corrected = np.zeros_like(band)
    traces = []
    candidate_states = []
    for approx_x in sorted(set(int(x) for x in candidate_xs)):
        candidate_source = str(
            (candidate_sources or {}).get(int(approx_x), 'formal_projection')
        )
        component = (candidate_components or {}).get(int(approx_x))
        trace_width = None
        trace_jump = None
        trace_height = None
        component_width = 0
        if component:
            try:
                component_width = int(component.get('x_right', 0)) - int(
                    component.get('x_left', 0)
                ) + 1
            except (TypeError, ValueError):
                component_width = 0
            # A blurred stroke can be wider than the strict thin-line limit.
            # Use the connected component only as evidence to relax the debug
            # tracer; the formal detector continues to use the original band.
            if component_width > 0:
                trace_width = min(
                    14,
                    max(
                        8,
                        int(round(component_width * 0.75)),
                        int(round(max(3.0, observed_period) * 0.17)),
                    ),
                )
                trace_jump = min(6.0, max(4.0, component_width * 0.25))
                trace_height = max(18, int(round(band.shape[0] * 0.20)))
        trace, reason = _trace_vernier_tick_centerline(
            band,
            approx_x,
            observed_period,
            return_failure_reason=True,
            max_width=trace_width,
            max_center_jump=trace_jump,
            min_height=trace_height,
            seed_search_limit=max(
                18,
                min(
                    band.shape[0],
                    int(round(max(3.0, observed_period) * 1.25)),
                ),
            ),
        )
        relaxed = False
        if trace is None and (
            component is not None
            or int(approx_x) in (relaxed_candidate_xs or set())
        ):
            # A component or an independent periodic top-projection candidate
            # proves that this is worth one bounded retry for blur-expanded
            # pixels. The retry still requires a top seed and continuous
            # stroke; no pixels are fabricated when the retry fails.
            relaxed_width = 14
            relaxed_jump = min(
                6.0,
                max(4.0, float(component_width) * 0.40),
            )
            trace, relaxed_reason = _trace_vernier_tick_centerline(
                band,
                approx_x,
                observed_period,
                return_failure_reason=True,
                max_width=relaxed_width,
                max_center_jump=relaxed_jump,
                min_height=18,
                seed_search_limit=max(
                    18,
                    min(
                        band.shape[0],
                        int(round(max(3.0, observed_period) * 1.50)),
                    ),
                ),
            )
            if trace is not None:
                relaxed = True
                reason = None
            else:
                reason = relaxed_reason or reason
        if trace is None:
            candidate_states.append({
                'approx_x': int(approx_x),
                'status': 'untraced',
                'reason': reason,
                'relaxed_retry': relaxed,
                'source': candidate_source,
            })
            continue
        candidate_states.append({
            'approx_x': int(approx_x),
            'status': 'traced',
            'reason': None,
            'source': candidate_source,
            'reference_x': float(trace['reference_x']),
            'y_start': int(trace['y_start']),
            'y_end': int(trace['y_end']),
            'max_width': int(trace_width) if trace_width is not None else None,
            'max_center_jump': float(trace_jump) if trace_jump is not None else None,
            'min_height': int(trace_height) if trace_height is not None else None,
            'relaxed_retry': relaxed,
        })
        reference_x = float(trace['reference_x'])
        for y, center_x, left, right in trace['points']:
            shift = int(round(reference_x - center_x))
            dst_left = max(0, int(left) + shift)
            dst_right = min(band.shape[1] - 1, int(right) + shift)
            if dst_right >= dst_left:
                corrected[int(y), dst_left:dst_right + 1] = np.maximum(
                    corrected[int(y), dst_left:dst_right + 1],
                    band[int(y), int(left):int(right) + 1],
                )
        traces.append(trace)
    if include_candidate_states:
        return corrected, traces, candidate_states
    return corrected, traces


def _build_per_tick_continuous_display_band(
    band: np.ndarray,
    traces: List[dict],
    observed_period: float,
    max_gap_rows: int = 4,
) -> tuple:
    """Build a display-only continuous mask from independent tick traces.

    The strict mask intentionally contains only rows accepted by the thin
    stroke tracer.  This companion mask searches the original binary band in
    each trace's local direction, so source pixels after a strict early stop
    remain visible.  Only short gaps between two supported rows may be filled;
    synthetic pixels are returned in a separate mask and never feed formal
    detection or alignment.
    """
    if band is None or np.asarray(band).ndim != 2:
        empty = np.zeros((0, 0), dtype=np.uint8)
        return empty, empty.copy(), []

    source_band = np.asarray(band)
    height, width = source_band.shape
    continuous = np.zeros_like(source_band)
    synthetic = np.zeros_like(source_band)
    display_traces = []
    try:
        period = max(3.0, float(observed_period))
    except (TypeError, ValueError):
        period = 10.0
    max_gap_rows = max(0, int(max_gap_rows))
    search_radius = max(4, min(18, int(round(period * 0.28))))

    for trace in traces or []:
        raw_points = trace.get('points') or []
        points = []
        for point in raw_points:
            try:
                y, center, left, right = point
                y = int(y)
                left = max(0, int(left))
                right = min(width - 1, int(right))
                if 0 <= y < height and right >= left:
                    points.append((y, float(center), left, right))
            except (TypeError, ValueError):
                continue
        if not points:
            continue
        points.sort(key=lambda item: item[0])
        point_by_y = {point[0]: point for point in points}
        y_values = np.asarray([point[0] for point in points], dtype=float)
        x_values = np.asarray([point[1] for point in points], dtype=float)
        if len(points) >= 2 and float(np.ptp(y_values)) > 0:
            slope, intercept = np.polyfit(y_values, x_values, 1)
        else:
            slope = 0.0
            intercept = float(x_values[0])
        reference_x = float(trace.get('reference_x', points[0][1]))
        widths = np.asarray(
            [point[3] - point[2] + 1 for point in points], dtype=float
        )
        max_width = max(4, min(16, int(round(float(np.median(widths)) * 2.5))))

        def predicted_center(y: int) -> float:
            return float(slope * float(y) + intercept)

        def source_segment(y: int, expected_center: float):
            if not (0 <= y < height):
                return None
            row_xs = np.flatnonzero(source_band[y] > 0)
            if row_xs.size == 0:
                return None
            segments = _contiguous_int_segments(row_xs)
            nearby = []
            for start, end in segments:
                left = int(start)
                right = int(end)
                center = (left + right) / 2.0
                distance = abs(center - expected_center)
                if distance > search_radius:
                    continue
                segment_width = right - left + 1
                # A very wide segment is normally a digit or seam.  A
                # moderately wide segment may contain the tick, so retain
                # only a narrow window around the predicted center.
                if segment_width > max_width * 3:
                    continue
                if segment_width > max_width:
                    half = max_width // 2
                    left = max(left, int(round(expected_center)) - half)
                    right = min(right, left + max_width - 1)
                    if right < left or not np.any(source_band[y, left:right + 1] > 0):
                        continue
                    center = (left + right) / 2.0
                nearby.append((distance, segment_width, left, right, center))
            if not nearby:
                return None
            _, _, left, right, center = min(
                nearby, key=lambda item: (item[0], item[1])
            )
            return int(left), int(right), float(center)

        # Use the strict trace as an anchor, then search the original band
        # for additional rows along its fitted local direction.
        candidates = {}
        for y in range(height):
            if y in point_by_y:
                _, center, left, right = point_by_y[y]
                candidates[y] = (left, right, center, False)
                continue
            segment = source_segment(y, predicted_center(y))
            if segment is not None:
                left, right, center = segment
                candidates[y] = (left, right, center, False)

        # Keep only runs connected to at least one strict trace point.  This
        # prevents a nearby digit run from becoming an independent display
        # tick when a long gap separates it from the actual stroke.
        candidate_rows = sorted(candidates)
        runs = []
        if candidate_rows:
            run = [candidate_rows[0]]
            for previous, current in zip(candidate_rows, candidate_rows[1:]):
                if current - previous - 1 <= max_gap_rows:
                    run.append(current)
                else:
                    runs.append(run)
                    run = [current]
            runs.append(run)
        kept_rows = set()
        filled_gap_rows = 0
        synthetic_gap_rows = 0
        for run in runs:
            if not any(row in point_by_y for row in run):
                continue
            kept_rows.update(run)
            for previous, current in zip(run, run[1:]):
                missing = current - previous - 1
                if missing <= 0 or missing > max_gap_rows:
                    continue
                previous_center = candidates[previous][2]
                current_center = candidates[current][2]
                for y in range(previous + 1, current):
                    ratio = (y - previous) / float(current - previous)
                    expected = previous_center + ratio * (
                        current_center - previous_center
                    )
                    segment = source_segment(y, expected)
                    if segment is not None:
                        left, right, center = segment
                        candidates[y] = (left, right, center, False)
                    else:
                        candidates[y] = (
                            int(round(expected)), int(round(expected)), expected, True
                        )
                        synthetic_gap_rows += 1
                    kept_rows.add(y)
                    filled_gap_rows += 1

        written_rows = 0
        synthetic_pixels = 0
        for y in sorted(kept_rows):
            left, right, center, is_synthetic = candidates[y]
            if is_synthetic:
                destination = int(round(reference_x))
                if 0 <= destination < width:
                    continuous[y, destination] = np.maximum(
                        continuous[y, destination], np.asarray(255, dtype=source_band.dtype)
                    )
                    synthetic[y, destination] = np.asarray(255, dtype=source_band.dtype)
                    written_rows += 1
                    synthetic_pixels += 1
                continue
            shift = int(round(reference_x - center))
            destination_left = max(0, left + shift)
            destination_right = min(width - 1, right + shift)
            if destination_right < destination_left:
                continue
            continuous[y, destination_left:destination_right + 1] = np.maximum(
                continuous[y, destination_left:destination_right + 1],
                source_band[y, left:right + 1],
            )
            written_rows += 1

        display_traces.append({
            'approx_x': int(trace.get('approx_x', round(reference_x))),
            'reference_x': reference_x,
            'y_start': int(min(kept_rows)) if kept_rows else None,
            'y_end': int(max(kept_rows)) if kept_rows else None,
            'source_rows': int(sum(
                1 for row in kept_rows if not candidates[row][3]
            )),
            'extended_rows': int(max(
                0, len(kept_rows) - len(points)
            )),
            'filled_gap_rows': int(filled_gap_rows),
            'synthetic_gap_rows': int(synthetic_gap_rows),
            'synthetic_pixels': int(synthetic_pixels),
            'written_rows': int(written_rows),
        })

    return continuous, synthetic, display_traces


def _build_tick_candidates(band: np.ndarray,
                           tick_xs: List[int],
                           observed_period: float,
                           projection: np.ndarray) -> List[dict]:
    ordered_xs = sorted(set(int(x) for x in tick_xs))
    candidates = [{
        'x_projection': int(x),
        'projection_strength': (
            float(projection[x]) if 0 <= x < len(projection) else 0.0
        ),
        'component_id': None,
        'component': None,
        'accepted': True,
        'rejection_reason': None,
    } for x in ordered_xs]
    components = _extract_vernier_tick_components(band, observed_period)
    search_radius = (
        max(4, min(12, int(round(observed_period * 0.42))))
        if observed_period > 0 else 8
    )

    edges = []
    for candidate_index, candidate in enumerate(candidates):
        for component_index, component in enumerate(components):
            distance = abs(
                float(component['x_near_seam']) - float(candidate['x_projection'])
            )
            if distance <= search_radius:
                edges.append((
                    distance,
                    -float(candidate['projection_strength']),
                    -int(component['area']),
                    candidate_index,
                    component_index,
                ))

    assigned_candidates = set()
    assigned_components = set()
    for _, _, _, candidate_index, component_index in sorted(edges):
        if candidate_index in assigned_candidates or component_index in assigned_components:
            continue
        component = components[component_index]
        candidate = candidates[candidate_index]
        candidate['component_id'] = int(component['component_id'])
        candidate['component'] = component
        assigned_candidates.add(candidate_index)
        assigned_components.add(component_index)
    return candidates


def _candidate_quality(candidate: dict) -> tuple:
    component = candidate.get('component')
    return (
        1 if component is not None else 0,
        float(candidate.get('projection_strength', 0.0)),
        int(component.get('area', 0)) if component else 0,
    )


def _suppress_duplicate_candidates(candidates: List[dict],
                                   observed_period: float) -> tuple:
    if not candidates:
        return [], []
    ordered = sorted(candidates, key=lambda item: float(item['x_projection']))
    duplicate_gap = max(
        3.0,
        float(observed_period) * float(config.vernier_scale.duplicate_period_ratio),
    )
    groups = []
    current = [ordered[0]]
    group_anchor_x = float(ordered[0]['x_projection'])
    for candidate in ordered[1:]:
        # Compare with the first peak in the group.  Comparing only adjacent
        # peaks chains several close fragments across a full observed period.
        if float(candidate['x_projection']) - group_anchor_x < duplicate_gap:
            current.append(candidate)
        else:
            groups.append(current)
            current = [candidate]
            group_anchor_x = float(candidate['x_projection'])
    groups.append(current)

    accepted = []
    rejected = []
    for group in groups:
        winner = max(group, key=_candidate_quality)
        accepted.append(winner)
        for candidate in group:
            if candidate is winner:
                continue
            rejected_candidate = dict(candidate)
            rejected_candidate['accepted'] = False
            rejected_candidate['rejection_reason'] = 'duplicate_within_observed_period'
            rejected.append(rejected_candidate)

    accepted.sort(key=lambda item: float(item['x_projection']))
    xs = np.asarray([float(item['x_projection']) for item in accepted], dtype=float)
    for index, candidate in enumerate(accepted):
        neighbor_gaps = []
        if index > 0:
            neighbor_gaps.append(xs[index] - xs[index - 1])
        if index + 1 < len(xs):
            neighbor_gaps.append(xs[index + 1] - xs[index])
        candidate['spacing_error'] = (
            min(abs(gap - observed_period) for gap in neighbor_gaps) / observed_period
            if neighbor_gaps and observed_period > 0 else 0.0
        )
    return accepted, rejected


def _build_ticks_from_band_detection(band_detection: dict,
                                     long_tick_factor: float = None) -> List[dict]:
    """Build tick dictionaries directly from the narrow-band projection result."""
    if not band_detection:
        return []
    band = band_detection.get('band')
    if band is None or band.size == 0:
        return []
    gray_band = band_detection.get('gray_band')
    if long_tick_factor is None:
        long_tick_factor = config.vernier_scale.long_tick_factor

    y_offset = int(band_detection.get('band_y1', 0))
    x_offset = int(band_detection.get('x1', 0))
    h, w = band.shape[:2]
    ticks = []
    candidates = list(band_detection.get('tick_candidates') or [])
    if not candidates:
        candidates = [{
            'x_projection': int(x),
            'projection_strength': 0.0,
            'component_id': None,
            'component': None,
            'spacing_error': 0.0,
        } for x in band_detection.get('tick_xs_local', [])]
    for candidate in candidates:
        x = int(candidate['x_projection'])
        if x < 0 or x >= w:
            continue
        component = candidate.get('component')
        if component is None:
            refined = _refine_vernier_tick_from_band(
                band, x, band_detection.get('expected_gap', 0.0)
            )
        else:
            refined = {
                'x': float(component['x_near_seam']),
                'x_top': float(component['x_near_seam']),
                'x_bottom': float(component['x_bottom']),
                'y_start': int(component['y_start']),
                'y_end': int(component['y_end']),
                'slope': 0.0,
            }
        if refined is None:
            strip = band[:, max(0, x - 2):min(w, x + 3)] > 0
            row_on = np.mean(strip, axis=1) > 0.16 if strip.size else np.zeros(h, dtype=bool)
            ys = np.where(row_on)[0]
            if len(ys) > 0:
                y_start_local = int(ys[0])
                y_end_local = int(ys[-1])
            else:
                y_start_local = 0
                y_end_local = h - 1
            x_refined = float(x)
            x_top = float(x)
            x_bottom = float(x)
            slope = 0.0
        else:
            x_refined = float(refined['x'])
            y_start_local = int(refined['y_start'])
            y_end_local = int(refined['y_end'])
            x_top = float(refined['x_top'])
            x_bottom = float(refined['x_bottom'])
            slope = float(refined['slope'])
        ref_y1 = min(h - 1, 2) if h > 2 else 0
        ref_y2 = min(h, ref_y1 + 10)
        x_precise = refine_tick_x_subpixel(
            gray_band, int(round(x_refined)), ref_y1, ref_y2
        ) if gray_band is not None else x_refined
        y_start = y_start_local + y_offset
        y_end = y_end_local + y_offset
        length = max(1, y_end - y_start)
        ticks.append({
            'x': int(round(x_precise)) + x_offset,
            'x_projection': x + x_offset,
            'x_refined': x_refined + x_offset,
            'x_precise': x_precise + x_offset,
            'x_top': x_top + x_offset,
            'x_bottom': x_bottom + x_offset,
            'y_start': y_start,
            'y_end': y_end,
            'y_mid': int(round((y_start + y_end) / 2.0)),
            'length': length,
            'projection_strength': float(candidate.get('projection_strength', 0.0)),
            'component_id': candidate.get('component_id'),
            'component_area': int(component['area']) if component else 0,
            'component_height': int(component['y_end'] - component['y_start'] + 1) if component else 0,
            'component_bottom_y': int(component['y_end']) if component else 0,
            'spacing_error': float(candidate.get('spacing_error', 0.0)),
            'fit_slope': slope,
            'source': 'band_projection_refined',
        })

    _classify_vernier_tick_lengths(ticks)
    return sorted(ticks, key=lambda t: t['x'])


def _classify_vernier_tick_lengths(ticks: List[dict]) -> None:
    for tick in ticks:
        tick['is_long'] = False
        tick['long_state'] = 'unknown'

    supported = [
        tick for tick in ticks
        if tick.get('component_id') is not None
        and float(tick.get('component_bottom_y', 0)) > 0
    ]
    if len(supported) < 4:
        return

    values = np.asarray(
        [float(tick['component_bottom_y']) for tick in supported], dtype=float
    )
    low = float(np.percentile(values, 25))
    high = float(np.percentile(values, 75))
    if high <= low:
        return

    labels = np.zeros(len(values), dtype=bool)
    for _ in range(12):
        next_labels = np.abs(values - high) < np.abs(values - low)
        if np.array_equal(next_labels, labels) and np.any(next_labels):
            labels = next_labels
            break
        labels = next_labels
        if not np.any(labels) or np.all(labels):
            return
        low = float(np.mean(values[~labels]))
        high = float(np.mean(values[labels]))

    short_count = int(np.sum(~labels))
    long_count = int(np.sum(labels))
    separation = (high - low) / max(low, 1.0)
    if (short_count < 2 or long_count < 2
            or separation < config.vernier_scale.long_cluster_min_separation_ratio):
        return

    for tick, is_long in zip(supported, labels):
        tick['is_long'] = bool(is_long)
        tick['long_state'] = 'long' if is_long else 'short'

    for tick in ticks:
        if tick.get('component_id') is not None:
            continue
        measured_length = float(tick.get('length', 0))
        if measured_length <= 0:
            continue
        is_long = abs(measured_length - high) < abs(measured_length - low)
        tick['is_long'] = bool(is_long)
        tick['long_state'] = (
            'long_from_measured_stroke' if is_long else 'short_from_measured_stroke'
        )


def _refine_vernier_tick_from_band(band: np.ndarray,
                                   approx_x: int,
                                   expected_gap: float) -> dict:
    if band is None or band.size == 0:
        return None
    h, w = band.shape[:2]
    if h <= 0 or w <= 0:
        return None

    approx_x = int(round(approx_x))
    radius = max(3, min(6, int(round(expected_gap * 0.20)) if expected_gap > 0 else 5))
    x1 = max(0, approx_x - radius)
    x2 = min(w - 1, approx_x + radius)
    if x2 <= x1:
        return None

    crop = band[:, x1:x2 + 1] > 0
    if crop.size == 0:
        return None

    centers = []
    local_approx = approx_x - x1
    max_seg_w = max(3, int(round(radius * 1.2)))
    ref_rows = max(8, min(14, int(round(expected_gap * 0.45)) if expected_gap > 0 else 10))
    ref_y1 = min(h - 1, 2) if h > 2 else 0
    ref_y2 = min(h, ref_y1 + ref_rows)
    for y in range(ref_y1, ref_y2):
        xs = np.where(crop[y])[0]
        if len(xs) == 0:
            continue

        segs = _contiguous_int_segments(xs)
        if not segs:
            continue
        seg = min(
            segs,
            key=lambda s: (
                abs(((s[0] + s[1]) / 2.0) - local_approx),
                -(s[1] - s[0] + 1),
            )
        )
        seg_w = seg[1] - seg[0] + 1
        if seg_w > max_seg_w:
            continue

        center = x1 + (seg[0] + seg[1]) / 2.0
        if abs(center - approx_x) > radius * 0.90:
            continue
        centers.append(center)

    x_ref = float(np.median(centers)) if centers else float(approx_x)
    row_on = np.mean(crop, axis=1) > 0.12
    ys = np.where(row_on)[0]
    if len(ys) > 0:
        y_start = int(ys[0])
        y_end = int(ys[-1])
    else:
        y_start = 0
        y_end = h - 1
    if y_end <= y_start:
        y_end = min(h - 1, y_start + 1)

    return {
        'x': max(0.0, min(float(w - 1), x_ref)),
        'x_top': max(0.0, min(float(w - 1), x_ref)),
        'x_bottom': max(0.0, min(float(w - 1), x_ref)),
        'y_start': y_start,
        'y_end': y_end,
        'slope': 0.0,
    }


def _contiguous_int_segments(xs: np.ndarray) -> List[tuple]:
    if xs is None or len(xs) == 0:
        return []
    xs = np.array(xs, dtype=int)
    segments = []
    start = int(xs[0])
    prev = int(xs[0])
    for value in xs[1:]:
        value = int(value)
        if value == prev + 1:
            prev = value
            continue
        segments.append((start, prev))
        start = value
        prev = value
    segments.append((start, prev))
    return segments


def _find_corresponding_mapped_tick(corrected_tick: dict,
                                    corrected_ticks: List[dict],
                                    mapped_ticks: List[dict]) -> dict:
    if corrected_tick is None or not corrected_ticks or not mapped_ticks:
        return None
    best_idx = min(
        range(min(len(corrected_ticks), len(mapped_ticks))),
        key=lambda i: abs(corrected_ticks[i]['x'] - corrected_tick['x'])
    )
    return mapped_ticks[best_idx]


def _find_zero_from_band_detection(vernier_ticks: List[dict],
                                   band_detection: dict,
                                   make_debug: bool = True):
    """Locate vernier zero from the already computed narrow-band ticks."""
    if not band_detection or not vernier_ticks:
        return None, None

    x1 = int(band_detection['x1'])
    x2 = int(band_detection['x2'])
    band = band_detection['band']
    proj_norm = band_detection['proj_norm']
    smooth = band_detection['smooth']
    peaks = band_detection['peaks']
    valleys = band_detection['valleys']
    tick_xs = list(band_detection['tick_xs_local'])
    h_th = float(band_detection['h_th'])
    A = float(band_detection['A'])
    B = float(band_detection['B'])
    typical_gap = float(band_detection['expected_gap'])

    if len(tick_xs) < 3 or typical_gap <= 2.0:
        return None, None

    zero_local_x = int(tick_xs[0])
    zero_global_x = x1 + zero_local_x
    tol = max(3.0, typical_gap * 0.35)
    ticks_in_range = [t for t in vernier_ticks if x1 - typical_gap <= t['x'] <= x2 + typical_gap]
    if ticks_in_range:
        nearest = min(ticks_in_range, key=lambda t: abs(t['x'] - zero_global_x))
        found_tick = nearest if abs(nearest['x'] - zero_global_x) <= tol else {'x': zero_global_x}
    else:
        found_tick = {'x': zero_global_x}

    roi_x1, roi_x2 = band_detection.get('vernier_tick_roi', (tick_xs[0], tick_xs[-1]))
    valley_candidates = [(0, float(roi_x2 - roi_x1), int(roi_x1), int(roi_x2), len(tick_xs))]
    best_valley = valley_candidates[0]

    vis = None
    if make_debug:
        vis = _make_valley_projection_vis(
            band, proj_norm, smooth, peaks, valleys, tick_xs, x1,
            h_th, A, B, typical_gap,
            valley_candidates, best_valley, found_tick)
    return found_tick, vis


def _make_valley_projection_vis(band: np.ndarray,
                                 proj_norm: np.ndarray,
                                 smooth: np.ndarray,
                                 peaks: list,
                                 valleys: list,
                                 tick_xs: list,
                                 x_offset: int,
                                 h_th: float,
                                 A: float,
                                 B: float,
                                 typical_gap: float,
                                 valley_candidates: list,
                                 best_valley: tuple,
                                 found_tick: dict = None) -> np.ndarray:
    """可视化：投影曲线 + 峰/谷标记 + 阈值 h + 刻度线 + 谷底候选 + 零线"""
    band_h, band_w = band.shape[:2]
    n = len(smooth)
    plot_w = max(700, n + 80)
    plot_h = 380
    margin = 40

    vis = np.zeros((plot_h + band_h + 30, plot_w, 3), dtype=np.uint8)
    vis[:] = (20, 20, 28)

    # ── 顶部：二值图缩略 ──
    bw_display = cv2.cvtColor(band, cv2.COLOR_GRAY2BGR)
    thumb_w = min(band_w, plot_w - margin * 2)
    thumb_h = band_h
    if band_h > 0 and band_w > 0:
        thumb = cv2.resize(bw_display, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
        ox = margin
        vis[:thumb_h, ox:ox + thumb_w] = thumb
        cv2.putText(vis, f"Auto tick band (h={band_h}px, w={band_w}px)", (margin, thumb_h + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 150), 1)

    # ── 图表区域 ──
    chart_y0 = band_h + 28
    chart_h = plot_h - 8
    chart_w = n
    chart_left = margin

    cv2.rectangle(vis, (chart_left, chart_y0),
                  (chart_left + chart_w, chart_y0 + chart_h), (35, 35, 42), -1)

    # 坐标轴
    cv2.line(vis, (chart_left, chart_y0), (chart_left, chart_y0 + chart_h), (80, 80, 90), 1)
    mid_y = chart_y0 + chart_h // 2
    cv2.line(vis, (chart_left, mid_y), (chart_left + chart_w, mid_y), (50, 50, 58), 1, cv2.LINE_AA)

    # 原始投影（浅灰柱状）
    for i in range(0, n, max(1, n // 700)):
        bar_h = int(proj_norm[i] * chart_h * 0.5)
        x = chart_left + i
        cv2.line(vis, (x, mid_y), (x, mid_y - bar_h), (50, 50, 62), 1)

    # 平滑曲线
    pts = []
    for i in range(n):
        y = chart_y0 + int(chart_h * 0.5 - smooth[i] * chart_h * 0.5)
        pts.append((chart_left + i, y))
    for i in range(len(pts) - 1):
        cv2.line(vis, pts[i], pts[i + 1], (100, 200, 255), 2, cv2.LINE_AA)

    # 峰标记（绿色圆点）和谷标记（红色圆点）
    for x, v in peaks:
        px = chart_left + x
        py = chart_y0 + int(chart_h * 0.5 - v * chart_h * 0.5)
        cv2.circle(vis, (px, py), 2, (0, 255, 100), -1)
    for x, v in valleys:
        px = chart_left + x
        py = chart_y0 + int(chart_h * 0.5 - v * chart_h * 0.5)
        cv2.circle(vis, (px, py), 2, (100, 140, 255), -1)

    # 阈值线 h (黄色)
    h_y = chart_y0 + int(chart_h * 0.5 - h_th * chart_h * 0.5)
    cv2.line(vis, (chart_left, h_y), (chart_left + chart_w, h_y),
             (0, 220, 220), 2, cv2.LINE_AA)
    cv2.putText(vis, f"h_th={h_th:.3f} (A={A:.3f} + B={B:.3f}) / 2", (chart_left + 4, h_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 220, 220), 1)

    # A 线 (绿色) 和 B 线 (蓝色)
    a_y = chart_y0 + int(chart_h * 0.5 - A * chart_h * 0.5)
    cv2.line(vis, (chart_left, a_y), (chart_left + chart_w, a_y),
             (0, 180, 80), 1, cv2.LINE_AA)
    cv2.putText(vis, f"peak_median_top80%={A:.3f}", (chart_left + chart_w - 260, a_y - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 180, 80), 1)
    b_y = chart_y0 + int(chart_h * 0.5 - B * chart_h * 0.5)
    cv2.line(vis, (chart_left, b_y), (chart_left + chart_w, b_y),
             (255, 140, 80), 1, cv2.LINE_AA)
    cv2.putText(vis, f"valley_median_top80%={B:.3f}", (chart_left + chart_w - 260, b_y - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 140, 80), 1)

    # 筛选后的刻度线（高于 h_th 的峰）
    for tx in tick_xs:
        px = chart_left + tx
        cv2.line(vis, (px, chart_y0), (px, chart_y0 + chart_h), (0, 200, 100), 1, cv2.LINE_AA)

    # 谷底候选区（浅红半透明高亮）
    for cand in valley_candidates:
        _, _, left_x, right_x, *_ = cand
        cv2.rectangle(vis, (chart_left + left_x, chart_y0),
                      (chart_left + right_x, chart_y0 + chart_h),
                      (90, 60, 110), 1, cv2.LINE_AA)

    # 最佳谷底（选中的：第一个满足条件的，品红色框 + 标签）
    if best_valley:
        _, _, best_left_x, best_right_x, *rest = best_valley
        hits = rest[0] if rest else 0
        cv2.rectangle(vis, (chart_left + best_left_x, chart_y0),
                      (chart_left + best_right_x, chart_y0 + chart_h), (220, 50, 120), 2, cv2.LINE_AA)
        mid_gap_x = chart_left + (best_left_x + best_right_x) // 2
        cv2.putText(vis, f"ZERO CAND hits={hits}", (mid_gap_x - 40, chart_y0 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (220, 50, 120), 2)

    # 找零线高亮（粗亮绿线）
    if found_tick:
        zx = int(found_tick['x']) - x_offset
        if 0 <= zx < n:
            zpx = chart_left + zx
            cv2.line(vis, (zpx, chart_y0 - 10), (zpx, chart_y0 + chart_h),
                     (50, 255, 50), 3, cv2.LINE_AA)
            cv2.circle(vis, (zpx, chart_y0 + 16), 8, (50, 255, 50), -1)
            cv2.putText(vis, "ZERO", (zpx + 10, chart_y0 + 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 255, 50), 2)

    # 间距标注
    cv2.putText(vis, f"typical_gap={typical_gap:.0f}px | {len(tick_xs)} ticks above h | {len(valley_candidates)} valley candidates",
                (chart_left + 4, chart_y0 + chart_h - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (150, 150, 170), 1)

    # 标题
    cv2.putText(vis, "Zero-Line Detection (valley pair + tick segments)", (margin, band_h + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 220), 1)

    # 图例
    legend_y = chart_y0 + chart_h + 2
    cv2.circle(vis, (margin + 6, legend_y - 6), 3, (0, 255, 100), -1)
    cv2.putText(vis, "peak", (margin + 14, legend_y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 255, 100), 1)
    cx = margin + 60
    cv2.circle(vis, (cx + 6, legend_y - 6), 3, (100, 140, 255), -1)
    cv2.putText(vis, "valley", (cx + 14, legend_y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (100, 140, 255), 1)
    cx += 80
    cv2.line(vis, (cx, legend_y), (cx + 24, legend_y), (0, 220, 220), 2)
    cv2.putText(vis, "h_th", (cx + 28, legend_y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 220, 220), 1)
    cx += 70
    cv2.rectangle(vis, (cx, legend_y - 8), (cx + 24, legend_y + 8), (220, 50, 120), 2)
    cv2.putText(vis, "gap", (cx + 28, legend_y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (220, 50, 120), 1)

    if found_tick:
        status = "ZERO FOUND"
        sc = (50, 255, 50)
    else:
        status = "NOT FOUND"
        sc = (255, 100, 100)
    cv2.putText(vis, f"Result: {status}", (plot_w - 200, legend_y + 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, sc, 1)

    return vis


def recognize_vernier_scale(region: dict,
                             main_gap: float,
                             color_region: np.ndarray = None,
                             main_ticks: List[dict] = None,
                             make_debug: bool = True) -> dict:
    """Vernier detection: valley-bounded range + split-anchored tick localization."""
    img = region['image']
    h, w = img.shape

    if main_gap <= 0:
        main_gap = 10.0

    binary = _foreground_binary_from_region(region.get('binary'), img)
    if binary is None:
        binary = cv2.adaptiveThreshold(
            img, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=config.vernier_scale.adaptive_block_size,
            C=config.vernier_scale.adaptive_C
        )
    if np.sum(binary > 0) < img.shape[0] * img.shape[1] * 0.03:
        _, binary = cv2.threshold(img, 0, 255,
                                  cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    region['binary'] = binary

    vproj = np.sum(binary, axis=0).astype(float)
    vproj_norm = vproj / np.max(vproj) if np.max(vproj) > 0 else vproj

    tick_band = region.get('tick_band')
    if tick_band is not None:
        tick_band = (
            max(0, int(tick_band[0])),
            min(h, int(tick_band[1]) + int(config.vernier_scale.tick_band_bottom_pad)),
        )
    band_detection = _detect_vernier_band_projection(
        binary, main_gap, img,
        tick_band=tick_band,
        make_debug=make_debug,
    )
    vernier_xs = np.array(
        band_detection['tick_xs_global'] if band_detection else [],
        dtype=int
    )
    vernier_ticks = []
    if len(vernier_xs) >= config.vernier_scale.min_tick_count:
        vernier_ticks = _build_ticks_from_band_detection(
            band_detection,
            long_tick_factor=config.vernier_scale.long_tick_factor
        )
        vernier_ticks = dedupe_ticks_by_relative_gap(vernier_ticks, gap_ratio=0.45)
        _classify_vernier_tick_lengths(vernier_ticks)

    if len(vernier_ticks) < config.vernier_scale.min_tick_count:
        reason = (
            'no_reliable_valley_bounded_tick_range'
            if band_detection is None else 'insufficient_vernier_tick_candidates'
        )
        return _empty_vernier_result(reason)

    precision = 0.02
    vernier_xs = np.array([t['x'] for t in vernier_ticks], dtype=int)
    v_gap = float(np.median(np.diff([t['x'] for t in vernier_ticks]))) if len(vernier_ticks) >= 2 else 0.0

    zero_tick, valley_vis = _find_zero_from_band_detection(
        vernier_ticks, band_detection, make_debug=make_debug
    )
    zero_x = float(zero_tick.get('x_precise', zero_tick['x'])) if zero_tick else float(vernier_ticks[0].get('x_precise', vernier_ticks[0]['x']))

    clean_vernier = [t for t in vernier_ticks if t['x'] >= zero_x - max(v_gap, 1.0) * 0.4]
    if len(clean_vernier) >= config.vernier_scale.min_tick_count:
        vernier_ticks = clean_vernier
    vernier_ticks.sort(key=lambda t: t['x'])

    corrected_ticks = [dict(t) for t in vernier_ticks]
    zero_x_corrected = float(zero_x)

    standardization = None
    if make_debug:
        standardization = _build_vernier_standardization(
            band_detection, corrected_ticks
        )
        band_detection['standardization'] = standardization

    mapped_ticks = _map_ticks_to_original(corrected_ticks, region)
    zero_y = None
    if zero_tick is not None:
        zero_y = zero_tick.get('y_mid', None)
    if zero_y is None and corrected_ticks:
        zero_y = float(np.median([t.get('y_mid', 0) for t in corrected_ticks]))
    zero_x = _map_x_to_original(zero_x_corrected, region, zero_y)
    vernier_xs = np.array([t['x'] for t in corrected_ticks], dtype=int)

    vis_ticks = None
    if make_debug:
        tick_view = _draw_vernier_ticks(
            region, binary, corrected_ticks, vproj_norm, vernier_xs,
            zero_x_corrected, band_detection=band_detection,
            standardization=standardization,
        )
        component_view = _draw_vernier_component_view(band_detection)
        vis_ticks = _stack_vernier_debug_views(
            [tick_view, valley_vis, component_view]
        )

    vernier_reading, aligned_tick, align_conf, alignment_info = find_best_alignment(
        mapped_ticks, precision, main_ticks, main_gap=main_gap
    )
    aligned_tick_corrected = _find_corresponding_mapped_tick(
        aligned_tick, mapped_ticks, corrected_ticks
    )

    vis_alignment = None
    if make_debug:
        vis_alignment = _draw_alignment(
            region, color_region, corrected_ticks,
            main_gap, zero_x_corrected, aligned_tick_corrected, align_conf,
            alignment_ambiguity=alignment_info.get('ambiguity'),
        )

    return {
        'vernier_ticks': mapped_ticks,
        'precision': precision,
        'vernier_reading': vernier_reading,
        'zero_x': zero_x,
        'aligned_tick': aligned_tick,
        'alignment_confidence': align_conf,
        'alignment_info': alignment_info,
        'alignment_ambiguity': alignment_info.get('ambiguity'),
        'vis_ticks': vis_ticks,
        'vis_alignment': vis_alignment,
        'vis_valley': valley_vis,
        'vproj_norm': vproj_norm,
        'vernier_peaks': vernier_xs,
        'vernier_band_detection': band_detection,
        'standardization': standardization,
    }
