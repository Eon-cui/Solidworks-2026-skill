# 零件建模工作流（SW2026 修复版）

> 替换开源版工作流。核心差异：FeatureCut3 验证签名、面数追踪、STEP 几何验收、单草图策略。

## 推荐路径：高层 `SW` 类（毫米接口）

```python
from sw_session import SW
from sw_verify import verify_step

with SW("Bracket") as s:               # 清场 → 新建零件 → (退出时关窗)
    # 1. 主体
    s.sketch_on_plane()                # 默认上视基准面 (中英文名自动兼容)
    s.circle(0, 0, 44)                 # (cx, cy, 直径) 毫米
    s.exit_sketch()
    s.extrude(6)
    s.check_faces("底盘")              # 面数必须增长, 否则 raise

    # 2. 在已有面上开草图 — 坐标点必须落在实体面上且避开孔区
    s.sketch_on_face(0, 6, -16, "顶面")  # (x,y,z) 毫米; 偏离面中心选点更稳
    s.circle(0, 0, 10)
    s.exit_sketch()
    s.cut(6)                           # FeatureCut3 验证签名 + Dir 自动重试 + None 必 raise
    s.check_faces("中心孔")

    # 3. 多孔 = 单草图画全部圆 (规避 CircularPattern4 ❌)
    s.sketch_on_face(13, 6, 13, "顶面(孔)")
    s.circle4(13, 3.2)                 # 4 孔 @(±13,±13)
    s.exit_sketch()
    s.cut(through_all=True)
    s.check_faces("4×孔")

    s.save(r"D:\out", "Bracket")       # SLDPRT + STEP 成对, 先删旧文件防文件锁

# 4. 铁律: STEP 几何级验收 (1 孔 = 2 半圆柱面, 已在 verify_step 内换算)
ok, rpt = verify_step(r"D:\out\Bracket.STEP",
                      expected_holes=[(5.0, 1, "φ10"), (1.6, 4, "φ3.2×4")],
                      max_circle=22)   # 盘类零件用最大圆验外径 (bbox 对圆盘不可靠)
print(rpt); assert ok
```

## 底层路径：`sw_part.py` 函数（米接口，开源版修复）

```python
from sw_connect import mm
from sw_part import sketch, sketch_circle, extrude_boss, extrude_cut, circular_pattern

with sketch(model, "Front Plane") as name:
    sketch_circle(model, 0, 0, mm(25))
feat = extrude_boss(model, name, mm(50))
assert feat is not None                # 每个特征都查!

with sketch(model, "Front Plane") as name2:
    sketch_circle(model, 0, 0, mm(5))
feat = extrude_cut(model, name2, mm(50))   # 内部 FeatureCut3 + 警告 None
assert feat is not None
```

修复点 vs 开源版：
- `extrude_cut`: FeatureCut4 → **FeatureCut3 26 参数**（Flip/Dir/NormalCut=False），返回 None 打警告
- `circular_pattern`: FeatureCircularPattern4 → **FeatureCircularPattern2**；但**首选单草图策略**（所有实例画进一个草图，一次拉伸/切除，零阵列依赖）

## 设计纪律

1. **装配拓扑先于零件设计** — 先写装配顺序（什么件从什么方向装入、卡在哪），再画零件。V2 项目 3 轮返工的教训
2. **FDM 打印公差**：孔 +0.2，轴 -0.1，压入过盈 +0.2（`sw_session.FIT_HOLE/FIT_SHAFT`）
3. **草图必须闭合**且轮廓不重叠 — 重叠区域 SW 选最简单的闭合区拉伸（齿轮变圆饼事故）
4. **坐标选面要避开孔**且偏离面中心 — 面中心可能恰好是孔；选点偏移面宽 20-30%
5. 参数散落 ≥3 处（build 脚本/校验期望值/文档）→ 写交叉校验脚本（`sw_check_interfaces.py` 模式）

## 已知废 API 的替代

| 想做什么 | 别用 | 用这个 |
|----------|------|--------|
| 切除 | FeatureCut4 | `SW.cut()` / `sw_part.extrude_cut` |
| 圆周阵列 | FeatureCircularPattern4 | 单草图画全部 / FeatureCircularPattern2 |
| 样条（渐开线齿形） | CreateSpline | 多段线近似 ≤20 齿；VBA 宏（sw_macro_guard） |
| 质量属性 | GetMassProperties | STEP 包围盒 + 密度手算 |
