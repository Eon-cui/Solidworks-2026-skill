# SW 快照复核

> 建模后必拍。deterministic checks 过了不是跳过视觉复核的理由。

## 政策

每个零件/装配体建模完成后**强制**拍快照复核。跳过仅限：
- 纯格式导出（几何未变）
- 生成失败，无有效 artifact 存在

跳过时报原因 + 跑了哪些 deterministic checks。

## SW 实现

```python
from solidworks_2026_skill.sw_snapshot import capture_views

# model = SW 的 IModelDoc2
pngs = capture_views(model, r"D:\out", "Bracket")
# → ["D:\out\Bracket_iso.png", "D:\out\Bracket_opposite.png",
#    "D:\out\Bracket_top.png", "D:\out\Bracket_front.png"]
```

依赖：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple Pillow`

## 角度包

**基础包（所有零件）：**

| 角度 | SW 视图名 | 覆盖 |
|------|----------|------|
| 等轴测 | `*等轴测` (viewID=7) | 前三面 |
| 对侧等轴测 | 手动相机 `dir=(-1,1,-0.8)` | 后三面 — 两个 iso 保证每个面至少出现一次 |
| 顶 | `*上视` | 平面图案/对称 |
| 前 | `*前视` | 侧轮廓 |

**追加（按需）：**
- section view：内腔/壳/盲孔/通道 — `SectionView` API 或手动隐藏部分体
- wireframe：装配体碰撞嫌疑 — `DisplayMode=WIREFRAME`
- transparent：重叠/封闭性可读性 — 透明度设 0.5

## 诊断转换

视觉复核是**诊断手段**，不是**权威验证**。每个视觉可疑 → 转确定性几何检查 → 才能声称验证：

| 视觉可疑 | 几何检查 |
|----------|---------|
| 孔阵列不对称 | `verify_step` 测孔数+半径 |
| 盖子/子件偏移 | `verify_assembly_poses` 测位姿 |
| 加强筋/凸台浮动 | `check_faces` 验面数+连通性 |
| 腔内/盲孔/通道异常 | section review → `verify_step` 测深/通条件 |
| 重复特征不均匀 | `sw_check_interfaces` 测间距/角度 |

## 包大小

- 简单静态件：基础 4 视图够
- 装配体/多体/壳/腔/筋/槽：基础 4 + section(1-2 截面)
- 修复后：只拍受影响的视图

不要循环拍。只有修复改变了可见几何才重拍。

## 输出

最终回复包含：
- 生成的 PNG 路径列表（或跳过原因）
- 支撑视觉发现的 deterministic checks 结果
