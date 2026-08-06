# 卡尺批量评估总表设计

## 目标

为 `tupian/` 中的测试图片建立可重复运行的批量评估报告，使用现有
`CaliperPipeline(fast_mode=True)` 正式识别流程，输出：

1. 每张图片一行的原始 JSON/CSV 结果；
2. 可直接用 Excel 查看和筛选的 `.xlsx` 文件；
3. 包含总体准确率、误差分布和疑似错误模块统计的 `summary` 工作表；
4. 保留人工复核字段，区分算法自动归因和最终确认归因。

该工具只用于离线评估，不读取文件名参与生产识别，不修改生产识别逻辑，
不根据文件名、理论刻线数量或期望读数补造结果。

## 背景与现状

项目已有 `tools/evaluate_all_pipeline.py`，能够：

- 遍历 `tupian/*.jpg`；
- 从文件名读取测试真值；
- 对 `14.80.jpg`、`33.00.jpg`、`38.30.jpg` 应用已有人工真值修正；
- 运行 `CaliperPipeline(fast_mode=True)`；
- 输出部分读数、OCR、主尺刻线、游标刻线和对齐字段到 JSON。

现有脚本缺少：

- 可复用的单张图片评估函数；
- CSV 和 Excel 导出；
- 明确的容差判断字段；
- 统一的自动疑似错误模块归因；
- 人工复核列；
- 总体统计和模块统计工作表。

## 设计范围

### 包含

- 扩展现有批量评估入口，而不是另建一套识别流程；
- 抽出纯函数或小型辅助函数，便于单元测试；
- 生成 JSON、CSV、XLSX 三种结果；
- 生成 `rows`、`summary` 两类 Excel 工作表；
- 自动归因只输出 `suspected_error_module`；
- 预留 `error_module_final`、`error_notes` 人工复核字段；
- 记录运行版本、时间、数据目录和容差配置。

### 不包含

- 修改 `caliper/` 内正式识别算法；
- 根据图片文件名修正生产读数；
- 强制拟合 51 条游标刻线；
- 自动生成不存在的刻线；
- 自动把疑似归因当作人工确认事实；
- 自动修改 50 张图片的人工标注；
- 训练机器学习模型或改变数据集。

## 输出目录与文件

默认输出目录：

```text
debug_tupian_batch_evaluation_20260806/
```

默认文件：

```text
evaluation.json
evaluation.csv
evaluation.xlsx
```

脚本应支持命令行参数覆盖输入目录和输出目录，默认仍使用项目根目录下的
`tupian/`。

## 数据流

```text
tupian/*.jpg
    |
    v
truth_from_name() + MANUAL_TRUTH_MM
    |
    v
evaluate_image(path)
    |
    +--> CaliperPipeline(fast_mode=True)
    +--> step_results: split/main/vernier
    +--> result.extra_info: OCR/读数推导
    |
    v
build_evaluation_row()
    |
    +--> tolerance / correctness
    +--> suspected_error_module
    +--> blank human review fields
    |
    v
JSON + CSV + XLSX(summary, rows)
```

`evaluate_image()` 必须返回一个普通字典，不让导出层依赖
`CaliperPipeline` 的内部对象。这样可以对归因、容差和导出单独测试。

## 评估行字段

### 事实和状态字段

| 字段 | 含义 |
|---|---|
| `image` | 图片文件名 |
| `truth_mm` | 离线评估真值；优先使用人工修正表，否则使用文件名 |
| `filename_truth_mm` | 可解析的文件名数值，便于审计真值修正 |
| `truth_source` | `filename` 或 `manual_correction` |
| `status` | `ok` 或 `failed` |
| `error` | 运行异常文本；正常行为为空 |
| `elapsed_ms` | 单张图片处理耗时 |

### 读数和误差字段

| 字段 | 含义 |
|---|---|
| `reading_mm` | 系统最终读数 |
| `main_scale_mm` | 主尺整数部分 |
| `vernier_scale_mm` | 游标小数部分 |
| `abs_error_mm` | `abs(reading_mm - truth_mm)` |
| `within_tolerance` | 是否满足离线评估容差 |
| `tolerance_mm` | 本行使用的容差 |

容差默认由命令行参数提供，默认值为 `0.02` mm；脚本不能把容差当作生产
识别逻辑，也不能用容差修正读数。

### 模块诊断字段

