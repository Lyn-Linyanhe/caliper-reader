"""
游标卡尺识别流水线主控。
"""

import time

import cv2
import numpy as np

from .config import config
from .main_scale import recognize_main_scale
from .merger import merge_readings
from .preprocess import preprocess
from .region_split import build_split_recovery_result, split_scales
from .result import CaliperResult
from .roi_extract import locate_roi_lowres, orient_caliper
from .utils import draw_legend_below
from .vernier_scale import recognize_vernier_scale


class CaliperPipeline:
    """游标卡尺识别流水线。"""

    def __init__(self, fast_mode: bool = False):
        self.debug_images = {}
        self.step_results = {}
        self.timings = {}
        self._pipeline_t0 = 0.0
        self.fast_mode = fast_mode

        self.preprocess_params = {
            'clip_limit': config.preprocess.clahe_clip_limit,
            'bilateral_d': config.preprocess.bilateral_d,
            'bilateral_sigma': config.preprocess.bilateral_sigma,
            'gamma': config.preprocess.gamma,
            'median_ksize': config.preprocess.median_ksize,
        }

    def _emit_progress(self, progress_callback, step_key: str, status: str):
        if progress_callback is None:
            return
        image = self.debug_images.get(step_key)
        if image is not None:
            progress_callback(step_key, image, status)

    def _start_timing(self):
        return time.perf_counter()

    def _record_timing(self, key: str, label: str, start_time: float):
        self.timings[key] = {
            'label': label,
            'ms': (time.perf_counter() - start_time) * 1000.0,
        }
        self.step_results['timings'] = self.timings

    def run(self, img: np.ndarray, progress_callback=None) -> CaliperResult:
        self.debug_images = {}
        self.step_results = {}
        self.timings = {}
        self._pipeline_t0 = time.perf_counter()
        original = img.copy()

        t0 = self._start_timing()
        roi_result = locate_roi_lowres(img)
        self._record_timing('roi_lowres', 'ROI 定位', t0)
        roi_timing_labels = {
            'roi_debug_vis': 'ROI: 定位可视化',
            'gray_full': 'ROI: 原图转灰度',
            'resize_gray_linear': 'ROI: 灰度缩放',
            'enhance_gamma_clahe': 'ROI: gamma/CLAHE',
            'adaptive_threshold': 'ROI: 自适应二值化',
            'horizontal_projection': 'ROI: 水平投影',
            'vertical_projection': 'ROI: 垂直投影',
            'refine_vernier_block': 'ROI: 游标本体精修',
            'refine_make_edge_map': 'ROI: 生成边缘图',
            'refine_select_y_edge_window': 'ROI: 选择 y 边缘窗口',
            'refine_find_y_edges': 'ROI: 查找上下边缘',
            'refine_find_right_edge': 'ROI: 查找右边缘',
            'refine_reading_window': 'ROI: 读数窗口精修',
            'map_and_crop': 'ROI: 映射裁剪',
        }
        for sub_key, ms in roi_result.get('roi_timings', {}).items():
            self.timings[f'roi_{sub_key}'] = {
                'label': roi_timing_labels.get(sub_key, f'ROI: {sub_key}'),
                'ms': float(ms),
            }
        self.step_results['timings'] = self.timings
        initial = self._run_from_roi_result(original, roi_result, progress_callback)
        vernier = self.step_results.get('vernier', {})
        candidates = roi_result.get('roi_recovery_candidates', [])
        # A partial vernier run may carry ``error=None`` even though it is too
        # short to establish the scale range.  Use the same evidence gate as
        # recovery acceptance so short runs do not bypass the ROI fallback.
        if self._vernier_result_is_reliable(vernier) or not candidates:
            return initial

        initial_state = (self.debug_images, self.step_results, self.timings)
        attempts = []
        for candidate in candidates:
            self.debug_images = {}
            self.step_results = {}
            self.timings = {}
            self._pipeline_t0 = time.perf_counter()
            recovered_roi = self._roi_result_for_recovery_candidate(
                original, roi_result, candidate
            )
            recovered = self._run_from_roi_result(
                original, recovered_roi, progress_callback
            )
            recovered_vernier = self.step_results.get('vernier', {})
            attempts.append({
                'name': candidate['name'],
                'added_area': candidate['added_area'],
                'vernier_error': recovered_vernier.get('error'),
                'vernier_tick_count': len(recovered_vernier.get('vernier_ticks', [])),
                'zero_x': recovered_vernier.get('zero_x'),
            })
            if self._vernier_result_is_reliable(recovered_vernier):
                recovered.extra_info['roi_recovery'] = {
                    'triggered': True,
                    'selected_candidate': candidate['name'],
                    'attempts': attempts,
                }
                self.step_results['roi']['roi_recovery'] = recovered.extra_info['roi_recovery']
                return recovered

        self.debug_images, self.step_results, self.timings = initial_state
        recovery_info = {
            'triggered': True,
            'selected_candidate': None,
            'attempts': attempts,
        }
        initial.extra_info['roi_recovery'] = recovery_info
        if isinstance(self.step_results.get('roi'), dict):
            self.step_results['roi']['roi_recovery'] = recovery_info
        return initial

    def _run_from_roi_result(self, original: np.ndarray,
                             roi_result: dict,
                             progress_callback=None) -> CaliperResult:
        if roi_result['roi_color'] is None:
            self._record_timing('total', '总耗时', self._pipeline_t0)
            return self._fail(original, 'ROI 提取失败')

        roi_source = str(roi_result.get('roi_source') or '')
        roi_source_label = {
            'lowres_projection': '低分辨率投影框',
            'lowres_body': '低分辨率主体框',
            'lowres_compact': '低分辨率紧凑框',
        }.get(roi_source)
        if roi_source.startswith('lowres_compact_recovery_'):
            roi_source_label = '低分辨率紧凑框局部扩边恢复'
        if roi_source_label is None:
            roi_source_label = 'ROI 定位'
        if roi_result.get('lowres_debug') is not None:
            self.debug_images['1_ROI定位'] = roi_result.get('lowres_debug')
        self._emit_progress(progress_callback, '1_ROI定位', f'ROI 定位完成：{roi_source_label}')

        t0 = self._start_timing()
        pp = preprocess(roi_result['roi_color'], make_debug=not self.fast_mode, **self.preprocess_params)
        self._record_timing('preprocess_roi', 'ROI 内正式预处理', t0)
        preprocess_timing_labels = {
            'gray': '预处理: 转灰度',
            'gamma': '预处理: gamma',
            'bilateral': '预处理: 双边滤波',
            'median': '预处理: 中值滤波',
            'clahe': '预处理: CLAHE',
            'unsharp': '预处理: 锐化',
            'adaptive_threshold': '预处理: 自适应二值化',
            'morph_open': '预处理: 形态学开运算',
            'cc_filter': '预处理: 连通域过滤',
        }
        for sub_key, ms in pp.get('step_timings', {}).items():
            self.timings[f'preprocess_{sub_key}'] = {
                'label': preprocess_timing_labels.get(sub_key, f'预处理: {sub_key}'),
                'ms': float(ms),
            }
        self.step_results['timings'] = self.timings
        roi_result['roi_color'] = pp['color']
        roi_result['roi_gray'] = pp['enhanced']
        roi_result['roi_binary'] = pp['binary_adaptive']
        if pp.get('debug_vis') is not None:
            self.debug_images['0_预处理'] = pp['debug_vis']
        self.step_results['preprocess'] = pp
        self._emit_progress(progress_callback, '0_预处理', '预处理完成')
        self.step_results['roi'] = roi_result

        t0 = self._start_timing()
        orient_result = orient_caliper(
            roi_result['roi_color'],
            roi_result['roi_gray'],
            roi_result['roi_binary'],
            make_debug=not self.fast_mode,
        )
        self._record_timing('orientation', '方向校正', t0)
        if orient_result.get('orient_vis') is not None:
            self.debug_images['1b_方向校正'] = orient_result['orient_vis']
        self.step_results['orient'] = orient_result
        self._emit_progress(progress_callback, '1b_方向校正', '方向校正完成')
        return self._run_remainder(original, orient_result, progress_callback)

    @staticmethod
    def _roi_result_for_recovery_candidate(original: np.ndarray,
                                           base_roi: dict,
                                           candidate: dict) -> dict:
        x1, y1, x2, y2 = candidate['roi_box_original']
        recovery = dict(base_roi)
        recovery['roi_color'] = original[y1:y2, x1:x2].copy()
        recovery['x_offset'] = x1
        recovery['y_offset'] = y1
        recovery['roi_box_original'] = (x1, y1, x2, y2)
        recovery['roi_source'] = 'lowres_compact_recovery_' + candidate['name']
        recovery['lowres_debug'] = None
        recovery['roi_selection'] = {
            **base_roi.get('roi_selection', {}),
            'recovery_candidate': candidate,
        }
        recovery['roi_recovery_candidates'] = []
        return recovery

    @staticmethod
    def _vernier_result_is_reliable(vernier_result: dict) -> bool:
        # A short, partial run can be internally periodic but cannot establish
        # the full vernier range. This gates recovery acceptance only; it does
        # not create, complete, or require an exact number of ticks.
        min_observed = max(
            config.vernier_scale.min_tick_count,
            config.vernier_scale.recovery_min_observed_tick_count,
        )
        return (
            not vernier_result.get('error')
            and len(vernier_result.get('vernier_ticks', [])) >= min_observed
            and float(vernier_result.get('zero_x', 0.0)) > 0.0
        )

    @staticmethod
    def _split_recovery_is_reliable(main_result: dict,
                                    vernier_result: dict) -> tuple[bool, str]:
        """Gate a later-band split with measured geometry and valley evidence."""
        if vernier_result.get('error'):
            return False, str(vernier_result.get('error'))
        main_ticks = main_result.get('main_ticks') or []
        vernier_ticks = vernier_result.get('vernier_ticks') or []
        detection = vernier_result.get('vernier_band_detection') or {}
        if len(main_ticks) < 10 or len(vernier_ticks) < 10:
            return False, 'insufficient_observed_tick_run'

        main_gap = float(main_result.get('main_gap', 0.0) or 0.0)
        expected_gap = float(detection.get('expected_gap', 0.0) or 0.0)
        if main_gap <= 3.0 or expected_gap <= 3.0:
            return False, 'missing_period_measurement'
        if not 0.70 <= expected_gap / main_gap <= 1.30:
            return False, 'main_vernier_period_mismatch'

        selection_score = float(detection.get('selection_score', 0.0) or 0.0)
        period_clarity = float(detection.get('period_clarity', 0.0) or 0.0)
        tick_structure = float(detection.get('tick_structure', 0.0) or 0.0)
        if selection_score < config.vernier_scale.valley_min_total_score:
            return False, 'weak_valley_pair_score'
        if period_clarity < config.vernier_scale.valley_min_period_clarity:
            return False, 'weak_period_clarity'
        if tick_structure < config.vernier_scale.valley_min_component_structure:
            return False, 'weak_tick_structure'

        roi = detection.get('vernier_tick_roi')
        if not roi or len(roi) != 2:
            return False, 'missing_vernier_tick_roi'
        boundary_x = float(detection.get('x1', 0)) + float(roi[0])
        zero_x = float(vernier_result.get('zero_x', 0.0) or 0.0)
        if abs(zero_x - boundary_x) > expected_gap * 0.75:
            return False, 'zero_not_anchored_to_left_valley'

        observed_xs = sorted(float(t.get('x_precise', t.get('x', 0.0)))
                             for t in vernier_ticks)
        if len(observed_xs) < 2:
            return False, 'missing_vernier_span'
        observed_span = observed_xs[-1] - observed_xs[0]
        if observed_span < expected_gap * 10.0:
            return False, 'vernier_run_too_short'
        main_xs = sorted(float(t.get('x_precise', t.get('x', 0.0)))
                         for t in main_ticks)
        if len(main_xs) < 2 or main_xs[-1] - main_xs[0] < main_gap * 10.0:
            return False, 'main_run_too_short'
        return True, 'periodic_valley_bounded_observed_run'

    def _try_split_starvation_recovery(self,
                                       rotated_gray: np.ndarray,
                                       rotated_binary: np.ndarray,
                                       rotated_color: np.ndarray,
                                       split_result: dict,
                                       main_gap_prior: float,
                                       make_debug: bool):
        """Try measured later bands only after the current vernier is empty."""
        candidates = split_result.get('split_recovery_candidates') or []
        attempts = []
        if not candidates:
            return None, None, None

        for candidate in candidates:
            candidate_split = build_split_recovery_result(
                rotated_gray,
                rotated_binary,
                rotated_color,
                split_result,
                candidate,
                make_debug=make_debug,
            )
            region_main = candidate_split['region_main']
            region_vernier = candidate_split['region_vernier']
            main_color = rotated_color[:candidate_split['split_y'], :]
            main_result = recognize_main_scale(
                region_main, main_color, make_debug=make_debug
            )
            vernier_color = rotated_color[candidate_split['split_y']:, :]
            vernier_result = recognize_vernier_scale(
                region_vernier,
                main_result.get('main_gap', main_gap_prior),
                vernier_color,
                main_result.get('main_ticks', []),
                make_debug=make_debug,
            )
            accepted, reason = self._split_recovery_is_reliable(
                main_result, vernier_result
            )
            detection = vernier_result.get('vernier_band_detection') or {}
            attempts.append({
                'name': candidate.get('name'),
                'split_y': candidate.get('split_y'),
                'offset': candidate.get('offset'),
                'main_tick_count': len(main_result.get('main_ticks', [])),
                'main_gap': main_result.get('main_gap'),
                'vernier_tick_count': len(vernier_result.get('vernier_ticks', [])),
                'zero_x': vernier_result.get('zero_x'),
                'selection_score': detection.get('selection_score'),
                'period_clarity': detection.get('period_clarity'),
                'accepted': bool(accepted),
                'reason': reason,
            })
            if not accepted:
                continue

            recovery = {
                'triggered': True,
                'reason': 'initial_vernier_starvation',
                'original_split_y': int(split_result['split_y']),
                'selected_candidate': candidate.get('name'),
                'attempts': attempts,
            }
            candidate_split['split_recovery'] = recovery
            candidate_split['tick_bands']['split_recovery'] = recovery
            return candidate_split, main_result, vernier_result

        return {
            'triggered': True,
            'reason': 'initial_vernier_starvation',
            'original_split_y': int(split_result['split_y']),
            'selected_candidate': None,
            'attempts': attempts,
        }, None, None

    def _run_remainder(self, original: np.ndarray,
                       orient_result: dict,
                       progress_callback=None) -> CaliperResult:
        rotated_color = orient_result['rotated_color']
        rotated_gray = orient_result['rotated_gray']
        rotated_binary = orient_result['rotated_binary']

        t0 = self._start_timing()
        split_result = split_scales(rotated_gray, rotated_binary, rotated_color, make_debug=not self.fast_mode)
        self._record_timing('region_split', '主尺/游标区域分离', t0)
        if split_result.get('split_vis') is not None:
            self.debug_images['2_区域分离'] = split_result['split_vis']
        self.step_results['split'] = split_result
        self._emit_progress(progress_callback, '2_区域分离', '区域分离完成')
        region_main = split_result['region_main']
        region_vernier = split_result['region_vernier']
        split_y = split_result['split_y']

        main_color = rotated_color[:split_y, :]
        t0 = self._start_timing()
        main_result = recognize_main_scale(region_main, main_color, make_debug=not self.fast_mode)
        self._record_timing('main_scale', '主尺刻线识别', t0)
        if main_result.get('vis_ticks') is not None:
            self.debug_images['3a_主尺刻度线'] = main_result['vis_ticks']
        self.step_results['main'] = main_result
        self._emit_progress(progress_callback, '3a_主尺刻度线', '主尺刻线识别完成')

        vernier_color = rotated_color[split_y:, :]
        t0 = self._start_timing()
        vernier_result = recognize_vernier_scale(
            region_vernier,
            main_result['main_gap'],
            vernier_color,
            main_result['main_ticks'],
            make_debug=not self.fast_mode,
        )
        self._record_timing('vernier_scale', '游标刻线识别与对齐', t0)

        split_recovery = None
        recovered_main = None
        recovered_vernier = None
        if vernier_result.get('error') == 'no_reliable_valley_bounded_tick_range':
            split_recovery, recovered_main, recovered_vernier = (
                self._try_split_starvation_recovery(
                    rotated_gray,
                    rotated_binary,
                    rotated_color,
                    split_result,
                    main_result.get('main_gap', 0.0),
                    make_debug=not self.fast_mode,
                )
            )
            if recovered_main is not None and recovered_vernier is not None:
                split_result = split_recovery
                main_result = recovered_main
                vernier_result = recovered_vernier
                region_main = split_result['region_main']
                region_vernier = split_result['region_vernier']
                split_y = split_result['split_y']
                main_color = rotated_color[:split_y, :]
                vernier_color = rotated_color[split_y:, :]
                self.step_results['split'] = split_result
                self.step_results['main'] = main_result
                if split_result.get('split_vis') is not None:
                    self.debug_images['2_区域分离'] = split_result['split_vis']
                if main_result.get('vis_ticks') is not None:
                    self.debug_images['3a_主尺刻度线'] = main_result['vis_ticks']

        if split_recovery is not None and recovered_main is None:
            split_result['split_recovery'] = split_recovery
            split_result['tick_bands']['split_recovery'] = split_recovery

        if not self.fast_mode:
            if vernier_result.get('vis_ticks') is not None:
                self.debug_images['4b_游标刻度线'] = vernier_result['vis_ticks']
                self._emit_progress(progress_callback, '4b_游标刻度线', '游标刻线识别完成')

        if not self.fast_mode:
            t0 = self._start_timing()
            vernier_result['vis_alignment'] = _regenerate_alignment_vis(
                vernier_result,
                vernier_color,
                rotated_color,
                split_y,
                main_result['main_ticks'],
                main_result['main_gap'],
            )
            self._record_timing('alignment_vis', '游标对齐图', t0)
            self.debug_images['4c_游标对齐'] = vernier_result['vis_alignment']
            self._emit_progress(progress_callback, '4c_游标对齐', '游标对齐完成')
        self.step_results['vernier'] = vernier_result

        if not self.fast_mode:
            t0 = self._start_timing()
            _add_legends(main_result, vernier_result)
            self._record_timing('legend_vis', '图例生成', t0)

        t0 = self._start_timing()
        final = merge_readings(
            main_result,
            vernier_result,
            rotated_color,
            region_main,
            region_vernier,
            split_y,
            make_debug=not self.fast_mode,
            simple_annotation=self.fast_mode,
        )
        roi_info = self.step_results.get('roi', {})
        final.extra_info.update({
            'roi_source': roi_info.get('roi_source', 'lowres_projection'),
            'roi_box_original': roi_info.get('roi_box_original'),
            'fast_mode': bool(self.fast_mode),
            'speed_strategies': {
                'reuse_region_binary': True,
                'simple_final_annotation': bool(self.fast_mode),
                'seam_near_main_refine': True,
                'seam_near_vernier_refine': True,
            },
        })
        self._record_timing('merge_readings', '读数合并/OCR/最终标注', t0)

        if not self.fast_mode:
            t0 = self._start_timing()
            ocr_debug_vis = _make_ocr_debug_vis(
                rotated_color,
                split_y,
                region_main,
                main_result,
                vernier_result,
                final,
            )
            self._record_timing('ocr_debug_vis', 'OCR 调试图', t0)
            if ocr_debug_vis is not None:
                self.debug_images['3b_主尺数字OCR'] = ocr_debug_vis
                self._emit_progress(progress_callback, '3b_主尺数字OCR', 'OCR 调试图完成')

        final.debug_images = self.debug_images
        self.debug_images['5_最终标注'] = final.image_annotated
        self._emit_progress(progress_callback, '5_最终标注', '最终标注完成')

        deriv_vis = final.extra_info.get('derivation_vis')
        if deriv_vis is not None:
            self.debug_images['5b_读数推导'] = deriv_vis
            self._emit_progress(progress_callback, '5b_读数推导', '读数推导完成')

        self._record_timing('total', '总耗时', self._pipeline_t0)
        final.extra_info['timings'] = self.timings.copy()
        self.step_results['timings'] = self.timings
        return final

    def _fail(self, img: np.ndarray, reason: str) -> CaliperResult:
        result = CaliperResult(
            main_scale=0.0,
            vernier_scale=0.0,
            total=0.0,
            precision=0.02,
            confidence=0.0,
            image_annotated=img,
            debug_images={'error': img},
            extra_info={'error': reason, 'timings': self.timings.copy()},
        )
        return result


