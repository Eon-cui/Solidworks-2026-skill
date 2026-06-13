---
name: sw-2026-skill
description: "Use when the user mentions SolidWorks, SW, CAD modeling, part design, assembly, mates, STEP/STL/PDF export, geometric verification, or needs to automate any CAD task on Windows with SolidWorks 2026 installed. Also use when encountering SW COM errors like 'member not found', FeatureCut silent failure, or Transform2 pose issues."
metadata: { "os": ["win32"], "requires": { "anyBins": ["python", "py"], "sw": "SolidWorks 2026 (2024+ 大部分兼容)" } }
---

# SolidWorks 2026 大一统自动化技能

> 本技能由 UR-SEU-2026 机械臂项目全程实战提炼（35+ 零件、32 实例装配体、43 配合全部脚本生成并通过 STEP 几何级验收）。
> 每条规则背后都是一次真实事故。**先读铁律，再写代码。**

## ⚡ 十条铁律（违反任何一条 = 重蹈覆辙）

| # | 铁律 | 为什么 |
|---|------|--------|
| 1 | **切除只用 FeatureCut3**（26 参数），且 `Flip=False, Dir=False, NormalCut=False`；返回值必查 `None` | `NormalCut=True`/`Dir=True` → 调用"成功"但特征不生成（静默失败）；`Flip=True` → 反切掉零件主体。P2 事故：15 孔全丢，控制台全 OK |
| 2 | **FeatureCut4 / FeatureCircularPattern4 / CreateSpline 禁用** | Python COM 下全参数组合静默失败或 AttributeError。降级：FeatureCut3 / FeatureCircularPattern2 / 单草图多实体 / 多段线近似 |
| 3 | **控制台 OK ≠ 特征生效** — 每特征后面数追踪（`GetBodies2→GetFaceCount`），最终验收解析 STEP 几何 | 两次假成功事故的根因。验收强度必须匹配交付物维度：零件=STEP 圆柱面半径分布，装配=位姿矩阵 |
| 4 | **所有 COM 裸 `None`/byref int → VARIANT 包裹** | `VARIANT(VT_DISPATCH, None)` 作 Callout/ExportData；`VARIANT(VT_BYREF\|VT_I4, 0)` 作 errors/warnings。裸传 → DISP_E_TYPEMISMATCH |
| 5 | **"找不到成员"诊断顺序：gen_py 手动包装 → PUTREF → 才怀疑 API 不存在** | SW 不支持 GetTypeInfo → `CastTo`/`EnsureDispatch` 全废。`GetModuleForTypelib(SW_TYPELIB,0,34,0).IXxx(obj._oleobj_)` 能救活 MathUtility/Component2/FirstFeature |
| 6 | **AddComponent5 只给平移** — 旋转必须 Transform2 PUTREF：`comp._oleobj_.Invoke(78, 0, DISPATCH_PROPERTYPUTREF, 0, xf._oleobj_)` | makepy 的 PROPERTYPUT 会"找不到成员"。V3.6 事故：交付了姿态全错的装配体 |
| 7 | **SelectByID2 坐标拾取 = 视线射线**（鼠标语义），非 3D 最近面 — 装配 mate 选面必须程序化：`GetBodies3→GetFaces→CylinderParams 半径匹配→IEntity.Select4` | 坐标选面在装配体内选错面 → mate 加到同零件两面（err=0 静默失败） |
| 8 | **窗口纪律**：开工 `CloseAllDocuments(True)` 清场，临时件 try/finally `QuitDoc`；连接用 `GetActiveObject` 优先（`Dispatch` 每次开新 SW 实例） | 一天调试积压 17 个 SW 实例；文件锁导致 SaveAs err=1 |
| 9 | **pywin32 属性/方法歧义** — `EditRebuild3`/`GetTitle`/`GetProcessID` 可能是属性，裸调 `()` 崩 | 用 `_v(x): return x() if callable(x) else x` 包装 |
| 10 | **单位全是米** — API 长度、MathTransform 平移、草图坐标全部米；用 `mm(50)` 转换 | MathTransform 平移写毫米 → 零件飞出 1000 倍距离 |