| 字段 | 含义 |
|---|---|
| `split_y` | 区域分割线位置 |
| `seam_source` | 分割线来源 |
| `main_tick_count` | 主尺候选刻线数量 |
| `vernier_tick_count` | 游标候选刻线数量 |
| `zero_x` | 游标 0 刻度线位置 |
| `alignment_confidence` | 游标对齐置信度 |
| `main_ocr_ok` | 主尺 OCR 是否成功 |
| `main_ocr_reason` | OCR 失败或降级原因 |
| `main_ocr_text` | OCR 原始文本 |
| `main_ocr_confidence` | OCR 置信度 |
| `suspected_error_module` | 规则自动推断的疑似首要错误模块 |
| `diagnostic_flags` | 其他同时满足的可疑条件，使用稳定的分号分隔编码 |
| `error_module_final` | 人工复核后的最终错误模块，初始为空 |
| `error_notes` | 人工复核备注，初始为空 |

`vernier_tick_count` 等字段只记录系统观察结果，不以理论 51 条作为正确
标准。

## 自动归因规则

自动归因是“筛查提示”，不是最终标签。规则按证据优先级执行，并只选择一个
首要模块；其他可疑情况放入 `diagnostic_flags`。

建议优先级：

1. `failed` 或缺少最终读数：`pipeline`
2. ROI 结果缺失、尺寸非法或出现低清 ROI 退回：`roi`
3. 分割线缺失、越界或主尺/游标区域高度明显异常：`region_split`
4. 主尺 OCR 失败、文本为空或明显为多位截断：`ocr`
5. 游标候选为空、0 线为空或对齐置信度缺失：`vernier_zero_line`
6. 游标候选数量/间距结构异常，但 0 线存在：`vernier_ticks`
7. 主尺候选为空或主尺刻线结构异常：`main_ticks`
8. 中间结果存在但最终值与真值超出容差：`reading_fusion`
9. 没有足够证据：`unknown`

这些规则只消费现有 `step_results` 和 `result.extra_info`，不使用真值调整
生产输出。真值只用于离线判断和归因报告。

## CSV 设计

CSV 使用 UTF-8 with BOM，保证 Windows Excel 打开中文字段不乱码。字段顺序
固定为“事实状态 -> 读数误差 -> 模块诊断 -> 人工复核 -> 中间数值”。

## XLSX 设计

不新增 pandas 依赖。使用 Python 标准库生成最小可用的 Open XML 工作簿：

- `rows` 工作表：完整逐图数据；
- `summary` 工作表：运行信息、总体指标、疑似模块计数、状态计数；
- 首行冻结；
- 自动筛选；
- 数值字段使用数值单元格；
- 人工复核列设置为空字符串；
- 列宽按字段名和内容上限计算。

## Summary 统计口径

`summary` 至少包含：

- 总图片数；
- 有效真值数；
- 运行成功数；
- 运行失败数；
- 满足 `0.02` mm、`0.10` mm、`0.50` mm 容差的数量和比例；
- 平均绝对误差；
- 最大绝对误差；
- 各 `suspected_error_module` 的计数；
- 各 `status` 的计数。

模块计数按“疑似首要模块”统计，不把一张图片重复计入多个首要模块。

## 测试策略

先测试后实现，至少覆盖：

1. 从普通文件名解析浮点真值；
2. 无法解析的文件名返回空真值；
3. 人工真值修正优先于文件名；
4. 容差边界 `0.02` mm 的包含关系；
5. OCR 缺失时归因为 `ocr`；
6. 游标 0 线缺失时归因为 `vernier_zero_line`；
7. 运行异常仍输出一行 `failed` 记录；
8. CSV 包含固定字段和 UTF-8 BOM；
9. XLSX 可以被标准库 `zipfile` 打开并包含 `rows`、`summary` 两个工作表；
10. 汇总统计与逐行数据一致。

测试不应运行完整 50 张图片作为单元测试；完整数据集运行属于集成验证。

## 验收标准

- 运行一次批量脚本即可生成 JSON、CSV、XLSX；
- 约 50 张图片每张都有一行，不因单张异常中断全批次；
- 现有正式识别流程调用方式不变；
- 生产代码和读数逻辑不被修改；
- 人工复核字段可在 Excel 中直接填写；
- 统计值可由 CSV/JSON 独立复算；
- 现有测试全部通过；
- 集成运行结束后报告中明确列出失败图片和疑似错误模块。
