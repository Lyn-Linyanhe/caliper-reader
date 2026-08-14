"""
游标卡尺读数识别 — caliper 包

流水线架构:
  步骤 0: 图像预处理（增强 + 滤波 + 二值化）
  步骤 1: ROI提取 + 方向矫正
  步骤 2: 区域分离（主尺 / 游标尺）
  步骤 3: 主尺刻线识别（刻线几何 + main_gap）
  步骤 4: 游标刻线识别（谷底范围 + 零线 + 对齐）
  步骤 5: 定向 OCR、读数合并 + 最终标注

主尺 OCR 在步骤 4 得到 zero_x 后由 merger.py 执行；主尺和游标模块
中的详细模式标准化曲线、连通域响应和逐刻线校正图属于诊断/研究路径，
不改变步骤 5 的正式读数。
"""

from .result import CaliperResult, TickInfo, DigitInfo
from .pipeline import CaliperPipeline, read_caliper, read_caliper_from_array
from .config import config

__version__ = "4.0.0"
__all__ = [
    'CaliperPipeline',
    'CaliperResult',
    'TickInfo',
    'DigitInfo',
    'config',
    'read_caliper',
    'read_caliper_from_array',
]