def _regenerate_alignment_vis(vernier_result: dict,
                              vernier_color: np.ndarray,
                              rotated_color: np.ndarray,
                              split_y: int,
                              main_ticks: list,
                              main_gap: float) -> np.ndarray:
    from .vernier_scale import _draw_alignment
    return _draw_alignment(
        {'y_offset': split_y},
        vernier_color,
        vernier_result['vernier_ticks'],
        main_gap,
        vernier_result['zero_x'],
        vernier_result.get('aligned_tick'),
        vernier_result.get('alignment_confidence', 0.0),
        alignment_ambiguity=vernier_result.get('alignment_ambiguity'),
        full_color=rotated_color,
        split_y=split_y,
        main_ticks=main_ticks,
    )


def _add_legends(main_result: dict, vernier_result: dict):
    vis_vt = vernier_result.get('vis_ticks')
    if vis_vt is not None and vis_vt.size > 0:
        items = [
            ("orange line = vernier tick", (200, 160, 40), 'line'),
            ("blue line = zero (0th tick)", (50, 150, 255), 'line'),
        ]
        vernier_result['vis_ticks'] = draw_legend_below(vis_vt, items)

    vis_va = vernier_result.get('vis_alignment')
    if vis_va is not None and vis_va.size > 0:
        items = [
            ("gray line = main scale tick", (80, 80, 90), 'line'),
            ("orange line = vernier tick", (200, 160, 40), 'line'),
            ("blue line = zero (crossing full ROI)", (50, 150, 255), 'line'),
            ("thick green = best alignment", (0, 255, 80), 'line'),
            ("yellow dash = main/vernier split", (255, 255, 100), 'line'),
        ]
        vernier_result['vis_alignment'] = draw_legend_below(vis_va, items)


