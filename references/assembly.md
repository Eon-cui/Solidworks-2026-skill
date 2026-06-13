# 装配体工作流（位姿级，SW2026 修复版）

> 开源版 `AddComponent4/5` 裸插入只给平移 → 姿态全错（V3.6 事故）。本工作流 = 位姿级插入 + 程序化 mate + 位姿级验收。

## 1. 位姿级插入组件

```python
import sys; sys.path.insert(0, r"SKILL_DIR/scripts")
from sw_session import connect, genmod
from sw_assembly import new_assembly, add_component_posed

sw = connect()                      # GetActiveObject 优先
sw.CloseAllDocuments(True)          # 铁律 8: 清场
asm = new_assembly(sw)

# 姿态矩阵: 行约定 p_world = p_local·R + t
IDENT  = [[1,0,0],[0,1,0],[0,0,1]]
AXIS_Z = [[1,0,0],[0,0,1],[0,-1,0]]   # 零件局部 Y → 世界 +Z

LAYOUT = [  # (路径, R, t毫米)
    (r"D:\parts\Base.SLDPRT",    IDENT,  (0, 0, 0)),
    (r"D:\parts\Housing.SLDPRT", AXIS_Z, (40, 115, 6)),
]
for path, R, t in LAYOUT:
    comp = add_component_posed(asm, sw, path, R, t)   # AddComponent5 + Transform2 PUTREF
```

提速技巧：插入前先 `OpenDoc6` 预打开每种零件一次，再 `ActivateDoc3` 回装配。

## 2. 程序化面选择 mate（禁用坐标 SelectByID2）

```python
from sw_mate import get_components, find_cyl_face, find_plane_face, add_concentric, add_coincident, add_lock_group, fix_component

comps = get_components(asm)                       # {Name2: IComponent2(gen_py 包装)}

# 转动副 = 同心(径向) + 平面贴合(轴向)。同心 mate 不锁轴向滑动!
f1 = find_cyl_face(comps["Shaft-1"],   10.95)     # 半径毫米, 零件内唯一半径直接匹配
f2 = find_cyl_face(comps["Housing-1"], 22.0)
add_concentric(asm, f1, f2)                       # err=1 才算成功(内部已查)

p1 = find_plane_face(comps["Shaft-1"],   axis=1, pos_mm=5.0)   # 法向∥局部Y, 根点 y≈5
p2 = find_plane_face(comps["Housing-1"], axis=1, pos_mm=6.0)
add_coincident(asm, p1, p2)

# 螺栓连接的刚性组: LOCK mate 链 (拖动不散架)
add_lock_group(asm, comps, ["Base-1", "Housing-1", "Motor-1", "Cap-1"])

fix_component(asm, comps["Base-1"])               # 接地
```

同半径多孔用 `find_cyl_face_at(comp, r_mm, axis_idx, pos_mm)` 按**局部坐标**区分（CylinderParams 是零件局部系！）。

### 为什么必须程序化

- `SelectByID2("", "FACE", x,y,z)` 是**视线射线拾取** — 选中的是当前视角下投影命中的面，不是 3D 最近面。装配体内必选错
- 正路：`comp.GetBodies3(0,0)` → 解 tuple → `IBody2.GetFaces()` → `ISurface.CylinderParams` 半径匹配 → `IEntity.Select4`
- AddMate5 **同零件两面 → err=0 静默失败**；err=1 = 成功
- 想要"SW 里拖动看运动"：刚性组 LOCK + 关节同心 + 轴向贴合，剩余自由度恰好 = 设计自由度

## 3. 常用 mate 速查（AddMate5 15 参数）

```python
asm_e.AddMate5(type, align, flip, d, dU, dL, gearN, gearD, a, aU, aL, posOnly, lockRot, widthOpt)
# 同心:  (1, 2, False, 0,0,0, 0,0, 0,0,0, False, False, 0)
# 贴合:  (0, 2, False, 0,0,0, 0,0, 0,0,0, False, False, 0)
# 距离:  (5, 2, False, d_m, d_m, d_m, 0,0, 0,0,0, False, False, 0)
# 齿轮:  (6, 2, False, 0,0,0, ratioN, ratioD, 0,0,0, False, False, 0)
# LOCK:  (16, 2, False, 0,0,0, 0,0, 0,0,0, False, False, 0)
# align=2(closest) 让解算器保持当前位置 — 初始位姿已正确时零移动
```

## 4. 位姿级验收（铁律：实例计数 ≠ 验收）

```python
from sw_verify import verify_assembly_poses
# 导出装配 STEP 后:
expected = [(label, R, t_mm) for ...]            # 与 LAYOUT 同源
n_ok, n_all, report = verify_assembly_poses(step_path, expected, tol_mm=0.1, tol_axis=0.01)
assert n_ok == n_all, report
```

原理：装配 STEP 中组件位姿在 `ITEM_DEFINED_TRANSFORMATION` 的**第一个** `AXIS2_PLACEMENT_3D`（第二个是恒等参考系）。每组件比对 origin（±0.1mm）+ Z 轴方向（±0.01）。

加完 mate 后**重导 STEP 复验** — mate 解算可能拉动组件；位姿无漂移才算交付。

## 5. 开源版可继续使用的函数（sw_assembly.py 保留）

`resolve_component` / `get_component_model` / `find_largest_cylinder_face`（零件上下文 + GetCorresponding 映射，适合简单两件配合）/ `add_mate5_checked`（含 err 检查）/ `add_gear_mate_by_cylinders` / `collect_mate_feature_summary`（验证 MateGroup 真实写入）。

多实例同零件、需要精确指定哪个孔时 → 用 `sw_mate.py` 的局部坐标过滤，不要 `find_largest_cylinder_face`。
