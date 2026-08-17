"""
游标卡尺识别 — 通用工具函数
"""

import cv2
import numpy as np
from typing import List
from .config import config


def rotate_image(img: np.ndarray, angle: float) -> np.ndarray:
    """旋转图像，不裁剪，空白区域填白色"""
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    ca, sa = abs(M[0, 0]), abs(M[0, 1])
    nW, nH = int(h * sa + w * ca), int(h * ca + w * sa)
    M[0, 2] += nW / 2 - w / 2
    M[1, 2] += nH / 2 - h / 2
    if len(img.shape) == 3:
        border = (255, 255, 255)
    else:
        border = 255
    return cv2.warpAffine(img, M, (nW, nH),
                          borderMode=cv2.BORDER_CONSTANT,
                          borderValue=border)


def find_peaks_adaptive(signal: np.ndarray, min_dist: int = 3,
                         threshold_factor: float = 0.3) -> np.ndarray:
    """自适应阈值找峰值：阈值为 signal 均值 + threshold_factor×标准差"""
    mu = float(np.mean(signal))
    sigma = float(np.std(signal))
    th = max(mu + threshold_factor * sigma, 0.02)

    peaks = []
    n = len(signal)
    for i in range(min_dist, n - min_dist):
        if signal[i] <= th:
            continue
        is_peak = True
        for d in range(1, min_dist + 1):
            if signal[i] <= signal[i - d] or signal[i] <= signal[i + d]:
                is_peak = False
                break
        if is_peak:
            peaks.append(i)
    return np.array(peaks, dtype=int)


def _tick_row_threshold(col: np.ndarray,
                        max_factor: float = 0.40,
                        single_stroke_cap: float = 0.80) -> float:
    """Threshold a 7px-wide vertical strip without rejecting 1px tick strokes."""
    if col is None or len(col) == 0:
        return 30.0
    dynamic = float(np.max(col)) * max_factor
    one_pixel_cap = 255.0 * single_stroke_cap
    return max(30.0, min(dynamic, one_pixel_cap))


