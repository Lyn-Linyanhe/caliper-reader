"""
游标卡尺识别 — 集中调参配置文件
==================================

使用方法：
    from caliper.config import config

    # 查看/修改参数
    config.preprocess.gamma = 0.85         # 压暗中间调，抑制高光
    config.roi.x_pad_ratio = 0.20         # 增加 ROI 横向安全边界
    config.main_scale.min_tick_count = 5   # 放宽最小刻线数

    # 重置为默认值
    config.reset()

    # 打印所有参数（调试用）
    config.summary()
"""


# ═════════════════════════════════════════════════════════════
#  0. 图像预处理 — preprocess.py
# ═════════════════════════════════════════════════════════════

class PreprocessConfig:
    """预处理参数：灰度 → gamma 校正 → 轻量去噪 → CLAHE → 锐化 → 二值化"""

    # ── 幂律变换 (gamma 校正) ──
    #     公式: s = 255 * (r/255)^(1/gamma)
    #     1.0 = 不改变；<1 压暗中间调；>1 提亮中间调
    #     典型范围: 0.6 ~ 1.5
    gamma: float = 1.5

    bilateral_d: int = 5
    bilateral_sigma: float = 25.0

    median_ksize: int = 0

    # ── CLAHE 对比度增强（局部自适应直方图均衡）──
    #     clip_limit: 对比度限制，越大对比度越强（也放大噪声）
    #     tile_grid: 分块大小，(8,8) 是常规默认
    clahe_clip_limit: float = 1.0
    clahe_tile_w: int = 8
    clahe_tile_h: int = 8

    # ── 非锐化掩膜锐化 ──
    #     v6.5: 公式已修正为标准 unsharp mask：sharp = orig + amount × (orig - blur)
    #     amount=0   → 不变（跳过锐化）
    #     amount=0.5 → 轻微锐化（默认，平衡刻度可见性 vs 噪声放大）
    #     amount=1.5 → 强锐化（可能引入噪声，下游过检）
    unsharp_amount: float = 0.25
    unsharp_blur_sigma: float = 1.5

    # ── 自适应阈值二值化 ──
    #     block_size: 局部邻域大小（奇数），越大对光照鲁棒但细节损失
    #     C: 从均值中减去的常数，越大二值化越保守（白像素越少）
    adaptive_block_size: int = 91
    adaptive_C: int = 17
    adaptive_binary_scale: float = 0.8

    # ── 后处理：形态学开运算（二值化后去噪）──
    #     先腐蚀再膨胀，消除孤立小噪点
    morph_open_enabled: bool = False
    morph_open_kernel_size: int = 3   # 核尺寸（椭圆核）
    morph_open_iterations: int = 1    # 迭代次数

    # ── 后处理：连通域过滤（二值化后去噪）──
    #     剔除面积小于阈值的孤立连通域（白连通域=噪声斑块）
    #     v6.5: 从 15 增加到 50，更激进地过滤背景墙椒盐噪声
    #     (主尺刻度线连通域面积一般 > 200，安全裕量充足)
    cc_filter_enabled: bool = False
    cc_min_area: int = 50             # 最小面积（像素）


# ═════════════════════════════════════════════════════════════
#  1. ROI 提取 — roi_extract.py
# ═════════════════════════════════════════════════════════════

class ROIExtractConfig:
    """ROI 参数：低清投影初框、主体精修和紧凑结构验证。"""

    # ── COM 质心法：以投影质心为轴，扩展的宽度/高度比例 ──
    #     预期读数区约占图宽 30%、图高 22%
    x_center_span_ratio: float = 0.30
    y_center_span_ratio: float = 0.22

    # ── 边界余量 ──
    #     在检测到的边界外扩的比例
    y_pad_ratio: float = 0.10
    x_pad_ratio: float = 0.15

    # ── ROI 尺寸下限（像素）──
    min_roi_height: int = 15
    min_roi_width: int = 30

    # ── 轮廓研究/兼容字段（当前低清 ROI 主路径未读取）──
    #     保留用于未来 ROI 候选研究和配置兼容，不是当前 ROI 调参入口。
    contour_area_ratio_min: float = 0.05
    contour_area_ratio_max: float = 0.60
    #     长宽比（宽/高）
    contour_aspect_min: float = 6.0
    contour_aspect_max: float = 30.0
    #     矩形度（轮廓面积 / 外接矩形面积）
    contour_rectangularity_min: float = 0.65
    #     最低总分（低于则放弃轮廓法）
    contour_min_score: float = 0.15

    # ── 评分权重 ──
    score_weight_area: float = 0.25
    score_weight_aspect: float = 0.40
    score_weight_rect: float = 0.25
    score_weight_position: float = 0.10

    # ── 形态学闭运算核宽（占图宽比例）──
    morph_kernel_ratio: float = 0.025  # 水平核宽 = 图宽 * ratio