def _make_ocr_debug_vis(rotated_color: np.ndarray,
                        split_y: int,
                        region_main: dict,
                        main_result: dict,
                        vernier_result: dict,
                        final_result) -> np.ndarray:
    from .main_scale import find_nearest_cm_digit_region

    main_color = rotated_color[:split_y, :]
    main_binary = region_main.get('binary')
    main_ticks = main_result.get('main_ticks', [])
    main_gap = main_result.get('main_gap', 0)
    zero_x = vernier_result.get('zero_x', 0)

    H_main, W_main = main_color.shape[:2]
    if H_main < 10 or W_main < 10:
        return None

    extra = final_result.extra_info if final_result else {}
    main_deriv = extra.get('main_derivation', {}) if hasattr(final_result, 'extra_info') else {}
    vertical_expand_gaps = (
        float(main_deriv.get('ocr_vertical_expand_gaps', 0.0))
        if isinstance(main_deriv, dict) else 0.0
    )
    binary_crop, x_off, y_off = find_nearest_cm_digit_region(
        main_ticks,
        main_gap,
        zero_x,
        main_binary,
        vertical_expand_gaps=vertical_expand_gaps,
    )
    if binary_crop is None or binary_crop.size == 0:
        fallback = main_color.copy()
        cv2.line(fallback, (int(zero_x), 0), (int(zero_x), H_main - 1), (0, 255, 255), 2)
        cv2.putText(
            fallback,
            "NO BACKUP REGION",
            (10, H_main - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (100, 100, 255),
            1,
        )
        return fallback

    ch, cw = binary_crop.shape
    strategy = main_deriv.get('strategy', '?') if isinstance(main_deriv, dict) else '?'
    eng = main_deriv.get('ocr_engine', '?') if isinstance(main_deriv, dict) else '?'
    ocr_candidates = main_deriv.get('ocr_candidates', []) if isinstance(main_deriv, dict) else []
    selected_candidates = [c for c in ocr_candidates if c.get('selected')]
    sel_bbox = selected_candidates[0].get('bbox') if selected_candidates else None
    if selected_candidates:
        selected = selected_candidates[0]
        ocr_line = "OCR => '{}' ref_x={}".format(
            selected.get('text'),
            int(round(float(selected.get('ref_tick_x', 0)))),
        )
        ocr_color = (0, 255, 100)
    elif ocr_candidates:
        ocr_line = "OCR candidates found, none selected"
        ocr_color = (0, 160, 255)
    else:
        ocr_line = "OCR => no candidate"
        ocr_color = (100, 100, 255)
    if isinstance(main_deriv, dict) and main_deriv.get('ocr_expanded_retry_used'):
        ocr_line += " [expanded retry]"

    panel_a = main_color.copy()
    for t in main_ticks:
        cv2.line(
            panel_a,
            (t['x'], max(0, t.get('y_start', 0))),
            (t['x'], min(H_main - 1, t.get('y_end', H_main))),
            (0, 160, 60),
            1,
        )
    cv2.line(panel_a, (int(zero_x), 0), (int(zero_x), H_main - 1), (0, 255, 255), 2)
    cv2.putText(
        panel_a,
        f"ZERO x={int(zero_x)}",
        (int(zero_x) + 4, 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 255, 255),
        1,
    )
    cv2.rectangle(panel_a, (x_off, y_off), (x_off + cw, y_off + ch), (0, 0, 255), 2)
    cv2.putText(
        panel_a,
        f"backup ({cw}x{ch}) expand={vertical_expand_gaps:.1f}g",
        (x_off + 3, y_off + 14),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        (0, 0, 255),
        1,
    )

    y_top_tick = max(t.get('y_start', 0) for t in main_ticks) if main_ticks else 0
    for x in range(0, W_main, 10):
        cv2.line(panel_a, (x, y_top_tick), (min(W_main, x + 5), y_top_tick), (255, 200, 50), 1)
    cv2.putText(
        panel_a,
        f"y_top_tick={y_top_tick}",
        (4, max(12, y_top_tick - 6)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        (255, 200, 50),
        1,
    )

    blow = cv2.resize(binary_crop, (cw * 4, ch * 4), interpolation=cv2.INTER_NEAREST)
    panel_b = cv2.cvtColor(blow, cv2.COLOR_GRAY2BGR)

    panel_c = main_color[y_off:y_off + ch, x_off:x_off + cw].copy()
    if len(panel_c.shape) == 2:
        panel_c = cv2.cvtColor(panel_c, cv2.COLOR_GRAY2BGR)

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(binary_crop, connectivity=8)
    for j in range(1, num_labels):
        x = int(stats[j, cv2.CC_STAT_LEFT])
        y = int(stats[j, cv2.CC_STAT_TOP])
        w_cc = int(stats[j, cv2.CC_STAT_WIDTH])
        h_cc = int(stats[j, cv2.CC_STAT_HEIGHT])
        area = int(stats[j, cv2.CC_STAT_AREA])
        cv2.rectangle(panel_c, (x, y), (x + w_cc, y + h_cc), (255, 140, 40), 1)
        if area > 10:
            cv2.putText(panel_c, f"{area}", (x, max(y - 1, 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.22, (255, 140, 40), 1)

    if sel_bbox is not None:
        bx1 = sel_bbox[0] - x_off
        by1 = sel_bbox[1] - y_off
        bx2 = sel_bbox[2] - x_off
        by2 = sel_bbox[3] - y_off
        cv2.rectangle(panel_c, (bx1, by1), (bx2, by2), (0, 255, 100), 3)

    gap = 3
    panel_w = max(W_main, cw * 4)
    if panel_b.shape[1] < panel_w:
        pb = np.zeros((panel_b.shape[0], panel_w, 3), dtype=np.uint8)
        pb[:] = (20, 20, 25)
        pb[:, :panel_b.shape[1]] = panel_b
    else:
        pb = panel_b

    if panel_c.shape[1] < panel_w:
        pc = np.zeros((panel_c.shape[0], panel_w, 3), dtype=np.uint8)
        pc[:] = (20, 20, 25)
        pc[:, :panel_c.shape[1]] = panel_c
    else:
        pc = panel_c

    label_h = 20
    total_h = (H_main + gap) + (label_h + pb.shape[0] + gap) + (label_h + pc.shape[0] + gap) + 36
    combined = np.zeros((total_h, panel_w, 3), dtype=np.uint8)
    combined[:] = (22, 22, 28)

    y = 0
    combined[y:y + H_main, :W_main] = panel_a
    cv2.putText(combined, "A: Main Scale + Backup Region (red) + Zero (yellow)",
                (4, y + H_main - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (140, 140, 140), 1)
    y += H_main + gap
    cv2.putText(combined, f"B: Backup Region ({cw}x{ch}) x4",
                (4, y + label_h - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 180, 180), 1)
    y += label_h
    combined[y:y + pb.shape[0], :] = pb
    y += pb.shape[0] + gap
    cv2.putText(combined, f"C: CC Analysis ({num_labels - 1} CCs) | {ocr_line}",
                (4, y + label_h - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, ocr_color, 1)
    y += label_h
    combined[y:y + pc.shape[0], :] = pc

    legend_items = [
        ("red rect = backup region", (0, 0, 255), 'rect'),
        ("yellow line = zero (vernier x=0)", (0, 255, 255), 'line'),
        ("orange box = all CCs", (255, 140, 40), 'rect'),
        ("green thick = selected CC", (0, 255, 100), 'rect'),
    ]
    combined = draw_legend_below(combined, legend_items)
    cv2.putText(combined, f"STEP 3b: Main Scale OCR [{eng}]  strategy={strategy}",
                (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    return combined


def read_caliper(image_path: str) -> CaliperResult:
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"无法读取图像: {image_path}")
    pipeline = CaliperPipeline()
    return pipeline.run(img)


def read_caliper_from_array(img: np.ndarray) -> CaliperResult:
    pipeline = CaliperPipeline()
    return pipeline.run(img)