补充小坑（写装配必看）：
- AddMate5 同零件两面 → err=0 **静默失败**；err=1 才是成功
- 同心 mate 只锁径向，**轴向滑动自由** — 转动副 = 同心 + 平面贴合/距离 mate
- `CylinderParams`/`PlaneParams` 返回**零件局部系**坐标（非世界系）；PlaneParams = [法向, 根点]
- 装配 STEP 位姿在 `ITEM_DEFINED_TRANSFORMATION` 的**第一个** AXIS2_PLACEMENT_3D（第二个是恒等参考系）
- `GetBodies3` early-bound 返回 `(bodies, info)` tuple，先解包
- SLDPRT 覆盖保存被文件锁挡 → 保存前先删除旧文件或 CloseAllDocuments
- **坐标系 Y-up**（GB 模板默认）：TOP 平面法向 Y，FRONT 法向 Z。`find_plane_face(axis_idx=1)` = Y-up 面。ANSI 模板为 Z-up，需对应调整 axis_idx

## 建模韧性协议

COM 调用失败 / 返回 None 时，按以下顺序处理。**禁止第一步就简化几何设计。**

1. **读错误** — 区分"参数错误" vs "几何不可能" vs "COM 静默失败"
2. **查文档** — `references/com-api-table.md`（是否已知不可用 API）
3. **自动重试** — cut/extrude 已内置方向+Flip 矩阵，不要手工重复
4. **换面选择** — 坐标选面失败（`face()`）→ `find_cyl_face()` / `find_plane_face()` 程序化选面
5. **换基准面** — 面草图失败 → 基准面 + 控制 extrude 方向
6. **诊断几何** — `verify_step()` 查看 STEP 中实际生成了什么（铁律 #3）
7. **最小调整** — 以上全失败，才改几何参数（位置、尺寸），不改拓扑结构

面数追踪（`check_faces`）每条特征必做。控制台 OK ≠ 特征生效。

## 快速开始

```python
import sys; sys.path.insert(0, r"SKILL_DIR/scripts")
from sw_session import SW

with SW("MyPart") as s:                      # 自动: 清场 + 新建零件 + 退出关窗
    s.sketch_on_plane(); s.circle(0, 0, 44); s.exit_sketch()
    s.extrude(6);  s.check_faces("底盘")     # 面数追踪防假成功
    s.sketch_on_face(0, 6, -16, "顶面"); s.circle(0, 0, 10); s.exit_sketch()
    s.cut(6);      s.check_faces("中心孔")   # FeatureCut3 验证签名 + Dir 自动重试
    s.save(r"D:\out", "MyPart")              # SLDPRT + STEP 成对

from sw_verify import verify_step            # 铁律 3: STEP 几何级验收
ok, report = verify_step(r"D:\out\MyPart.STEP", expected_holes=[(5.0, 1, "φ10中心孔")], max_circle=22)
print(report); assert ok
```

> `SW()` 类的草图坐标用**毫米**（内部转米）；底层 `sw_part.py` 函数用**米**。混用前看函数 docstring。

## 模块导航