# ═════════════════════════════════════════════════════════════
#  1b. 方向矫正 — roi_extract.py / orient_caliper()
# ═════════════════════════════════════════════════════════════

class OrientConfig:
    angle_detection_scale: float = 0.75

    """方向配置；当前生效项只有 angle_detection_scale。

    实际方向估计使用接缝附近 Scharr-y 响应点和 RANSAC 直线拟合。下面
    的 Canny/Hough/角度阈值字段保留作历史实验和配置兼容，当前函数不读取它们；
    后续若研究局部方向校正，可在独立开关下重新启用，不能直接替换正式路径。
    """

    # ── Canny 边缘检测 ──
    canny_low: int = 40
    canny_high: int = 150

    # ── HoughLinesP 概率霍夫 ──
    hough_threshold: int = 50   # 累加器阈值（越高要求越严格）
    hough_min_length: int = 25  # 线段最小长度（像素）
    hough_max_gap: int = 6      # 同一直线的最大间断

    # ── 角度过滤 ──
    #     只保留角度在此范围内的线（刻度线近似垂直）
    angle_min: float = 55.0     # 与水平方向夹角下限
    angle_max: float = 125.0    # 与水平方向夹角上限

    # ── 角度合并 ──
    #     缩尾比例（去掉最极端的两端）
    trim_ratio: float = 0.1     # 两端各去掉 10%

    # ── 旋转阈值 ──
    #     小于此角度的不做旋转（避免微小抖动 + HoughLinesP 随机噪声）
    rotate_min_angle: float = 0.3
    #     大于此角度认为是检测错误
    rotate_max_angle: float = 80.0


# ═════════════════════════════════════════════════════════════
#  2. 区域分离 — region_split.py
# ═════════════════════════════════════════════════════════════

class RegionSplitConfig:
    """区域分离参数：竖直组件端点 → 投影谷底 → 物理比例回退。"""

    # ── 历史兼容字段：当前 split_scales 不读取 ──
    # 当前区域分离直接复用 Pipeline 传入的二值图，并使用下方的
    # 竖直开运算、组件端点和投影谷底路径。以下旧增强/候选扫描字段
    # 保留用于配置兼容和未来实验，修改它们不会改变当前正式分割。
    clahe_clip_limit: float = 2.5
    clahe_tile_w: int = 8
    clahe_tile_h: int = 8

    # 旧候选扫描搜索范围（当前正式路径不读取）
    search_lo_ratio: float = 0.10
    search_hi_ratio: float = 0.75

    # 旧接缝密度候选扫描字段（当前正式路径不读取）
    density_band_ratio_denom: int = 12
    density_band_min: int = 25
    density_min_score: int = 4  # 最低分（两侧各至少2条线）

    # 旧闭运算回退字段（当前正式路径不读取）
    close_kernel_ratio: float = 0.33  # 核宽 = 图宽 * ratio（最小值 30）

    # 旧梯度候选字段（当前正式路径不读取）
    gradient_threshold_factor: float = 1.8  # 阈值 = 均值 × factor（最小值 0.04）
    gradient_min_thresh: float = 0.04

    # ── 最终回退比例（所有方案失败时）──
    #     物理先验：主尺约占 ROI 高度的 55%~65%
    fallback_split_ratio: float = 0.60

    # ── 游标区域最小高度比例 ──
    #     游标区至少有 ROI 高度的 28%，否则强制重分配
    min_vernier_height_ratio: float = 0.28

    # ── 竖向刻线图与水平投影 ──
    # 仅保留达到短刻线尺度的竖向结构，再从局部 x 窗口聚合为水平响应。
    vertical_open_height_ratio: float = 0.032
    vertical_open_min_height: int = 35
    vertical_open_max_height: int = 61
    projection_component_max_width_ratio: float = 0.0025
    projection_component_max_width_min: int = 8
    projection_component_max_width_max: int = 14
    projection_component_max_height_ratio: float = 0.22
    projection_use_components: bool = True
    seam_use_component_endpoints: bool = True
    projection_smooth_height_ratio: float = 0.008
    projection_smooth_min: int = 7
    projection_smooth_max: int = 13


