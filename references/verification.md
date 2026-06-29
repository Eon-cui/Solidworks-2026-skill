# 验收体系（防假成功）

> 两次假成功事故的教训：**验收强度必须匹配交付物维度**。控制台 OK 验证的是"调用没抛异常"，不是"几何正确"；实例计数验证的是"零件存在"，不是"位姿正确"。

## Validation Pipeline

现有验证工具串成 6 阶段流水线。**Stage N 失败 → 停止，不跳级。** 每阶段工具和详见见下表，具体实现见后续各节。

| Stage | 做什么 | 工具 | 失败现象 | 详见 |
|:-----:|--------|------|----------|------|
| 0 | 文件有效性 + 面数追踪 | `SW.check_faces()` | 面数不增长 / 文件<100KB | [三层防御](#三层防御建模时) |
| 1 | STEP 圆柱面半径分布 | `verify_step()` | 孔数/孔径不匹配 | [三层防御 L3](#三层防御建模时) |
| 2 | 装配体位姿矩阵 | `verify_assembly_poses()` | origin 偏移>0.1mm / Z轴偏差>0.01 | [装配位姿验证原理](#装配位姿验证原理) |
| 3 | 跨零件接口 PCD/角度/孔径 | `sw_check_interfaces.py` | PCD 不匹配 / 孔数不一致 | [跨零件接口交叉校验](#跨零件接口交叉校验) |
| 4 | 视觉复核 | `SW.snapshot()` → Pillow | 肉眼可见的几何异常 | [snapshot-review.md](snapshot-review.md) |
| 5 | 7D3S 量化评分 | `score_s1()` / `score_s2()` | 评分<24 / 任一维度 0 分 | [7D3S 框架](#7d3s-框架零件级量化验收) |

**使用方式：**

```python
from solidworks_2026_skill.sw_verify import run_validation_pipeline

result = run_validation_pipeline(sldprt_path, step_path, expected_spec)
# → {'stage': 'S2', 'passed': False, 'report': '❌ J1C: 期望 t=(0,78,0) 未匹配'}
```

`expected_spec` 格式见 `run_validation_pipeline` 的 docstring。

## 验收维度对照表（铁律）

| 交付物 | 最低验收 | 工具 |
|--------|----------|------|
| 单特征 | 返回值非 None + 面数增长 | `SW.check_faces()` |
| 零件 | STEP 圆柱面半径分布 vs 设计孔径表 + 外径/包围盒 | `sw_verify.verify_step()` |
| 装配体 | STEP 位姿矩阵（origin ±0.1mm + 轴向 ±0.01）逐组件比对 | `sw_verify.verify_assembly_poses()` |
| 配合 | mate 全部 err=1 + 加 mate 后重导 STEP 复验无漂移 | `sw_mate` + 复验 |
| 跨零件接口 | PCD 直径/角度/孔径配对一致 | `sw_check_interfaces.py` |

**降级交付必须显式声明** — "X 没做到，用 Y 替代了"。默默降级 = 假成功。

## 三层防御（建模时）

```python
# L1: 特征返回值
feat = s.cut(6)            # 内部 None → raise

# L2: 面数追踪
s.check_faces("中心孔")     # GetBodies2→GetFaceCount, 不增长 → raise

# L3: STEP 几何解析 (最终验收)
ok, rpt = verify_step(step, expected_holes=[(r_mm, count, name), ...], max_circle=R)
```

STEP 解析换算规则：
- **1 个通孔/盲孔 = 2 个半圆柱面**（verify_step 内部已 `//2`）
- 1 个圆角 = 1 个圆柱面
- 圆盘外径：用 `max_circle`（CIRCLE 半径最大值）。**bbox 对圆盘类不可靠**（圆周无显式点）
- 凸台/腔被其他特征切分时半圆柱面对数会变（如走线腔被配重舱分段 1→2 对），按实际几何调整期望值

## 7D3S 框架（零件级量化验收）

7 维 × 3 阶段，35 分满分，24 分 PASS，**任一维度 0 分一票否决 REJECT**。

| 维度 | 名称 | 自动化 | 评什么 |
|:----:|------|:------:|--------|
| D1 | 几何完整性 | 🤖 S2 | CLOSED_SHELL + 点数 + 特征可辨识 |
| D2 | 尺寸精度 | 🤖 S2 | 关键尺寸偏差 <0.2mm=5 分 … ≥5mm=0 分 |
| D3 | 轻量化 | 👁 S3 | 无冗余材料 |
| D4 | 文件有效性 | 🤖 S1 | ≥100KB+SW 可开=5 … 不存在=0 |
| D5 | 建模效率 | 🤖 S1 | <10s=5 … >120s=1 |
| D6 | 可重复性 | 🤖 S1 | 3 次生成 MD5 一致=5 |
| D7 | 装配兼容性 | 👁 S3 | 配合面无干涉 |

阶段：S1 文件检查（全自动）→ S2 STEP 解析（全自动）→ S3 人眼评审（截图辅助）。
`sw_verify.score_s1()` / `score_s2()` 提供 S1/S2 自动评分。

## 跨零件接口交叉校验

参数散落在多个 build 脚本时，人工比对不可靠。模式（`sw_check_interfaces.py`）：

```python
from sw_check_interfaces import cyl_axes, hole_centers, pcd_and_angle

axes = cyl_axes("PartA.STEP")                  # [(r, cx,cy,cz, ax,ay,az), ...]
pts  = hole_centers(axes, r_mm=1.75, axis="Y") # 指定半径+轴向的孔心去重
pcd, ang = pcd_and_angle(pts)                  # 节圆直径 + 起始角
assert abs(pcd - 36) < 0.1                     # PartA 输出 PCD36 ↔ PartB 输入 PCD36
```

铁律：**接口检查必须随设计版本同跑**（修改接口尺寸 → build 脚本 + 期望值 + 文档三处同步 → 跑校验）。陈年失配案例：φ22.2 孔从筒身移到端盖后校验脚本 3 个版本没人发现还在查旧零件。

## 装配位姿验证原理

```python
# SW 导出装配 STEP: 每个组件一条 ITEM_DEFINED_TRANSFORMATION
# 引用两个 AXIS2_PLACEMENT_3D: [0]=组件位姿(要读这个!), [1]=恒等参考系
# placement: 第一引用 CARTESIAN_POINT = origin(毫米), 第二引用 DIRECTION = 局部Z轴的世界方向
```

匹配策略：对每个期望 (label, R, t)，在 placement 池中找 origin 距离 <0.1mm 且 Z 轴（R 第三行）偏差 <0.01 的未使用项。

## 视觉确认（S3 辅助）

```python
model.ShowNamedView2("*等轴测", 7); model.ViewZoomtofit2(); model.GraphicsRedraw2()
model.SaveBMP(r"D:\out\preview.bmp", 2400, 1800)   # 高分辨率全景 + PIL 裁剪局部
```

注意 `ViewZoomTo2` 框选坐标不直观，容易拍到空白 — 优先 Zoomtofit + 高分辨率 + 裁剪。
