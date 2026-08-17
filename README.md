# 游标卡尺读数识别

本项目使用 Python、OpenCV、Tkinter 和 OCR，从游标卡尺照片中读取毫米读数。它面向 **游标分度为 0.02 mm** 的卡尺：先由图像中的主尺数字和刻线确定整数部分，再由实际检测到的游标刻线与主尺刻线对齐确定小数部分。

项目的目标是让每一个结果都能回溯到图像证据。生产识别不读取文件名推断读数，不按理论网格补造刻线，也不强制把游标刻线拟合成固定的 51 条。文件名只可用于测试时提供真值。

```text
原始照片
  -> ROI 定位
  -> 预处理与方向校正
  -> 主尺 / 游标尺区域分离
  -> 主尺刻线检测
  -> 游标尺谷底范围、刻线与 0 线检测
  -> 主尺数字 OCR 与整数推导
  -> 游标对齐与小数推导
  -> 合并读数、质量提示与可视化
```

## 目录

- [能力与边界](#能力与边界)
- [先看这一页](#先看这一页)
- [安装与启动](#安装与启动)
- [GUI 使用](#gui-使用)
- [完整识别流程](#完整识别流程)
- [算法与参数参考](#算法与参数参考)
- [读数、歧义与结果字段](#读数歧义与结果字段)
- [调试图与失败排查](#调试图与失败排查)
- [Python API](#python-api)
- [测试与评估](#测试与评估)
- [限制与使用建议](#限制与使用建议)

## 先看这一页

### 什么是正式读数

以下四个字段共同构成一次识别的正式结果：

```text
main_scale      主尺部分，单位 mm
vernier_scale   游标部分，单位 mm，必定是 0.02 的整数倍
total           正式总读数 = main_scale + vernier_scale，单位 mm
precision       当前固定为 0.02 mm
```

程序对外给出的结论只有 `CaliperResult.total`。例如 `total == 75.50`，表示正式读数为 `75.50 mm`；它不是把某条刻线“估算”到 `75.51 mm` 后再四舍五入的结果。

下面这些内容**不是**正式读数，不能替代 `total`：

| 内容 | 它是什么 | 正确用法 | 绝对不能做什么 |
| --- | --- | --- | --- |
| `continuous_index` | 对齐误差曲线的亚像素插值位置 | 判断最佳对齐附近是否平坦 | 乘以 `0.02` 后写入读数；这会产生 `0.03 mm` 等非分度值。 |
| `reference_total` | 歧义时相邻真实刻线的参考总读数 | 供人眼复核两条几乎同样对齐的线 | 覆盖 `total` 或自动挑选看起来更接近文件名的值。 |
| `confidence` | 内部结构质量提示 | 决定是否需要查看详细图 | 当作测量误差上限或准确率。 |
| 文件名 | 测试真值的便捷标记 | 计算离线评估误差 | 参与生产识别或修正 OCR/游标结果。 |

### 什么情况下可以接受，什么情况下必须排查

| 看到的结果 | 结论 | 下一步 |
| --- | --- | --- |
| `total` 非零、无橙色歧义提示，最终标注与刻线一致 | 可作为程序给出的正式候选读数 | 对关键照片仍建议查看最终标注。 |
| `total` 非零，出现“对齐歧义” | `total` 仍是正式候选，`reference_total` 是相邻备选 | 打开“游标对齐”图，比较蓝色正式线和橙色 `ALT` 线。 |
| `total == 0.0`，但照片并非真实零刻度 | 识别失败或主尺整数缺失 | 先看 `extra_info['error']`；若没有，再看 `main_derivation['ocr_reason']` 和 ROI/分割图。 |
| 主尺正确、游标小数偏差一个或数个分度 | 通常是游标谷底窗口、零线或游标刻线问题 | 按“游标刻度线”页从谷底、首条线、连通域、对齐顺序检查。 |
| 主尺整数偏差 10 mm、100 mm 或 OCR 空 | 通常是 OCR 框、数字组合、ROI 或主尺锚点问题 | 先检查“主尺数字 OCR”，再回看 ROI 和区域分离。 |

### 一次读数必须经过的证据链

任何可信的最终读数，都应能在下列链路中逐项找到依据：

```text
ROI 覆盖数字和刻线
  -> 分割线没有截断两套刻线
  -> 主尺刻线与 main_gap 合理
  -> 游标两侧谷底夹住完整刻线范围
  -> 范围内第一条真实线是 zero_x
  -> OCR 数字绑定到正确的主尺长刻线
  -> 最佳游标线与主尺线对齐
  -> main_scale + vernier_scale = total
```

其中任一环节缺少图像证据，都不应靠文件名、固定刻线数量、理论网格或人工期望值补上。

## 能力与边界

当前实现具备下列能力。

- 自动从全图定位读取所需的紧凑 ROI，目标是覆盖主尺数字、主尺刻线、游标刻线和分割接缝，同时尽量排除背景与卡尺无关部件。
- 通过接缝线的 RANSAC 估计校正整体倾斜；后续坐标统一使用校正后的 ROI 坐标系。
- 从二值图和投影中实际检测主尺、游标尺刻线，并保存每条线的横坐标、纵向范围、长度及可视化证据。
- 用游标刻线带横向投影中的两侧有效谷底确定游标刻线横向窗口；窗口中第一条已验证、实际观察到的刻线是游标 `0` 线。
- 用主尺 OCR 识别厘米数字，支持相邻字符组合成 `10` 至 `15` 等多位数字，并与最近的主尺长刻线绑定。
- 当 OCR 首次候选框没有数字或 OCR 无有效数字时，向上下各扩展一次数字候选范围后重试；仍失败才尝试以长主尺刻线为锚点。这是 OCR 的候选框回退，不是对读数的猜测。
- 游标正式小数读数始终为 `0.02 mm` 的整数倍。若最佳刻线与一个相邻真实刻线的对齐误差几乎相同，界面提供一个仅供人工复核的参考读数。
- GUI 提供快速模式和详细模式。详细模式能查看 ROI、区域分离、主尺/游标刻线、OCR、谷底、连通域、对齐和最终标注。

当前不支持自动识别 `0.05 mm`、`0.1 mm` 等其他游标分度，也不能保证在强反光、严重模糊、遮挡或有效结构未被 ROI 覆盖时输出可靠值。`total == 0.0` 在通常业务照片中应优先视为识别失败，必须查看 `extra_info['error']` 或 OCR 推导信息，而不是直接当作有效的零刻度测量。

## 安装与启动

### Python 与依赖

项目当前在 Python 3.12 环境下验证。使用任意可用的 Python 3.12 或更高版本安装依赖：

```powershell
python -m pip install -r requirements.txt
python main.py
```

`requirements.txt` 包含：

- `opencv-python`：图像读写、几何变换、二值处理、形态学和连通域。
- `numpy`：投影、统计和数组计算。
- `Pillow`：Tkinter 图像显示。
- `pytesseract`：Tesseract 的 Python 调用接口。
- `easyocr`：Tesseract 不可用时的 OCR 备用引擎。

### OCR 引擎

安装 `pytesseract` 并不等于安装 Tesseract 本体。在 Windows 上，若需要 Tesseract，必须另外安装其可执行程序并保证程序可发现。运行时会优先使用可用的 OCR 引擎；Tesseract 不可用时会尝试 EasyOCR。若没有可用 OCR 引擎，主尺整数没有可靠来源，最终读数不能作为有效测量。

## GUI 使用

1. 运行 `python main.py`。
2. 点击“打开图像文件”选择卡尺照片。
3. 默认勾选“快速模式”。快速模式复用中间二值结果、减少调试图绘制并使用简化的最终标注，适合批量或日常查看。
4. 需要诊断时取消“快速模式”，重新打开图片。详细模式会生成各阶段中间图，处理时间相对更长。
5. 左侧显示精度、主尺读数、游标读数、总读数、总质量提示和 OCR 引擎状态；右侧标签页显示中间结果。

当游标存在相邻刻线对齐难以区分的情况，总读数下会显示橙色文字，例如：

```text
对齐歧义：推荐 75.50 mm；参考 75.52 mm（误差 1.00 / 1.00 px）
```

“推荐”是正式输出，仍保存在 `CaliperResult.total`；“参考”只用于人工判断图像中哪条线更贴近，绝不自动替换正式输出。详细模式的“游标对齐”图中，参考刻线用橙色 `ALT` 标记。

## 完整识别流程

### 流程总览：每一步负责什么

下表是排查时的最短路径。先用“输入/输出”确定问题首次出现的步骤，再阅读对应小节的细节；不要从最终读数直接猜某一个阈值应当修改。

| 步骤 | 输入 | 这一步唯一负责的事情 | 关键输出 | 输出异常时优先看 |
| --- | --- | --- | --- | --- |
| 1. ROI 定位 | 原始照片 | 裁出包含读数结构的紧凑图像 | `roi_box_original`、`roi_source` | ROI 是否缺数字、零线、主尺或游标末端；是否多带入背景。 |
| 2. 预处理 | ROI 彩色图 | 产生增强灰度和稳定二值前景 | `enhanced`、`binary_adaptive` | 刻线是否因反光/模糊消失，数字是否与刻线大面积粘连。 |
| 3. 方向校正 | ROI 灰度/二值/彩色图 | 把卡尺整体接缝校正为近水平 | `rotated_*`、旋转角 | 刻线是否仍整体倾斜。 |
| 4. 区域分离 | 校正后二值图 | 找到主尺和游标之间的 `split_y` | `region_main`、`region_vernier`、`seam_source` | 绿色刻线带是否截短主尺，或把主尺混入游标。 |
| 5. 主尺刻线 | 主尺 `tick_band` | 观察而非生成主尺毫米线 | `main_ticks`、`main_gap` | 漏线、多线、短线和 `main_gap` 是否不稳定。 |
| 6. 游标刻线与零线 | 游标 `tick_band`、`main_gap` | 用两侧谷底圈出游标范围，提取真实线并确定第一条零线 | `vernier_ticks`、`zero_x` | 谷底是否夹对范围；数字 `0` 是否干扰首条线。 |
| 7. OCR 与主尺整数 | `zero_x`、主尺线、数字候选图 | 识别厘米数字并换算零线左侧主尺毫米值 | `main_digits`、`main_derivation`、`main_scale` | OCR 框、字符组合、标签和锚点是否正确。 |
| 8. 游标对齐与合并 | 主尺线、游标线、主尺整数 | 选误差最小的已观测游标线，输出离散小数和总值 | `vernier_scale`、`total`、`alignment_ambiguity` | 最佳线是否真实存在；是否应显示相邻参考线。 |

**重要：** 第 5 到第 8 步不会修复第 1 到第 4 步已经造成的裁切或混入问题。ROI/分割错误时，先修复前置图像范围，再评估刻线、OCR 和对齐。

### 1. ROI 定位

实现：`caliper/roi_extract.py::locate_roi_lowres`

输入为全图彩色图像。算法先在低分辨率灰度图上进行 gamma/CLAHE 增强和自适应阈值化，再从水平与垂直投影中定位卡尺主体。随后通过游标主体、读数窗口结构和有效刻线支撑对候选范围细化，最后映射回原始分辨率并保留有限安全边界。

ROI 候选分为较紧凑的读数窗口和较完整的主体窗口。选择时优先保证数字、主尺刻线和游标结构仍在范围内，而不是单纯选择面积最小的框。`roi_source` 记录最终来源，`roi_box_original` 是其在原图中的 `(x1, y1, x2, y2)` 坐标，`roi_selection` 保存候选选择诊断。

当前 ROI 不使用螺丝模板匹配。正式路径由低分辨率投影得到初框，再通过主体边缘、游标结构和紧凑读数窗口验证逐级细化。ROI 过大时背景、卡尺边缘或数字更容易进入后续投影；ROI 过小时主尺数字、主尺长刻线或游标端部可能被裁掉。因此 ROI 既要覆盖有效信息，也要尽可能紧凑。

若游标阶段明确报告 `no_reliable_valley_bounded_tick_range`，并且初始 ROI 已预先生成局部扩边候选，流水线才会尝试这些候选。每一个候选仅在原紧凑 ROI 的边缘增大，不会退回成明显更大的全主体框；只有候选结果无游标错误、具有有效 `zero_x` 且检测到足够多的真实游标刻线时才采纳。该恢复机制不会补线，也不在正常结果上更换 ROI。恢复信息位于 `extra_info['roi_recovery']`。

### 2. ROI 预处理

实现：`caliper/preprocess.py::preprocess`

预处理依次生成灰度图、gamma 校正、双边滤波、中值滤波、CLAHE、锐化、自适应二值图、形态学开运算和小连通域过滤结果。主要输出为增强灰度图 `enhanced` 与自适应二值图 `binary_adaptive`。后续模块优先复用这份二值图，避免每个阶段独立阈值化造成结构不一致。

二值图的前景用于刻线投影与连通域证据，不等于“每个前景像素都是刻线”。数字、边缘、螺丝和噪声同样可能成为前景，因此后续步骤必须用区域、几何、长度、连通域和周期一致性继续筛选。

### 3. 全局方向校正

实现：`caliper/roi_extract.py::orient_caliper`

算法从卡尺接缝的多组候选点估计直线，使用 RANSAC 抑制离群点后得到旋转角度，同时旋转彩色图、增强灰度图和二值图。主尺、游标、OCR 的所有后续坐标都在同一套旋转坐标系中工作。

方向校正的目的不是把每条刻线单独拉直，而是消除整体拍摄倾斜。若接缝本身不清晰或受到遮挡，方向估计质量会下降，并进一步影响区域分离的水平接缝和刻线的垂直长度测量。

### 4. 主尺与游标尺区域分离

实现：`caliper/region_split.py::split_scales`

区域分离沿 `y` 方向寻找两套刻线之间的接缝 `split_y`。它先在二值前景上做竖直开运算，突出细竖直结构；再从连通域起点、终点响应中寻找主尺刻线末端和游标刻线起端相邻的接缝。证据不足时回退到刻线带投影谷底，最后才使用物理比例回退。

`seam_source` 记录接缝来源，例如连通域端点或投影谷底。分离后分别构造 `region_main` 和 `region_vernier`，每个区域都包含 `tick_band`。`tick_band` 是该区域内允许进行刻线投影的纵向带：它排除数字、边框和大部分背景，直接决定后续刻线检测的长度与可靠性。

接缝偏上会截短主尺下端或让游标区域过高；接缝偏下会把主尺结构混入游标区域。两种情况都会使刻线长度、数字 OCR 候选高度和对齐证据偏离，所以区域分离错误通常不能仅靠后续调参补救。

### 5. 主尺刻线检测

实现：`caliper/main_scale.py::recognize_main_scale`

主尺检测只在 `region_main.tick_band` 内做竖直投影。算法从投影峰段得到候选，估计相邻毫米线的实际像素间距 `main_gap`，合并重复响应，并回到局部二值图测量每条刻线的 `x` 坐标、`y_start`、`y_end` 和 `length`。`x_precise` 是供精细对齐使用的亚像素横坐标。

`x_precise` 当前采用第二版亚像素精修。对灰度窄带的每一行，先在刻线左右两侧寻找梯度极小值和极大值，得到整数边缘 `l`、`r`，其中心为 `x_base`。再分别用极值点及其左右邻点做三点抛物线插值，得到连续中心 `x_continuous`；单侧插值偏移限制在 `[-0.5, 0.5] px`，最终只融合一半修正量：

```text
x_precise = x_base + 0.5 * (x_continuous - x_base)
```

该折中保留了二值/整数边缘定位的稳定性，又减少了原先约 `0.25 px` 量化造成的同分候选。主尺和游标尺都调用同一个函数；它只改变刻线横坐标及对齐误差曲线，不改变游标的离散分度，正式小数仍按 `best_index * 0.02 mm` 计算。

对靠近接缝、在区域裁剪后看起来过短的主尺刻线，检测会根据完整二值图的可见部分恢复其测量范围。该行为只恢复已观察到的前景长度，不会在没有图像证据的位置生成主尺线。

主要输出：

- `main_ticks`：实际检测到的主尺刻线字典列表。
- `main_gap`：相邻主尺毫米线的估计像素间距。
- `vis_ticks`：详细模式的主尺刻线可视化。

主尺 OCR 在合并阶段执行，因为数字候选的水平位置必须依赖稍后得到的游标零线 `zero_x`。

### 6. 游标谷底、刻线与零线

实现：`caliper/vernier_scale.py::recognize_vernier_scale`

游标检测只在 `region_vernier.tick_band` 形成的窄竖直刻线带内工作，核心步骤如下。

1. 对刻线带做横向竖直投影并平滑，得到“该 x 位置是否具有刻线”的响应曲线。
2. 从低响应连续段中枚举左右谷底对。有效谷底必须两侧都有足够高的峰支持，且两谷底之间不能出现大的内部谷底或明显断裂；这避免把一段平坦背景当成游标窗口。
3. 在每个谷底对之间提取高于投影阈值的峰段，估计已观测刻线的周期，并用周期一致性、投影清晰度、连通域支撑、刻线结构和候选数量评分选择最可靠范围。候选分数相近时，接近预期数量仅是排序证据之一，不会要求或伪造 51 条线。
4. 在每个投影候选附近提取细竖直连通域。短的上下断裂先按有限间距桥接，再使用竖直开运算突出长细线；候选需有足够的细长结构和合适的上缘关系。
5. 数字 `0` 可能与上方零刻线粘连。首端候选因此允许从上方范围继续向下追踪细竖线，而不能仅因起始几行为空白或整个连通域宽大就错误丢弃真实零线。
6. 在选定的谷底横向范围内，按 `x` 排序后第一条通过验证、实际检测到的刻线就是游标 `0` 线，输出为 `zero_x`。后续每一条游标线以该零线为第 `0` 条、第 `1` 条……计数。

这里的连通域是过滤和验证证据，不是单独决定零线的唯一来源。特别是数字与刻线粘连时，完整连通域可能很宽；算法关注其上方可连续追踪的细竖直结构，不能机械地把“宽连通域”全部判为数字噪声。

主要输出包括 `vernier_ticks`、`zero_x`、`aligned_tick`、`vernier_reading`、`alignment_confidence`、`alignment_ambiguity`、`vernier_band_detection`、`vis_ticks` 和 `vis_alignment`。失败时会返回 `error`，常见值为 `no_reliable_valley_bounded_tick_range`。

### 7. 游标对齐与离散小数读数

每一条已检测的游标刻线与最近主尺刻线计算横向距离，距离最小的游标线为最佳对齐线。若最佳线在排序后的索引为 `best_index`，正式游标小数为：

```text
vernier_scale = best_index * 0.02 mm
```

局部误差曲线仍会计算抛物线亚像素插值，其结果保存为 `continuous_index`，用于诊断最佳位置附近的曲线形状；它绝不参与正式读数。因此正式 `vernier_scale` 永远是 `0.00`、`0.02`、`0.04` 等 `0.02 mm` 网格值，不会出现 `0.03 mm`。

#### 对齐歧义参考值

最佳刻线左右相邻、且实际检测到的游标线中，误差最小的一条可作为参考候选。只有参考误差与最佳误差的差值位于由 `main_gap` 换算并限制在 `0.05` 至 `0.10 px` 的窄阈值内，才创建 `alignment_ambiguity`。该信息包含：

- `primary_index` / `primary_reading` / `primary_error_px`：正式最佳候选。
- `reference_index` / `reference_reading` / `reference_error_px`：仅供复核的相邻真实刻线。
- `margin_px`：两者误差之差。
- `threshold_px`：本图最终使用的歧义判定阈值。

参考值必须是最佳候选左右相邻的已观察刻线，不能来自缺失刻线、理论网格或任意较远刻线。歧义提示只增加诊断信息，不改变最佳候选、不降低或抬高正式小数，也不修改 `CaliperResult.total`。

### 8. OCR、主尺整数与合并

实现：`caliper/merger.py::merge_readings` 与 `caliper/ocr.py`

游标零线 `zero_x` 决定应读取哪一侧的主尺整数。算法首先在零线上方、左侧附近，使用主尺间距 `main_gap` 截取数字候选纵向范围：默认从主尺刻线带上缘向上约 `4 * main_gap` 到 `1 * main_gap`。这使数字区域跟随实际刻线位置，而不是用固定绝对 y 坐标。

二值图中的数字连通域被分割为字符 patch 后送入 OCR。相邻字符会按空间关系组合为有效厘米数，例如 `1` 和 `0` 组合为 `10`，用于避免多位主尺数字被截成首位。首次没有候选数字连通域或 OCR 无有效数字时，候选框向上下扩展一次重试；仍失败时可由主尺长刻线提供锚点回退。

识别到的厘米标签会绑定到最近主尺刻线。系统优先选择位于零线左侧最近的有效标签；若只有零线右侧紧邻的标签可用，并且其刻线确实在零线右侧，则该标签数值减一，用作零线左侧应有的整数。该规则只处理相邻整数刻度的物理关系，不从文件名或预期读数推断数字。

读数公式为：

```text
main_scale = ocr_cm_value * 10 + reference_tick 到 zero_x 之间的主尺毫米刻线数
total = main_scale + vernier_scale
```

OCR 失败时，主尺部分会返回 `0.0`，并在 `extra_info['main_derivation']['ocr_reason']` 中说明原因，例如 `no_digit_component`、`ocr_no_digit` 或 `no_ocr_digit_left_of_zero`。此时即使游标小数存在，`total` 也不应被视作完整测量值。

## 算法与参数参考

本节对应当前源码中的 `caliper/config.py`。这里的“默认值”是当前代码真正的默认值；除非明确标为“保留/当前主路径未读取”，否则都能在当前处理路径中找到调用点。

### 记号、评分与调参原则

为避免“一个像素阈值”在不同照片尺寸下含义不清，本文统一使用下列记号：

| 记号 | 含义 |
| --- | --- |
| `W`, `H` | 当前 ROI 或当前阶段图像的宽、高，单位像素。 |
| `g` | `main_gap`，相邻主尺 1 mm 刻线的实测中位像素间距。 |
| `p` | 游标候选刻线的实测周期，由已检测峰的位置差估计。 |
| `P(x)` | 某一刻线带在横坐标 `x` 的竖直前景投影。 |
| `E_i` | 第 `i` 条游标线到最近主尺线的横向距离，单位像素。 |

调参必须遵守下面顺序。

1. 先固定输入图片、保留修改前的详细模式图和全量评估报告。
2. 只改一个同类参数，并同时观察目标图和正常图；不能只让问题图变好。
3. 先确认错误首次出现的位置。ROI 或 `split_y` 错误时，不允许先调游标谷底、OCR 或对齐参数。
4. 以图像证据为准：参数只能改变“接受或拒绝已观察到的结构”，不能根据文件名、理想读数、固定 51 条线或理论网格生成不存在的刻线。
5. 每次改动后重跑 `tools/evaluate_all_pipeline.py` 和相关专项测试，比较准确率、`0.02 mm` 网格约束与问题图可视化。

### 参数状态说明

`config.py` 是一个汇总配置文件，包含当前主路径、备用逻辑和历史兼容字段。下表中的状态很重要：

| 状态 | 含义 |
| --- | --- |
| **生效** | 当前流水线的代码路径直接读取该值。 |
| **条件生效** | 仅在对应回退、开关或异常条件出现时读取。 |
| **保留** | 字段仍在配置类中，但当前主路径没有调用点；修改它不会改变当前结果。 |

### A. 预处理：灰度、增强与二值前景

实现：`caliper/preprocess.py::preprocess`

对灰度像素 `I`，gamma 步骤使用查表变换：

```text
I_gamma = 255 * (I / 255)^(1 / gamma)
```

之后依次执行双边滤波、可选中值滤波、CLAHE、可选反锐化，再对增强图做高斯自适应阈值。当前 `adaptive_binary_scale=0.8` 时，先缩小到 `0.8W x 0.8H`，阈值窗口也按相同比例缩放，二值结果再用最近邻放回原尺寸。这样降低高分辨率纹理对阈值的敏感度，同时不引入灰度插值。

| 参数 | 默认值 | 状态 | 算法作用 | 增大后的主要影响与风险 |
| --- | ---: | --- | --- | --- |
| `gamma` | `1.5` | 生效 | 上式中的幂指数；`gamma > 1` 提亮中间调，`gamma < 1` 压暗中间调。 | 暗刻线/数字的相对对比可能改变，但过大可能放大背景纹理。 |
| `bilateral_d`, `bilateral_sigma` | `5`, `25.0` | 生效 | 双边滤波的邻域直径与空间/灰度平滑强度。 | 噪声更少，但细刻线边缘可能被抹平。 |
| `median_ksize` | `0` | 条件生效 | `>= 3` 时额外中值滤波；偶数会升为下一奇数。 | 去椒盐噪声更强，但会削弱很短或很细的笔画。 |
| `clahe_clip_limit` | `1.0` | 生效 | CLAHE 的局部对比度截断。 | 局部对比更强；过大时反光边缘和纸纹也会变成前景。 |
| `clahe_tile_w`, `clahe_tile_h` | `8`, `8` | 生效 | CLAHE 分块网格。 | 分块更细会更局部，可能引入块间亮度不连续。 |
| `unsharp_amount`, `unsharp_blur_sigma` | `0.25`, `1.5` | 生效 | `enhanced = (1+a)I - a*Gaussian(I)`。 | 刻线边缘更锐；过强会产生双边/伪峰。 |
| `adaptive_binary_scale` | `0.8` | 生效 | 二值化前的缩放比例。 | 更小更平滑但会损失细笔画；`>=1` 时不缩放。 |
| `adaptive_block_size`, `adaptive_C` | `91`, `17` | 生效 | 局部阈值窗口与从局部均值减去的常数。 | 更大窗口抗小纹理但不适应局部光照；更大 `C` 会减少白色前景。 |
| `morph_open_enabled` | `False` | 条件生效 | 开关开启时用 `morph_open_kernel_size=3`、`iterations=1` 做椭圆开运算。 | 可去小噪声，也可能断开细刻线；默认关闭以保护细结构。 |
| `cc_filter_enabled` | `False` | 条件生效 | 开关开启时删除面积小于 `cc_min_area=50` 的连通域。 | 可去孤立噪声，也可能删除弱数字笔画；默认关闭。 |

### B. ROI 与方向校正：先保证输入几何正确

实现：`caliper/roi_extract.py::locate_roi_lowres`、`orient_caliper`

低分辨率 ROI 使用中心投影、游标主体和读数窗口结构产生候选。`x_center_span_ratio=0.30`、`y_center_span_ratio=0.22` 限制中心回退窗的相对尺寸；投影边界外再使用 `x_pad_ratio=0.15`、`y_pad_ratio=0.10` 扩边。`min_roi_width=30`、`min_roi_height=15` 是任何候选必须满足的最小像素尺寸。

方向校正不再采用配置中的 Hough 参数作为主方法，而是从接缝候选点拟合 RANSAC 线。实际生效的 `angle_detection_scale=0.75` 先缩小用于角度估计，以减少计算量；得到的接缝角度会直接用于旋转彩色、灰度和二值图。当前 `orient_caliper` 不读取 `rotate_min_angle`、`rotate_max_angle` 或 Hough 参数，因此它们不能用于改变当前旋转行为。

| 参数 | 默认值 | 状态 | 调整含义 |
| --- | ---: | --- | --- |
| `x_center_span_ratio`, `y_center_span_ratio` | `0.30`, `0.22` | 生效 | 增大会扩大投影中心回退窗，减少裁掉风险但更易纳入背景。 |
| `x_pad_ratio`, `y_pad_ratio` | `0.15`, `0.10` | 生效 | 增大会保留更多边界；过大将降低后续投影纯度。 |
| `min_roi_width`, `min_roi_height` | `30`, `15` px | 生效 | 提高可拒绝过小错误候选；过高可能误拒绝远景或低分辨率照片。 |
| `angle_detection_scale` | `0.75` | 生效 | 角度估计的缩放比例；更小更快但接缝点定位更粗。 |
| `contour_*`、`score_weight_*`、`morph_kernel_ratio` | 见 `config.py` | 保留 | 当前低分辨率主路径不使用轮廓评分回退；不要把它们当成 ROI 效果的调参入口。 |
| `canny_*`、`hough_*`、`angle_min/max`、`trim_ratio`、`rotate_min/max_angle` | 见 `config.py` | 保留 | 当前方向主路径使用接缝 RANSAC，不是 Hough 线段投票；修改这些字段不会替代或重设当前 RANSAC 判定。 |

### C. 区域分离：`split_y` 与两条 `tick_band`

实现：`caliper/region_split.py::split_scales`

先对二值图做竖直开运算，保留高而窄的前景成分，再沿 `y` 聚合其端点响应。优先选择“主尺刻线末端”和“游标刻线起端”之间的连通域端点接缝；失败时才从平滑的行投影谷底选接缝；再失败使用 `split_y = 0.60H`。最后强制游标区域高度至少为 `0.28H`，并在接缝两侧重新求 `tick_band`。

| 参数 | 默认值 | 状态 | 算法作用与调节风险 |
| --- | ---: | --- | --- |
| `seam_use_component_endpoints` | `True` | 生效 | 启用端点接缝优先级。关闭后直接失去最强几何证据，通常不应关闭。 |
| `vertical_open_height_ratio` | `0.032H` | 生效 | 竖直开运算核高，最终夹在 `35` 到 `61` px。过小会保留文字/噪声，过大可能吃掉短刻线。 |
| `projection_component_max_width_ratio` | `0.0025W` | 生效 | 可用于端点投影的连通域最大宽度，最终夹在 `8` 到 `14` px。增大后更宽的文字笔画可能混入。 |
| `projection_component_max_height_ratio` | `0.22H` | 生效 | 端点组件允许的最大高度。过大可能引入非刻线长结构。 |
| `projection_smooth_height_ratio` | `0.008H` | 生效 | 行响应平滑窗口，最终夹在 `7` 到 `13`。增大使谷底更稳定但会移动窄接缝。 |
| `search_lo_ratio`, `search_hi_ratio` | `0.10`, `0.75` | 保留 | 旧的候选扫描搜索范围，当前主路径不读取；仅作为历史配置保留。 |
| `density_band_ratio_denom`, `density_band_min`, `density_min_score` | `12`, `25`, `4` | 保留 | 历史接缝密度候选扫描参数；当前端点/投影主路径没有读取点，修改它们不会改变当前分割线。 |
| `fallback_split_ratio` | `0.60H` | 条件生效 | 仅所有图像证据失败时使用的物理比例，不能作为常规准确性来源。 |
| `min_vernier_height_ratio` | `0.28H` | 生效 | 防止游标区域过矮。增大可保护游标，但可能把接缝强制上移。 |
| `clahe_*`, `close_kernel_ratio`, `gradient_*` | 保留值 | 保留 | 属于旧的分割回退设定，当前端点/投影主路径未读取。 |

### D. 主尺刻线：投影峰到实测线段

实现：`caliper/main_scale.py::recognize_main_scale`

在主尺 `tick_band` 内，令 `B(y,x)` 为前景掩码，计算 `P(x)=sum_y[B(y,x)>0]` 并归一化。阈值为：

```text
T_main = max(mean(P) + peak_threshold_factor * std(P), 0.02)
```

连续 `P(x) > T_main` 段的中心形成粗候选。每个候选再到二值图测量连续竖直前景段，并以带底部附近的灰度做亚像素 `x_precise` 精修。接缝裁短的主尺线允许沿完整主尺二值图向上恢复**已连通、实际存在**的前景长度。最终按相对间距 `0.45g` 去重，`main_gap` 是最终刻线 `x` 差分的中位数。

| 参数 | 默认值 | 状态 | 算法作用与调节风险 |
| --- | ---: | --- | --- |
| `adaptive_block_size`, `adaptive_C` | `31`, `2` | 条件生效 | 仅主尺复用的 ROI 二值图不可用时，使用此自适应阈值；`C` 更小会留下更多前景。 |
| `peak_threshold_factor` | `0.20` | 生效 | 上式中的标准差系数。降低会增加弱线和噪声候选；提高会漏掉浅刻线。 |
| `min_tick_count` | `3` | 生效 | 少于 3 条直接判主尺检测失败。它是最低可运行条件，不是质量合格线。 |
| `long_tick_factor` | `1.3` | 生效 | `length > median(length)*1.3` 才标为长线，用于 OCR 回退锚点。提高会减少长线候选。 |
| `short_tick_recovery_enabled` | `True` | 生效 | 恢复接缝附近被窄带裁短、但在完整二值图中仍连通的线段。 |
| `short_tick_min_contiguous_ratio` | `0.60` | 生效 | 要求恢复段有足够连续性；降低会更激进地接受碎片。 |
| `short_tick_min_foreground_factor` | `2.00` | 生效 | 恢复段相对于局部前景的最低强度因子；降低会增加噪声恢复。 |
| `short_tick_period_tolerance` | `0.30` | 生效 | 恢复后的 x 位置对实测主尺周期的容差比例。增大可能把非刻线接受为恢复线。 |
| `spacing_refine_enabled` 与 `spacing_*` | 见 `config.py` | 保留 | `utils.refine_ticks_by_spacing` 作为显式标准化/校准研究工具保留，但 `recognize_main_scale` 不调用它；因此这些字段不会影响当前主尺或游标结果。生产规则仍是不补造刻线。 |

### E. 游标刻线窗口、谷底评分与连通域

实现：`caliper/vernier_scale.py::recognize_vernier_scale`

游标阶段先在 `tick_band` 内做二值化和竖直投影，候选谷底是平滑信号低于自适应谷底阈值的连续段。两段谷底 `(L, R)` 之间必须满足：至少有 8 条投影峰、两侧都存在近/远期峰支持、内部没有跨度超过 `1.3p` 的大谷底。对每个通过结构门槛的谷底对，计算：

```text
total_score = 0.30 * valley_score
            + 0.30 * period_clarity
            + 0.25 * spacing_score
            + 0.15 * component_score

component_score = 0.35 * component_support
                + 0.50 * component_structure
                + 0.15 * projection_structure
```

只有 `period_clarity >= 0.20`、`tick_structure >= 0.08`、`total_score >= 0.30` 的候选能进入最终选择。若没有长短连通域结构但 `component_support >= 0.75`，允许作为明确的“均匀刻线”回退。最终范围内的实际候选经过短竖直断裂桥接、竖直开运算、投影与连通域验证以及相对周期去重；**第一条被接受的真实刻线**才是零线。

| 参数 | 默认值 | 状态 | 算法作用与调节风险 |
| --- | ---: | --- | --- |
| `adaptive_block_size`, `adaptive_C` | `31`, `4` | 条件生效 | 仅游标区域无可复用二值图时使用；`C` 更小会保留更多前景。 |
| `tick_band_bottom_pad` | `16` px | 生效 | 将区域分离得到的游标带下缘向下扩展，以免刻线下端被裁短。过大可能引入数字笔画。 |
| `component_vertical_bridge_gap` | `10` px | 生效 | 桥接同一细竖线内部的短空隙。增大可连接断线，也可能把数字与刻线错误连在一起。 |
| `component_vertical_open_height` | `7` px | 生效 | 连通域上的竖直开运算核高。增大更偏向长直线，过大可能漏短线。 |
| `component_fallback_min_height_ratio` | `0.50` | 生效 | 无完整长短结构时，允许的组件最低相对高度。降低会使数字残片更易通过。 |
| `valley_score_depth/period/spacing/component_weight` | `0.30/0.30/0.25/0.15` | 生效 | 上式四项权重，总和为 1。改变某项必须同时检查所有四项和正常样本。 |
| `valley_min_period_clarity`, `valley_min_total_score`, `valley_min_component_structure` | `0.20`, `0.30`, `0.08` | 生效 | 候选进入最终排序前的硬门槛。降低会接纳不稳定范围；提高会导致无谷底结果。 |
| `valley_peak_support_near_periods`, `valley_peak_support_far_periods` | `1.0p`, `2.0p` | 生效 | 谷底两侧检查峰支撑的近/远观察窗口。过短会误拒边缘真实谷底，过长会把远处结构误作支撑。 |
| `valley_internal_break_periods` | `1.3p` | 生效 | 两谷底间允许的最大内部断裂尺度。增大后更容易把两个不连续区间合并。 |
| `valley_score_tie_margin` | `0.02` | 生效 | 仅总分接近时才进入二级排序。增大后更多候选被视为并列。 |
| `valley_preferred_tick_count` | `51` | 生效，仅并列排序 | 只在分数差不超过 `0.02` 时，偏好“已检测数量”更接近 51 的候选。它不要求 51 条，不补线，不改变实际候选数量。 |
| `duplicate_period_ratio` | `0.65p` | 生效 | 距离小于该比例的邻近候选用于去重。提高会合并更多相近响应，过高可能误合并两条真线。 |
| `long_tick_factor`, `long_cluster_min_separation_ratio` | `1.3`, `0.20` | 生效 | 评估游标长短线聚类结构。它们是评分证据，不是生成缺失线的规则。 |
| `recovery_min_observed_tick_count` | `40` | 条件生效 | 局部 ROI 扩边恢复可被采纳时要求的最少实测游标线数。不是识别时强制的 51 条要求。 |

### F. 游标对齐、置信度和歧义门槛

对每条游标线 `v_i`，计算到所有主尺线的最近横向距离：

```text
E_i = min_j |x(v_i) - x(main_j)|
best_index = argmin_i E_i
vernier_scale = 0.02 * best_index
```

`alignment_confidence` 不是总结果置信度。若 `E_best <= 0.5 px`，直接取 `0.95`；否则取最佳线前后两条邻居误差的中位数与 `E_best` 的比值，按 `>=3 / >=2 / >=1.5 / <1.5` 映射到 `0.9 / 0.7 / 0.5 / 0.3`。

歧义阈值不是固定任意像素，而是：

```text
raw = main_gap * 0.002
ambiguity_threshold = clamp(raw, 0.05 px, 0.10 px)
```

只有最佳线的左右相邻、且实际检测到的线中误差最小者，在 `0 <= E_reference-E_best <= ambiguity_threshold` 时才显示参考值。

| 参数 | 默认值 | 状态 | 作用 |
| --- | ---: | --- | --- |
| `align_conf_perfect/strong/moderate/weak/bad` | `0.95/0.9/0.7/0.5/0.3` | 生效 | 对齐误差形状映射出的显示质量档位，不参与读数索引选择。 |
| `align_ambiguity_margin_gap_ratio` | `0.002` | 生效 | 将 `g` 转为原始歧义误差边界。 |
| `align_ambiguity_margin_min_px`, `align_ambiguity_margin_max_px` | `0.05`, `0.10` px | 生效 | 把阈值夹在极窄范围，避免对齐提示泛滥。增大上限会增加参考提示数量，但不增加正式精度。 |

### G. OCR 字符、两位数与主尺合并

实现：`caliper/ocr.py`、`caliper/merger.py`

OCR 裁剪使用真实主尺刻线顶部 `y_top_tick` 和 `g`：

```text
y_top    = y_top_tick - 4g - expand_y
y_bottom = y_top_tick - 1g + expand_y
x_left   = zero_x - 1.7 * (10g)
x_right  = zero_x + 0.4 * (10g)
```

第一次 `expand_y=0`。若没有数字连通域或没有有效 OCR 数字，第二次使用 `expand_y=g`；仍失败才以长刻线顶部作为 OCR 锚点再试。当前主尺读数路径的连通域规则位于 `main_scale.find_digit_cc_candidates`：初始面积范围为 `700..3000 px`，再按裁剪高度动态调整为 `effective_min_area=min(700, max(250, 0.09H_crop^2))` 与 `dynamic_max_area=max(3000, 0.20H_crop^2)`，并要求宽至少 `3 px`、高至少 `5 px`、高宽比在 `0.6..3.5`。这些是代码内的当前算法常量，并非 `OCRConfig.cc_*` 参数。

横向间隔不超过 `max(6, 0.75g)` 的 `1` 与下一字符可组合为 `10` 至 `15`。每个标签绑定到最近主尺刻线，绑定距离不得超过 `max(8 px, 0.45g)`；优先选择零线左侧最近标签，或使用零线右侧相邻标签减一。

| 参数 | 默认值 | 状态 | 算法作用与调节风险 |
| --- | ---: | --- | --- |
| `main_label_group_gap_ratio` | `0.75g` | 生效 | 组合 `1` 和下一位为 `10..15` 的最大字符间隙。过大可能把本不相邻的数字组合。 |
| `projection_strong_factor`、`projection_min_strong`、`cc_*`、`merge_x_gap_ratio`、`pad_*`、`fallback_*` | 见 `config.py` | 保留 | 历史 OCR 全扫描/单点辅助字段，当前没有正式读取点；当前 `merge_readings` 的定向 OCR 使用 `find_digit_cc_candidates` 内的规则，不读取这些字段。 |
| `patch_resize_factor` | `3` | 生效 | OCR 前将小 patch 放大三倍。更大可改善笔画分辨率，也会放大噪声。 |
| `patch_clahe_clip`, `patch_adaptive_C` | `2.5`, `3` | 生效 | 单字符 patch 的增强和二值化常数。主要用于 OCR，不应拿来修刻线问题。 |
| `patch_adaptive_block` | `11` | 保留 | 当前路径按放大后 patch 的实际尺寸动态计算奇数窗口（上限 11），不读取这个配置值；修改它不会改变 OCR 结果。 |
| `tesseract_psm`, `tesseract_whitelist` | `'8'`, `'0123456789'` | 生效 | Tesseract 单字符模式和数字白名单。 |
| `easyocr_allowlist`, `easyocr_min_size`, `easyocr_text_threshold`, `easyocr_low_text`, `easyocr_min_conf` | 数字白名单，`5/0.3/0.2/0.2` | 条件生效 | Tesseract 不可用时的 EasyOCR 参数。提高阈值会减少误认，也会增加空识别。 |

### H. 总质量提示与参数依赖图

总 `confidence` 由 `merger.py::calc_confidence()` 内的固定规则计算：主尺刻线数达到 10 条或 5 条、游标刻线数相对 `1/precision` 的比例、以及主尺间距变异系数小于 0.15 时分别加分，最终上限为 0.95。`MergerConfig.conf_main_tick_min`、`conf_vernier_tick_min` 和 `conf_gap_cv_threshold` 虽然保留在配置类中，但当前没有读取点；修改它们不会改变质量提示，也不会改变 `split_y`、零线、OCR 或正式读数。实际质量提示仍不是标定准确率。

```text
ROI 参数
  -> ROI 图不完整/背景过多才考虑
  -> 区域分离参数
       -> split_y 或 tick_band 错才考虑
       -> 主尺 / 游标刻线参数
            -> 先检查投影与连通域，再决定是否调峰值、谷底或去重
            -> OCR 参数
                 -> 只有 OCR 框和字符证据错误时考虑
            -> 对齐歧义参数
                 -> 只有真实相邻刻线误差近乎并列时考虑
```

也就是说，`align_ambiguity_*` 不能解决零线偏移，`main_label_group_gap_ratio` 不能解决 ROI 裁掉数字，`valley_*` 不能修正区域分离线偏到主尺中间。参数的正确入口由最早异常的可视化阶段决定。

## 读数、歧义与结果字段

结果类型定义在 `caliper/result.py::CaliperResult`：

| 字段 | 单位/类型 | 含义与使用方式 |
| --- | --- | --- |
| `main_scale` | `float`，mm | OCR 与主尺刻线推导出的整数/毫米部分。 |
| `vernier_scale` | `float`，mm | 正式游标小数，始终是 `0.02` 的整数倍。 |
| `total` | `float`，mm | 正式总读数，等于 `main_scale + vernier_scale`。 |
| `precision` | `float`，mm | 当前固定为 `0.02`。 |
| `confidence` | `0.0` 至 `1.0` | 主尺刻线数量、游标刻线覆盖情况和主尺间距均匀性的内部质量提示，不替代人工检查。 |
| `image_annotated` | `numpy.ndarray` | 最终标注图。 |
| `debug_images` | `dict[str, numpy.ndarray]` | 快速或详细模式下生成的中间图。 |
| `extra_info` | `dict` | 零线、OCR 推导、ROI、时间和歧义等诊断信息。 |

`extra_info` 的常用键如下：

| 键 | 说明 |
| --- | --- |
| `main_ticks_count` / `vernier_ticks_count` | 最终实际检测到的刻线数。不是理论刻线数。 |
| `main_gap_px` | 相邻主尺毫米线的像素间距。 |
| `zero_x` | 旋转 ROI 坐标系中的游标零线横坐标。 |
| `main_digits` | OCR 字符及其位置的诊断列表。 |
| `main_derivation` | OCR 文本、置信度、选中标签、推导策略和失败原因。 |
| `alignment_ambiguity` | 无歧义时为 `None`；有歧义时含推荐/参考小数与最终总读数。 |
| `roi_source` / `roi_box_original` | 最终 ROI 的来源和原图坐标。 |
| `roi_recovery` | 局部 ROI 扩边恢复的触发情况、尝试和最终候选。 |
| `timings` | 各阶段耗时，单位毫秒。 |

合并后 `alignment_ambiguity` 还会增加：

```text
primary_total   = main_scale + primary_reading
reference_total = main_scale + reference_reading
```

其中 `primary_total` 与 `total` 表示同一个正式结论；`reference_total` 只在界面和诊断中显示，不能写回正式结果。

## 调试图与失败排查

详细模式会生成下列主要标签页；快速模式通常只保留 ROI 和简化最终标注，避免中间图生成影响速度。

| 标签 | 图中证据 | 优先用于排查的问题 |
| --- | --- | --- |
| `1_ROI定位` | 原图 ROI、候选框和选择范围 | 数字、主尺或游标是否被裁掉；ROI 是否过大。 |
| `0_预处理` | 增强、二值化和前景结构 | 反光、模糊、阈值化后刻线是否消失。 |
| `1b_方向校正` | 校正前后对比 | 卡尺接缝是否仍明显倾斜。 |
| `2_区域分离` | `split_y`、主尺/游标区域和刻线带 | 分割线是否截短主尺或把主尺混入游标。 |
| `3a_主尺刻度线` | 投影候选和实测主尺线 | 主尺漏检、多检、长度测量是否合理。 |
| `3b_主尺数字OCR` | 数字候选框、连通域、OCR 文字和锚点 | OCR 框偏移、多位数字组合或主尺整数推导。 |
| `4b_游标刻度线` | 游标刻线、原始投影、连通域响应、长度标准曲线、谷底范围、零线、连通域 | 谷底范围、零线、数字粘连、断裂刻线、多检和长短刻线结构。 |
| `4c_游标对齐` | 主尺/游标对齐线、最佳线与橙色 `ALT` | 小数对齐是否相邻并列。 |
| `5_最终标注` | 最终主尺、游标、总读数标注 | 汇总检查。 |
| `5b_读数推导` | OCR 锚点、主尺和游标合并关系 | 最终数字为何由该整数与小数组成。 |

“游标刻度线”页不是单独的谷底或连通域页，而是一张纵向合成图。向下滚动可依次看到刻线与原始投影、接缝侧连通域响应、长度标准曲线、谷底选择曲线和连通域证据：绿色通常表示已采用的连通域，橙色表示被拒绝候选，青色表示未匹配连通域。

长度标准曲线只使用最终接受的游标刻线长度做确定性一维两类聚类。两簇均有至少三条线且长度中心相差足够明显时，短线簇绘为 `1.0`、长线簇绘为 `1.5`；不满足条件时明确显示单类，所有线绘为 `1.0`。它只帮助检查“已接受刻线的位置与长短结构”，不参与谷底、零线、刻线筛选、对齐或读数。检查游标零线错误时，应依次确认：谷底对是否夹住真实游标范围、零线前的第一个投影候选是否对应细竖线、数字 `0` 是否与该线粘连、以及该线是否在连通域追踪中被错误过滤。

游标页末尾的“逐刻线校正”面板用于检查相机视角造成的单条刻线横向漂移。算法从每个已观察到的游标候选出发，仅追踪接缝侧开始的细前景笔画；遇到笔画变宽、横向跳变或较长断裂即停止，避免把数字或背景带入。每条有效轨迹以自身的接缝侧中心为锚点独立平移，形成一张只含已追踪细线的校正诊断图。上图的黄色线是各刻线原始中心轨迹，蓝点是每条线独立的接缝锚点；下方灰色曲线是原始投影，黄色曲线是逐线拉直后的投影，绿色和橙色竖线分别表示原始与已追踪候选。该图只用于验证刻线形状与投影，不参与游标候选、谷底、零线、对齐或读数。

推荐排查顺序是：先检查 ROI 是否完整而紧凑；再检查区域分离线和两侧 `tick_band`；随后检查主尺或游标刻线本身；最后检查 OCR 和对齐。不要在 ROI 或区域分离错误时先调整对齐阈值，因为后续模块面对的是已被裁错或混入无关结构的图像。

## Python API

### 直接读取文件

`read_caliper` 支持含中文路径的图像文件读取：

```python
from caliper.pipeline import read_caliper

result = read_caliper('tupian/60.50.jpg')
print(result.main_scale, result.vernier_scale, result.total)
```

该便捷接口使用默认 `CaliperPipeline()`，即 `fast_mode=False`，会产生完整调试图。

### 使用 OpenCV 图像数组

```python
import cv2
import numpy as np

from caliper.pipeline import CaliperPipeline

raw = np.fromfile('tupian/60.50.jpg', dtype=np.uint8)
image = cv2.imdecode(raw, cv2.IMREAD_COLOR)

pipeline = CaliperPipeline(fast_mode=False)
result = pipeline.run(image)

print(f'正式读数: {result.total:.2f} mm')
print('OCR 推导:', result.extra_info['main_derivation'])
print('对齐歧义:', result.extra_info['alignment_ambiguity'])
```

`fast_mode=True` 适用于不需要详细中间图的调用。每次 `run()` 后，`pipeline.step_results` 可用于诊断本次运行的 ROI、分割、主尺和游标原始阶段结果；它是诊断数据，不应作为稳定的长期外部接口。

### 接收进度图

`run()` 接受可选的 `progress_callback(step_key, image, status)`。回调只会在相应阶段已有图像时执行：

```python
def on_progress(step_key, image, status):
    print(step_key, status, image.shape)

pipeline = CaliperPipeline(fast_mode=False)
result = pipeline.run(image, progress_callback=on_progress)
```

## 测试与评估

运行测试前先安装项目依赖及 `pytest`：

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```

离散游标读数和歧义参考值的专项测试：

```powershell
python -m pytest -q tests/test_alignment_ambiguity.py tests/test_vernier_debug_panel.py
```

`tupian/` 中的照片名通常便于提供测试真值，但名称不参与生产识别。已确认的测试标注例外为：`14.80.jpg` 的真值是 `140.80 mm`，`33.00.jpg` 的真值是 `30.30 mm`，`38.30.jpg` 的真值是 `30.84 mm`。

仓库不会提交 `tupian/` 中的本地图片集（当前约 300 MB），也不会提交 `debug_*`、`paper/` 和测试缓存。需要运行依赖真实图片的回归测试时，请在仓库根目录自行准备同名的 `tupian/` 目录；不依赖图片的单元测试可以直接运行。

可用下列命令重跑整套图片评估，并将结果写入指定的评估目录：

```powershell
python tools/evaluate_all_pipeline.py
```

本轮 2026-08-13 审计快照位于 `debug_tupian_batch_evaluation_20260813_research_audit_v2/evaluation.json`：49 张图片全部完成流程，其中 48 张有文件名真值；43/48 张误差不超过 `0.10 mm`，46/48 张误差不超过 `0.50 mm`。`130.70.jpg` 的主尺 OCR 失败并输出 `0.14 mm`，`40.20.jpg` 的区域分离/游标检测失败并输出 `0.00 mm`，`140.00.jpg` 的游标对齐误差为 `0.48 mm`。这些是当前状态的审计记录，不代表算法上限；重新修改代码后必须重新运行评估。

## 标准化曲线（详细模式诊断）

主尺和游标尺都提供统一的 `standardization` 结果结构。它只保存正式流程已经接受的刻线证据，用于曲线显示、问题定位和后续校正研究，不参与 `main_ticks`、`vernier_ticks`、`zero_x`、游标对齐或 `total` 的计算。

```text
standardization
├── version
├── width
├── x_offset
├── curves: raw_projection / support / normalized_response
├── ticks
└── classification: mode / centers / counts / separation / threshold
```

曲线数组使用检测带的局部横坐标，长度等于 `width`；`x_offset` 用于映射回父级旋转 ROI。主尺的支撑来自接缝侧 ±2 像素窗口的最大二值投影；游标尺的支撑来自已匹配连通域的下端 `component_bottom_y`，原始曲线来自游标带 `proj_norm`。游标长度聚类至少需要 6 条有效刻线，两类各至少 3 条且中心差不小于 `max(2 px, 0.20 × 长度中位数)`；否则显示 `single` 或 `unknown`，不会拟合理论曲线或补造固定 51 条刻线。

详细模式中游标标准化对象同时位于 `step_results['vernier']['standardization']` 和 `step_results['vernier']['vernier_band_detection']['standardization']`，UI 直接使用同一对象；快速模式和空检测结果返回 `None`。导出命令如下：

```powershell
python tools/export_standardization_samples.py --input-dir tupian --output-dir debug_tupian_standardization_20260814 --image 30.00.jpg --image 120.60.jpg --image 72.52.jpg --image 130.70.jpg --image 40.20.jpg --image 140.00.jpg
```

输出目录包含每张图的 `*_main_standardization.png`、`*_vernier_standardization.png` 和 `standardization_summary.json`。`40.20.jpg` 的游标曲线为空是其前置区域分离未得到可靠候选的真实结果，工具不会用文件名读数或理论网格填补。

## 限制与使用建议

- 本项目仅适配 `0.02 mm` 游标卡尺；更换分度必须重新设计精度、候选数量和对齐规则，不能只改显示精度。
- 主尺数字必须足够可见。OCR 是主尺整数的重要图像证据；没有数字或数字候选框错误时，不能把零值当成可信读数。
- 强反光、运动模糊、透视严重、刻线被遮挡、数字与刻线大面积粘连、ROI 未覆盖有效结构、区域分割线错误，都可能使后续结果偏差或失败。
- `confidence` 是内部质量提示，不是统计意义上的测量置信区间。数值高也应在关键照片上查看最终标注与详细调试图。
- 出现“对齐歧义”时，正式结果仍满足离散刻度规则；参考值只表达相邻两条真实刻线在像素层面难以区分，适合交由人眼复核。
- 不要以文件名、期望读数或固定 51 条刻线来修正生产结果。任何修复都应能在 ROI、分割、投影、连通域、OCR 或对齐图中找到图像证据。