# ═════════════════════════════════════════════════════════════
#  3. 主尺识别 — main_scale.py
# ═════════════════════════════════════════════════════════════
class MainScaleConfig:
    """主尺参数：自适应阈值 → 垂直投影 → 实测刻线提取 → x 精修。"""

    # ── 二值化（自适应阈值）──
    #     blockSize: 局部邻域大小（奇数）
    #     C: 从均值中减去的常数，越小前景越多（刻线越多）
    adaptive_block_size: int = 31
    adaptive_C: int = 2
    short_tick_recovery_enabled: bool = True
    short_tick_min_contiguous_ratio: float = 0.60
    short_tick_min_foreground_factor: float = 2.00
    short_tick_period_tolerance: float = 0.30

    # ── 历史兼容字段：当前正式路径不读取 ──
    # 旧 find_peaks_adaptive 的 min_dist；当前正式路径使用
    # _find_threshold_segments()，不读取该字段。
    peak_min_dist: int = 3
    # 当前投影阈值使用下面的 peak_threshold_factor。
    peak_threshold_factor: float = 0.20
    # ── 最小刻线数 ──
    min_tick_count: int = 3

    # ── 主尺长/短刻线判定 ──
    # 主尺仍使用该因子作为 OCR 锚点和长线恢复的辅助规则。
    long_tick_factor: float = 1.3

    # ── 等间距研究字段（当前正式流程不读取）──
    #     供 utils.refine_ticks_by_spacing() 的显式标准化/校准实验使用。
    #     该研究工具只在附近有图像前景支持时接受候选，不强制生成固定数量，
    #     也不是当前主尺结果的来源。
    spacing_refine_enabled: bool = True
    #     网格匹配容差比例（0.30 = 30% 间距）
    spacing_tolerance: float = 0.30
    #     间距 > S*gap_factor 触发补全（1.30 = 更敏感）
    spacing_gap_factor: float = 1.30
    #     间距 < S*dup_factor 触发去重（伪影过滤）
    spacing_dup_factor: float = 0.50
    #     网格吸附容差（0.28 = 偏移超过 28% 间距则保留原位）
    spacing_snap_ratio: float = 0.28


# ═════════════════════════════════════════════════════════════
#  4. 游标尺识别 — vernier_scale.py
# ═════════════════════════════════════════════════════════════

class VernierScaleConfig:
    """Vernier recognition params: projection window -> fixed 0.02mm -> alignment."""

    # ── 二值化（自适应阈值）──
    #     blockSize: 局部邻域大小（奇数）
    #     C: 从均值中减去的常数，越小前景越多（刻线越多）
    adaptive_block_size: int = 31
    adaptive_C: int = 4

    # ── 最小刻线数 ──
    min_tick_count: int = 3

    # ── 对齐置信度阈值 ──
    align_conf_perfect: float = 0.95  # 误差 <= 0.5px
    align_conf_strong: float = 0.9    # 邻居/最优 >= 3
    align_conf_moderate: float = 0.7  # 邻居/最优 >= 2
    align_conf_weak: float = 0.5      # 邻居/最优 >= 1.5
    align_conf_bad: float = 0.3       # 更差

    # ── 历史兼容字段：游标当前不按固定倍数分类 ──
    # 当前游标长短状态由观测到的连通域下端位置做两类聚类；该字段
    # 保留兼容旧调用接口，修改它不会改变当前游标分类。
    long_tick_factor: float = 1.3

    align_ambiguity_margin_gap_ratio: float = 0.002
    align_ambiguity_margin_min_px: float = 0.05
    align_ambiguity_margin_max_px: float = 0.10

    # ── 游标刻线带/连通域测量 ──
    tick_band_bottom_pad: int = 16
    component_vertical_open_height: int = 7
    component_vertical_bridge_gap: int = 10
    component_fallback_min_height_ratio: float = 0.50

    # ── 两侧谷底范围评分（全部来自当前图像，不生成理论刻线）──
    valley_score_depth_weight: float = 0.30
    valley_score_period_weight: float = 0.30
    valley_score_spacing_weight: float = 0.25
    valley_score_component_weight: float = 0.15
    valley_min_period_clarity: float = 0.20
    valley_min_total_score: float = 0.30
    valley_min_component_structure: float = 0.08
    valley_peak_support_near_periods: float = 1.0
    valley_peak_support_far_periods: float = 2.0
    valley_internal_break_periods: float = 1.3
    valley_score_tie_margin: float = 0.02
    valley_preferred_tick_count: int = 51
    recovery_min_observed_tick_count: int = 40

    # ── 实测周期候选清理 ──
    duplicate_period_ratio: float = 0.65
    long_cluster_min_separation_ratio: float = 0.20


# ═════════════════════════════════════════════════════════════
#  5. OCR 数字识别 — ocr.py
# ═════════════════════════════════════════════════════════════