def extract_ticks_from_binary(binary: np.ndarray,
                               approx_xs: np.ndarray,
                               min_length_ratio: float = 0.25,
                               long_tick_factor: float = None,
                               recover_short_ticks: bool = False,
                               short_tick_min_contiguous_ratio: float = 0.60,
                               short_tick_min_foreground_factor: float = 2.00,
                               short_tick_period_tolerance: float = 0.30) -> List[dict]:
    """在指定 x 坐标附近精确提取刻线起止点。

    v6: 加入"刻线长度 ≥ 区域高度 × min_length_ratio"硬约束，
        过滤掉短伪刻线（如 OCR 数字笔画、噪声、阴影边缘）。
    v6.5: long_tick_factor 改为参数，调用方传入主尺/游标尺各自的 config 值。
    """
    h, w = binary.shape
    min_len_px = max(6, int(h * min_length_ratio))
    if long_tick_factor is None:
        long_tick_factor = config.main_scale.long_tick_factor
    ticks = []
    coarse_xs = sorted({int(x) for x in approx_xs if 3 <= int(x) < w - 3})
    coarse_period = 0.0
    if len(coarse_xs) >= 3:
        diffs = np.diff(coarse_xs)
        positive = diffs[diffs > 1]
        if positive.size:
            coarse_period = float(np.median(positive))

    def has_periodic_neighbors(index: int) -> bool:
        if coarse_period <= 0 or index <= 0 or index >= len(coarse_xs) - 1:
            return False
        left_gap = coarse_xs[index] - coarse_xs[index - 1]
        right_gap = coarse_xs[index + 1] - coarse_xs[index]
        tolerance = coarse_period * short_tick_period_tolerance
        return (abs(left_gap - coarse_period) <= tolerance and
                abs(right_gap - coarse_period) <= tolerance)

    for coarse_index, x in enumerate(coarse_xs):

        # 取 x 附近的列（±3像素），求和得到该位置的垂直投影
        strip = binary[:, max(0, x - 3):min(w, x + 4)]
        col = np.sum(strip, axis=1)

        # v6: 列强度阈值收紧到 max*0.40（之前 0.25 太宽松）
        threshold = _tick_row_threshold(col)
        indices = np.where(col > threshold)[0]

        segs = contiguous_segments(indices, min_len=5)
        if not segs:
            continue

        ys, ye = max(segs, key=lambda s: s[1] - s[0])
        length = ye - ys
        is_recovered_short = (
            recover_short_ticks and
            length < min_len_px and
            length >= int(np.ceil(min_len_px * short_tick_min_contiguous_ratio)) and
            len(indices) >= int(np.ceil(min_len_px * short_tick_min_foreground_factor)) and
            has_periodic_neighbors(coarse_index)
        )
        if length < min_len_px and not is_recovered_short:
            continue

        x_refined = _refine_tick_x(binary, x, ys, ye,
                                   search_radius=max(4, min(10, min_len_px // 2)))
        ticks.append({
            'x': int(x_refined),
            'y_start': int(ys),
            'y_end': int(ye),
            'y_mid': int((ys + ye) / 2),
            'length': int(length),
            'is_recovered_short': bool(is_recovered_short),
        })

    if ticks:
        ml = float(np.median([t['length'] for t in ticks]))
        for t in ticks:
            t['is_long'] = t['length'] > ml * long_tick_factor

    return ticks


def dedupe_ticks_by_relative_gap(ticks: List[dict],
                                 gap_ratio: float = 0.45) -> List[dict]:
    if len(ticks) < 3:
        return sorted(ticks, key=lambda item: item['x'])

    ordered = sorted(ticks, key=lambda item: float(item['x']))
    xs = np.asarray([float(item['x']) for item in ordered], dtype=float)
    diffs = np.diff(xs)
    positive = diffs[diffs > 0]
    if positive.size == 0:
        return [max(ordered, key=_tick_quality)]

    tolerance = max(3.0, float(np.median(positive)) * float(gap_ratio))
    groups = []
    current = [ordered[0]]
    group_start = float(ordered[0]['x'])
    for tick in ordered[1:]:
        if float(tick['x']) - group_start <= tolerance:
            current.append(tick)
        else:
            groups.append(current)
            current = [tick]
            group_start = float(tick['x'])
    groups.append(current)
    return [max(group, key=_tick_quality) for group in groups]


def _tick_quality(tick: dict):
    return (
        float(tick.get('projection_strength', 0.0)),
        int(tick.get('component_area', 0)),
        int(tick.get('length', 0)),
    )


def _refine_tick_x(binary: np.ndarray,
                   approx_x: int,
                   y_start: int,
                   y_end: int,
                   search_radius: int = 6) -> int:
    """Refine a coarse x position by looking for the densest vertical stroke."""
    h, w = binary.shape[:2]
    if h == 0 or w == 0:
        return int(approx_x)

    x1 = max(0, int(approx_x) - search_radius)
    x2 = min(w - 1, int(approx_x) + search_radius)
    if x2 <= x1:
        return int(approx_x)

    y1 = max(0, int(y_start) - 1)
    y2 = min(h - 1, int(y_end) + 1)
    if y2 <= y1:
        return int(approx_x)

    crop = binary[y1:y2 + 1, x1:x2 + 1]
    if crop.size == 0:
        return int(approx_x)

    col_scores = np.sum(crop > 0, axis=0).astype(float)
    if not np.any(col_scores > 0):
        return int(approx_x)

    best = np.max(col_scores)
    best_idx = np.where(col_scores == best)[0]
    if len(best_idx) == 0:
        return int(approx_x)

    refined = x1 + int(round(float(np.mean(best_idx))))
    return max(0, min(w - 1, refined))


def refine_tick_x_subpixel(gray: np.ndarray,
                           approx_x: float,
                           y_start: int,
                           y_end: int,
                           search_radius: int = 7) -> float:
    if gray is None or gray.size == 0:
        return float(approx_x)
    h, w = gray.shape[:2]
    x1 = max(0, int(round(approx_x)) - search_radius)
    x2 = min(w, int(round(approx_x)) + search_radius + 1)
    y1 = max(0, int(y_start))
    y2 = min(h, int(y_end))
    if x2 - x1 < 3 or y2 <= y1:
        return float(approx_x)

    patch = cv2.GaussianBlur(gray[y1:y2, x1:x2], (3, 1), 0).astype(float)
    centers = []
    mid = (patch.shape[1] - 1) / 2.0
    left_idx = np.arange(0, int(np.floor(mid)) + 1)
    right_idx = np.arange(int(np.ceil(mid)), patch.shape[1])
    for row in patch:
        gradient = np.gradient(row)
        left = int(left_idx[np.argmin(gradient[left_idx])])
        right = int(right_idx[np.argmax(gradient[right_idx])])
        width = right - left
        if width < 1 or width > 7 or gradient[left] >= -3 or gradient[right] <= 3:
            continue

        # Fit a local parabola around each gradient extremum.  The original
        # integer extremum remains the anchor; the correction is deliberately
        # blended by half so that subpixel precision improves without letting
        # a noisy edge move the tick by the full continuous estimate.
        def _parabolic_offset(index: int) -> float:
            if index <= 0 or index >= len(gradient) - 1:
                return 0.0
            y_prev = float(gradient[index - 1])
            y_curr = float(gradient[index])
            y_next = float(gradient[index + 1])
            denominator = y_prev - 2.0 * y_curr + y_next
            if abs(denominator) < 1e-9:
                return 0.0
            offset = 0.5 * (y_prev - y_next) / denominator
            if not np.isfinite(offset):
                return 0.0
            return float(np.clip(offset, -0.5, 0.5))

        base_center = x1 + (left + right) / 2.0
        continuous_center = x1 + (
            left + _parabolic_offset(left) +
            right + _parabolic_offset(right)
        ) / 2.0
        centers.append(base_center + 0.5 * (continuous_center - base_center))

    return float(np.median(centers)) if centers else float(approx_x)


def contiguous_segments(indices: np.ndarray, min_len: int = 5) -> List[tuple]:
    """将连续索引归并为线段"""
    if len(indices) < 2:
        return []
    segs, start = [], indices[0]
    for i in range(1, len(indices)):
        if indices[i] != indices[i - 1] + 1:
            if int(indices[i - 1]) - int(start) + 1 >= min_len:
                segs.append((int(start), int(indices[i - 1])))
            start = indices[i]
    if int(indices[-1]) - int(start) + 1 >= min_len:
        segs.append((int(start), int(indices[-1])))
    return segs


def refine_ticks_by_spacing(x_positions: np.ndarray,
                            binary: np.ndarray,
                            spacing_tolerance: float = 0.30,
                            gap_factor: float = 1.55,
                            dup_factor: float = 0.50,
                            snap_ratio: float = 0.28) -> np.ndarray:
    """Refine tick candidates using an explicit, opt-in spacing model.

    This helper is retained for standardization and calibration experiments.
    It is deliberately not called by the production main-scale recognizer:
    inserting a candidate on a theoretical grid can create a tick that is not
    supported strongly enough by the image.  The function therefore returns
    only research candidates and never mutates the input array or binary image.

    The model estimates a robust period from the observed positions, fills a
    large gap only when a nearby foreground column supports the expected
    position, removes near-duplicate candidates by column strength, and snaps
    small position errors to the observed grid.  It does not force a fixed
    number of ticks.
    """
    if x_positions is None or binary is None or binary.ndim != 2:
        return np.asarray([], dtype=float) if x_positions is None else np.asarray(x_positions, dtype=float)

    xs = np.asarray(sorted(set(float(x) for x in x_positions)), dtype=float)
    if xs.size < 3:
        return xs
    height, width = binary.shape[:2]
    if height <= 0 or width <= 0:
        return xs

    diffs = np.diff(xs)
    positive = diffs[diffs > 1.0]
    if positive.size == 0:
        return xs
    raw_period = float(np.median(positive))
    valid = positive[positive <= raw_period * 2.5]
    period = float(np.median(valid)) if valid.size else raw_period
    if period < 2.0:
        return xs

    gap_threshold = period * float(gap_factor)
    duplicate_threshold = period * float(dup_factor)
    search_radius = max(2, int(round(period * 0.28)))

    def column_strength(position: float) -> float:
        column = int(round(position))
        if column < 0 or column >= width:
            return 0.0
        return float(np.sum(binary[:, column] > 0))

    def supported_column(nominal: float):
        lo = max(0, int(round(nominal)) - search_radius)
        hi = min(width - 1, int(round(nominal)) + search_radius)
        if hi < lo:
            return None
        strengths = np.sum(binary[:, lo:hi + 1] > 0, axis=0)
        if strengths.size == 0:
            return None
        best = int(np.argmax(strengths))
        # A weak column is not evidence for a missing tick.
        if float(strengths[best]) < max(3.0, height * 0.10):
            return None
        return float(lo + best)

    filled = []
    for index, current in enumerate(xs[:-1]):
        filled.append(float(current))
        next_x = float(xs[index + 1])
        gap = next_x - float(current)
        missing = int(round(gap / period)) - 1
        if missing <= 0 or gap <= gap_threshold:
            continue
        step = gap / float(missing + 1)
        for missing_index in range(1, missing + 1):
            nominal = float(current) + missing_index * step
            candidate = supported_column(nominal)
            if candidate is not None and abs(candidate - nominal) <= search_radius:
                filled.append(candidate)
    filled.append(float(xs[-1]))

    filled = np.asarray(sorted(set(round(value, 1) for value in filled)), dtype=float)
    if filled.size < 2:
        return filled

    cleaned = [float(filled[0])]
    for candidate in filled[1:]:
        if candidate - cleaned[-1] < duplicate_threshold:
            if column_strength(candidate) > column_strength(cleaned[-1]):
                cleaned[-1] = float(candidate)
        else:
            cleaned.append(float(candidate))
    cleaned = np.asarray(cleaned, dtype=float)

    if cleaned.size >= 3:
        gaps = np.diff(cleaned)
        valid_gaps = gaps[gaps > 1.0]
        grid_period = float(np.median(valid_gaps)) if valid_gaps.size else period
        if grid_period >= 2.0:
            origin = float(cleaned[0])
            snapped = []
            for candidate in cleaned:
                grid = origin + round((candidate - origin) / grid_period) * grid_period
                if abs(candidate - grid) <= grid_period * float(snap_ratio):
                    snapped.append(grid)
                else:
                    snapped.append(candidate)
            cleaned = np.asarray(sorted(set(round(value, 1) for value in snapped)), dtype=float)
    return cleaned


def make_comparison_vis(left_img: np.ndarray, right_img: np.ndarray,
                         left_label: str = "", right_label: str = "",
                         bg_color: tuple = (40, 40, 45)) -> np.ndarray:
    """生成左右对比图"""
    h1, w1 = left_img.shape[:2]
    h2, w2 = right_img.shape[:2]

    # 确保都是 3 通道
    if len(left_img.shape) == 2:
        left_img = cv2.cvtColor(left_img, cv2.COLOR_GRAY2BGR)
    if len(right_img.shape) == 2:
        right_img = cv2.cvtColor(right_img, cv2.COLOR_GRAY2BGR)

    gap = 4
    out_h = max(h1, h2)
    out_w = w1 + w2 + gap
    vis = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    vis[:] = bg_color

    vis[:h1, :w1] = left_img
    vis[:h2, w1 + gap:w1 + gap + w2] = right_img

    if left_label:
        cv2.putText(vis, left_label, (5, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    if right_label:
        cv2.putText(vis, right_label, (w1 + gap + 5, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    return vis


def draw_projection_plot(signal: np.ndarray, peaks: np.ndarray = None,
                          width: int = 800, height: int = 200,
                          title: str = "") -> np.ndarray:
    """绘制投影曲线图（用于调试可视化）"""
    if len(signal) == 0:
        return np.zeros((height, width, 3), dtype=np.uint8)

    # 归一化
    s_max = float(np.max(signal))
    if s_max > 0:
        s_norm = signal / s_max
    else:
        s_norm = signal

    n = len(s_norm)
    plot = np.ones((height, width, 3), dtype=np.uint8) * 30

    # 绘制曲线
    for i in range(min(n - 1, width - 2)):
        x0 = int(i * (width - 40) / n) + 20
        x1 = int((i + 1) * (width - 40) / n) + 20
        y0 = height - 20 - int(s_norm[i] * (height - 50))
        y1 = height - 20 - int(s_norm[i + 1] * (height - 50))
        cv2.line(plot, (x0, y0), (x1, y1), (100, 200, 255), 1)

    # 绘制峰值
    if peaks is not None and len(peaks) > 0:
        for p in peaks:
            pi = int(p)
            if 0 <= pi < n:
                px = int(pi * (width - 40) / n) + 20
                py = height - 20 - int(s_norm[pi] * (height - 50))
                cv2.circle(plot, (px, py), 4, (0, 255, 100), -1)

    # 标题
    if title:
        cv2.putText(plot, title, (10, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    return plot


def draw_legend_below(image: np.ndarray, items: list, line_h: int = 18) -> np.ndarray:
    """
    在图像下方拼接一个图例面板（不覆盖原图）。
    """
    h, w = image.shape[:2]
    panel_h = len(items) * line_h + 16
    panel = np.zeros((panel_h, w, 3), dtype=np.uint8)
    panel[:] = (30, 30, 35)
    for i, (label, color, style) in enumerate(items):
        cy = 10 + i * line_h
        if style == 'line':
            cv2.line(panel, (8, cy), (32, cy), color, 2)
        elif style == 'rect':
            cv2.rectangle(panel, (8, cy - 6), (32, cy + 6), color, 1)
        elif style == 'circle':
            cv2.circle(panel, (20, cy), 5, color, -1)
        cv2.putText(panel, label, (38, cy + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)
    return np.vstack([image, panel])
