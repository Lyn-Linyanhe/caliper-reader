# 主尺与游标尺标准化曲线设计

日期：2026-08-13  
状态：已获用户确认，等待实施计划审阅

## 1. 目标

为主尺和游标尺建立统一、可追溯的标准化曲线输出，使曲线能够表达“图像中实际观测到的刻线证据”，并在详细模式的 UI 和调试结果中展示。第一阶段只增加诊断数据和可视化，不改变正式刻线、零线、对齐和最终读数。

本设计针对两个现有但不对称的研究入口：

- 主尺的 `_standardize_tick_response()`：根据接缝侧连续前景支撑生成短线/长线显示响应。
- 游标尺的 `_build_length_clustered_standard_response()`：根据已接受游标刻线的实测长度做一维两类聚类并生成显示响应。

## 2. 非目标与硬约束

第一阶段明确不做以下事情：

1. 不强制拟合或补足 51 条游标刻线。
2. 不按理论等间距网格生成没有图像前景支持的刻线。
3. 不使用图片文件名、期望读数或人工真值修正曲线或正式读数。
4. 不用标准化曲线改写 `main_ticks`、`vernier_ticks`、`zero_x`、对齐候选、`vernier_reading` 或 `total`。
5. 不把连续对齐诊断值写回正式的 `0.02 mm` 离散读数。
6. 不改变快速模式的计算路径和正式输出。

如果以后要让标准化曲线参与候选筛选，必须另建显式开关、A/B 评估和回归测试，不在本设计范围内隐式接入。

## 3. 当前代码事实

正式调用链为：

```text
CaliperPipeline.run()
 -> split_scales()
 -> recognize_main_scale()
 -> recognize_vernier_scale()
 -> merge_readings()
```

主尺识别已经计算：

- 刻线带原始竖直投影 `vproj` 及归一化投影；
- 接缝侧连续前景支撑 `support`；
- 已接受刻线的 `x_projection`、`x`、`x_precise`、`length` 和 `is_long`；
- 详细图中的标准化响应。

但主尺标准化响应当前只是 `_draw_main_ticks()` 内的局部数组，没有结构化地放入 `step_results['main']`。

游标识别已经计算：

- 谷底范围内的原始投影；
- 连通域下端响应；
- 已接受游标刻线的 `length`、`component_bottom_y`、`x_projection`、`x_precise` 和长短状态；
- 长度两类聚类的标准化响应及聚类信息；
- 逐刻线独立追踪与拉直诊断面板。

游标标准化响应目前只在 `_draw_vernier_ticks_on_band()` 内生成，聚类信息没有作为独立的标准化结果对象保存。

## 4. 统一数据契约

主尺和游标尺均在详细模式返回一个 `standardization` 字典。建议结构如下：

```python
{
    'version': 1,
    'width': int,
    'x_offset': int,
    'curves': {
        'raw_projection': np.ndarray,
        'support': np.ndarray,
        'normalized_response': np.ndarray,
    },
    'ticks': [
        {
            'x': float,
            'x_projection': float,
            'measured_length': float,
            'support_value': float,
            'normalized_value': float,
            'class': 'short' | 'long' | 'unknown',
            'quality': float,
        },
    ],
    'classification': {
        'mode': 'single' | 'two_clusters' | 'unknown',
        'centers': [float, ...],
        'counts': [int, ...],
        'separation': float,
        'threshold': float | None,
    },
}
```

约定：

- `width` 是曲线数组所在局部图像的宽度。
- `x_offset` 将局部曲线坐标映射回旋转后 ROI 坐标；主尺通常为 0，游标为检测带的 `x1`。
- 所有曲线数组长度均为 `width`，没有隐式缩放或改变采样间隔。
- `raw_projection` 表示检测阶段实际使用的投影；不得用标准化响应替代。
- `support` 表示独立的结构证据。主尺使用接缝侧连续前景长度，游标使用连通域下端响应。
- `normalized_response` 只在已接受候选的观测位置生成峰，不生成缺失刻线。
- `ticks` 只描述已接受刻线；未匹配连通域不能被曲线伪装成已接受刻线。
- `quality` 是诊断排序值，不是统计意义上的概率或测量置信区间。
- 快速模式可返回 `standardization=None` 或不返回该键，但不能触发额外曲线计算。

为兼容现有测试和调用，保留 `_standardize_tick_response()` 与 `_build_length_clustered_standard_response()` 的原有返回形式；新增的结构化构建函数应在其外层组装结果，不直接改变旧 helper 的数组/元组接口。

## 5. 主尺标准化方案

### 5.1 输入

主尺标准化构建器接收：

- `region` 的主尺二值图和 `tick_band`；
- 已接受的 `main_ticks`；
- 已计算的归一化竖直投影；
- `_seam_anchored_support()` 生成的接缝侧支撑。

### 5.2 支撑值和长短分类

对每条已接受刻线，在 `x_projection ± 2 px` 范围取支撑最大值作为 `support_value`。标准化峰幅值采用：

- 短线：`1.0`；
- 长线：`1.5`。

长线分类可以继续使用现有的稳健分位数阈值，但必须同时记录：

- 使用的 `threshold`；
- 每条线的实际 `support_value`；
- 两类中心或等价的分离度；
- 分离不足时的 `unknown` 状态。

如果没有足够的有效支撑值，`classification.mode='unknown'`，曲线仍可绘制观测峰，但所有分类值为 `unknown`，不执行长线推断。