class OCRConfig:
    """OCR 参数：上游定向连通域选框后的 patch 增强和引擎识别。

    当前正式路径由 ``merger.py`` 调用 ``ocr_patch_to_digit``；旧的全扫描
    投影、搜索、连通域合并和几何回退字段保留作配置兼容但不再读取。
    """

    # ── 历史兼容字段：旧 DigitReader.read() 路径不在正式链路 ──
    # 以下投影、搜索、连通域合并和回退字段保留供旧实验/兼容读取。
    # 当前正式 OCR 由 merger.py 定向裁剪数字 patch，不读取这些字段。
    projection_strong_factor: float = 0.5
    projection_min_strong: int = 3

    # 旧全扫描数字搜索区域
    search_tick_gap_ratio: float = 0.50
    search_y_min_ratio: float = 0.25
    search_y_min_height: int = 15

    # 旧全扫描连通域过滤
    cc_min_area: int = 8                 # 降低以捕获弱对比度数字
    cc_min_width: int = 3
    cc_min_height: int = 5
    cc_aspect_min: float = 0.0           # 去掉宽高比限制
    cc_aspect_max: float = 999.0

    # 旧全扫描连通域合并；当前多位标签组合使用 merger.py 的定向候选
    merge_x_gap_ratio: float = 0.30
    main_label_group_gap_ratio: float = 0.75

    # 旧全扫描候选框 padding
    pad_min: int = 3
    pad_divisor: int = 4

    # 旧全扫描回退框
    fallback_x_half_ratio: float = 0.18  # 半宽 = tick_gap * ratio 或 min_px
    fallback_x_half_min: int = 10
    fallback_y_end_ratio: float = 0.40   # y 终点 = 图高 * ratio（即刻度线上方）
    fallback_y_h_ratio: float = 0.20     # 搜索高度 = 图高 * ratio

    # ── 补丁增强 ──
    patch_resize_factor: int = 3         # 放大倍数（v6.5: 2→3，小 patch 更清晰）
    patch_clahe_clip: float = 2.5
    patch_adaptive_block: int = 11
    patch_adaptive_C: int = 3

    # ── Tesseract ──
    tesseract_psm: str = '8'             # Page Segmentation Mode: 8=单行
    tesseract_whitelist: str = '0123456789'

    # ── EasyOCR ──
    easyocr_allowlist: str = '0123456789'
    easyocr_min_size: int = 5
    easyocr_text_threshold: float = 0.3
    easyocr_low_text: float = 0.2
    easyocr_min_conf: float = 0.2


# ═════════════════════════════════════════════════════════════
#  5. 读数合并 — merger.py
# ═════════════════════════════════════════════════════════════

class MergerConfig:
    """历史合并配置兼容组；当前 merger.py 未读取这些字段。"""

    # ── 置信度评分 ──
    #     主尺刻线数不足阈值
    conf_main_tick_min: int = 5
    #     游标刻线数不足阈值
    conf_vernier_tick_min: int = 5
    #     间距变异系数阈值（超过则降级）
    conf_gap_cv_threshold: float = 0.15  # CV = std/mean

    # ── 绘制 ──
    #     标注线的颜色 BGR
    draw_main_tick_color: tuple = (0, 235, 100)     # 绿色
    draw_main_long_color: tuple = (0, 255, 80)       # 亮绿（长刻度）
    draw_vernier_tick_color: tuple = (255, 200, 50)  # 橙色
    draw_zero_line_color: tuple = (50, 150, 255)     # 蓝色
    draw_alignment_color: tuple = (50, 255, 150)     # 青绿


# ═════════════════════════════════════════════════════════════
#  主配置类
# ═════════════════════════════════════════════════════════════

class CaliperConfig:
    """游标卡尺识别总配置"""

    def __init__(self):
        self.preprocess = PreprocessConfig()
        self.roi = ROIExtractConfig()
        self.orient = OrientConfig()
        self.region_split = RegionSplitConfig()
        self.main_scale = MainScaleConfig()
        self.vernier_scale = VernierScaleConfig()
        self.ocr = OCRConfig()
        self.merger = MergerConfig()

    def reset(self):
        """将所有参数重置为默认值"""
        self.preprocess = PreprocessConfig()
        self.roi = ROIExtractConfig()
        self.orient = OrientConfig()
        self.region_split = RegionSplitConfig()
        self.main_scale = MainScaleConfig()
        self.vernier_scale = VernierScaleConfig()
        self.ocr = OCRConfig()
        self.merger = MergerConfig()

    def summary(self) -> str:
        """打印所有配置参数（调试用）"""
        lines = ["=== 游标卡尺识别参数配置 ==="]
        for group_name in ['preprocess', 'roi', 'orient', 'region_split',
                            'main_scale', 'vernier_scale', 'ocr', 'merger']:
            group = getattr(self, group_name)
            lines.append(f"\n── {group_name} ──")
            fields = {
                name: value
                for cls in reversed(type(group).__mro__)
                for name, value in vars(cls).items()
                if not name.startswith('_') and not callable(value)
            }
            fields.update(vars(group))
            for k, v in fields.items():
                lines.append(f"  {k} = {v}")
        return "\n".join(lines)


# ── 全局单例 ──
config = CaliperConfig()