| 需求 | 脚本 | 参考文档 |
|------|------|----------|
| 环境自检（依赖+SW 安装） | `sw_2026_skill/sw_preflight.py` | `references/troubleshooting.md` |
| 会话管理（with 清场/面数追踪/genmod） | `sw_2026_skill/sw_session.py` | `references/com-patterns.md` |
| 连接/打开/新建/模板查找 | `sw_2026_skill/sw_connect.py` | — |
| 零件建模（草图+特征，修复版） | `sw_2026_skill/sw_part.py` | `references/part-modeling.md` |
| 装配体（位姿级插入 add_component_posed） | `sw_2026_skill/sw_assembly.py` | `references/assembly.md` |
| 配合（程序化面选择 mate） | `sw_2026_skill/sw_mate.py` | `references/assembly.md` |
| 验收（STEP 几何/面数/装配位姿/7D3S） | `sw_2026_skill/sw_verify.py` | `references/verification.md` |
| 跨零件接口交叉校验 | `sw_2026_skill/sw_check_interfaces.py` | `references/verification.md` |
| 导出 STEP/STL/PDF/DXF | `sw_2026_skill/sw_export.py` | — |
| VBA 宏防护（大模型生成宏时） | `sw_2026_skill/sw_macro_guard.py` | — |
| 工程图/运动算例/审查/外观 ⚠未实测 | `sw_2026_skill/_untested/` | `references/upstream/` |
| COM API 哪些能用哪些废 | — | `references/com-api-table.md` |
| COM 调用三件套（VARIANT/gen_py/PUTREF） | — | `references/com-patterns.md` |
| 排障 | — | `references/troubleshooting.md` |
| MCP server（121 tools） | `mcp/server.py` | 下节 |

## MCP 模式 vs 直接调用模式

| 场景 | 用哪个 |
|------|--------|
| AI 客户端（Claude Desktop/Codex/Cursor）交互式操控 SW | **MCP**: `python mcp/server.py`（stdio）。121 tools，单进程持久连接，内置全部验证签名 |
| 批量建模/装配/验收脚本（可重复执行的 build 脚本） | **直接 import sw_2026_skill/**。一个 Python 进程跑完全部操作，避免多进程多 SW 实例 |
| 一次性小操作 | 直接 import；MCP 启动成本不值 |

MCP 启动：`python SKILL_DIR/mcp/server.py`（stdio, 自带入口）。
MCP 关键 tools：`sw_extrude_cut`（FeatureCut3 正确签名）、`sw_asm_add_component_posed`（位姿级插入）、`sw_asm_verify_poses`（STEP 位姿验收）、`sw_count_faces`/`sw_verify_step_geometry`（防假成功）、`sw_close_all_docs`/`sw_quit_doc`（窗口纪律）。

## 已知限制（明确不能做的）

| API / 能力 | 状态 | 替代 |
|-----------|:----:|------|
| CreateSpline | ❌ | 多段线近似（≤20 齿齿轮够用）；VBA 宏走 `sw_macro_guard.py` |
| FeatureCut4 | ❌ | FeatureCut3（`sw_part.extrude_cut`） |
| FeatureCircularPattern4 | ❌ | FeatureCircularPattern2，或单草图画全部实体（更稳） |
| SaveAs4 导出 STEP | ❌ 4KB 空壳 | `Extension.SaveAs` + VARIANT 包裹（`sw_export.py`） |
| GetMassProperties | ❌ 类型不匹配 | 包围盒估算 |
| SetDisplayMode | ❌ | 用户手动 |
| dynamic dispatch 的 MathUtility/Component2/FirstFeature | ❌ | gen_py 手动包装（铁律 5）后全部 ✅ |
| 异型孔向导 HoleWizard5 | ⚠ 未封装 | 普通孔 + 沉孔两步切除 |
| 装配体内 SelectByID2 坐标选面 | ⚠ 不可靠 | `sw_mate.py` 程序化面选择 |

## 工作流纪律（写任何 SW 脚本前自查）

1. 文件前两行：`import sys` + `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`（Windows GBK 终端）
2. 用 `with SW()` 模式？面数追踪了？
3. 特征调用返回值查 `None` 了？
4. 验收解析 STEP 了？（控制台 OK 不算数）
5. 装配位姿用 `add_component_posed` 了？mate 用程序化面选择了？
6. 新 COM 方法先 makepy 读签名（`references/com-patterns.md` 模式 4），不要凭记忆猜参数