### 5.3 主尺曲线

主尺 `curves` 至少包含：

1. `raw_projection`：当前 `vproj_norm`。
2. `support`：当前接缝侧支撑，可按显示需要归一化，但不得改变原始支撑值字段。
3. `normalized_response`：以已接受刻线为中心、短线 1.0/长线 1.5 的高斯峰。

主尺标准化结果写入 `step_results['main']['standardization']`，详细图继续由该结构绘制。正式主尺刻线检测仍只使用原始投影、真实二值前景和现有精细化结果。

## 6. 游标尺标准化方案

### 6.1 输入

游标标准化构建器接收：

- 谷底确定的检测带及其局部坐标；
- 检测带原始投影；
- 已接受 `vernier_ticks`；
- `_component_bottom_response()` 生成的连通域下端响应；
- 每条刻线的实测 `length` 和组件信息。

### 6.2 长度聚类

继续使用当前观测长度的一维两类迭代，不引入外部理论曲线：

1. 丢弃非有限值和非正长度。
2. 对长度做 5/95 分位裁剪，降低孤立异常值影响。
3. 用 25/75 分位初始化两个中心。
4. 迭代按最近中心重新分组并更新中心。
5. 仅在两簇各至少 3 条、中心差不小于 `max(2 px, 0.20 × 中位长度)` 时确认双簇。
6. 其他情况标记为 `single` 或 `unknown`，所有响应峰使用 1.0。

需要把当前 `cluster_info` 扩展为：

- `mode`；
- `centers`；
- `counts`；
- `separation = (high - low) / max(low, 1.0)`；
- 使用的有效样本数和阈值。

### 6.3 游标曲线

游标 `curves` 至少包含：

1. `raw_projection`：谷底范围内的实际投影曲线。
2. `support`：连通域靠近接缝下端的响应曲线。
3. `normalized_response`：按长度簇绘制短线 1.0、长线 1.5 的响应。

游标标准化结果写入：

```text
step_results['vernier']['standardization']
step_results['vernier']['vernier_band_detection']['standardization']
```

两处引用应指向同一逻辑结果，避免 UI 和诊断脚本看到不同曲线。曲线不参与谷底候选评分、零线选择、对齐误差计算和正式小数读数。

## 7. UI 与调试图

详细模式下，主尺页面保持现有图像上方、曲线下方的纵向布局：

```text
主尺刻线叠加图
原始竖直投影
接缝侧支撑
标准化响应
```

游标页面继续使用同一页纵向合成图：

```text
游标刻线叠加图
原始投影
连通域下端响应
长度归一化标准响应
逐刻线校正诊断
```

标题必须展示实际模式和样本信息，例如：

```text
Length-normalized standard response
(two length clusters: 18.2/31.4 px, n=26/25, separation=0.72)
```

曲线面板使用独立深色背景和统一纵轴范围。任何框、谷底候选区或文字标签不得覆盖曲线主体；谷底诊断仍单独使用其现有面板。

## 8. 错误处理

- 空刻线列表：返回全零曲线和 `classification.mode='unknown'`，不抛异常。
- 宽度为零或输入数组形状不匹配：返回空结构或全零数组，并记录 `quality=0.0`。
- 长度/支撑值包含 `None`、NaN 或字符串：跳过该条，不影响其他候选。
- 聚类样本不足或分离不足：不强行分成两类，不抛异常。
- 结构化结果生成失败：详细图可降级到现有数组绘图，但正式读数必须继续使用原有路径；异常不得被静默地转化为新的正式刻线。

## 9. 测试与验收

### 9.1 单元测试

新增或扩展测试覆盖：

- 主尺结构化曲线的宽度、曲线长度、x 偏移和候选字段。
- 主尺支撑不足时 `unknown` 分类。
- 游标双簇长度在明显分离时得到正确中心、数量和 1.0/1.5 峰值。
- 游标近似单簇和样本不足时不误报双簇。
- 非有限长度、空组件和空输入不会抛异常。

### 9.2 回归测试

必须验证：

- `python -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp/standardization` 通过；
- `python -m compileall -q caliper main.py tools tests` 通过；
- 快速模式和详细模式在代表性样本上的 `total`、`main_scale`、`vernier_scale`、`zero_x` 一致；
- 49 张图片批量评估的当前基线不下降；
- 详细模式的代表图至少包括 `30.00.jpg`、`120.60.jpg`、`72.52.jpg`、`130.70.jpg`、`40.20.jpg` 和 `140.00.jpg`。

### 9.3 验收结果

验收需要同时给出：

1. 主尺和游标尺各一张标准化曲线可视化图。
2. 至少一张双簇成功、一张单簇/unknown 降级的游标示例。
3. 结构化结果字段示例及其坐标系说明。
4. 批量评估前后读数指标对比，证明第一阶段没有改变正式读数。

## 10. 后续接入条件

只有在曲线在不同 ROI、光照、刻线长度和连通域状态下稳定后，才讨论将其用于正式候选评分。后续接入必须满足：

- 增加显式配置开关，默认关闭；
- 明确曲线影响的是候选生成、候选过滤还是对齐评分；
- 保留原始观测证据和回退路径；
- 对已知失败样本和正常样本分别做 A/B 批量评估；
- 不以理论数量、文件名真值或最终读数反向修正曲线。
