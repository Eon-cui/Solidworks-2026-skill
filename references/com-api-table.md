# SW2026 COM API 状态表（全部实测，2026-06）

> 测试环境：SolidWorks 2026, Python 3.x + pywin32, Windows 11。
> 实测方法：makepy 读真实签名 + 最小复现 + 方向矩阵穷举。**不要凭文档或记忆猜签名。**

## 总表

| API | 状态 | 替代方案 | 坑 |
|-----|:----:|----------|-----|
| `NewDocument` | ✅ | — | 模板路径空/幽灵模板 → 返回 None；glob 兜底搜 `*.prtdot`（见 sw_connect.find_template） |
| `OpenDoc6` | ✅ | — | errors/warnings 必须 `VARIANT(VT_BYREF\|VT_I4, 0)`；early-bound 下传 int 返回 tuple |
| `InsertSketch2` / `CreateLine` / `CreateCircleByRadius` / `Create3PointArc` / `CreateCenterRectangle` | ✅ | — | 坐标单位米 |
| **`CreateSpline`** | ❌ AttributeError | 多段线近似（≤20 齿）；VBA 宏 | |
| `FeatureExtrusion3` | ✅ 23 参数 | — | 23 个参数一个不能多/少 |
| **`FeatureCut3`** | ✅ 26 参数 | — | **铁律 `Flip=False, Dir=False, NormalCut=False`**。`NormalCut=True` 或 `Dir=True` → 静默失败返回 None；`Flip=True` → 反切主体。返回值必查 None。底面草图法向翻转时 Dir=False 朝空气切 → None → 自动重试 Dir=True（sw_part.extrude_cut 已内置） |
| **`FeatureCut4`** | ❌ 全参数组合静默失败 | FeatureCut3 | 调用"成功"但特征不生成 |
| `FeatureCircularPattern2` | ✅ | — | |
| **`FeatureCircularPattern4`** | ❌ 特征选择失败 | FeatureCircularPattern2 / 单草图画全部实体 | |
| `FeatureFillet` | ✅ | — | 选边后 `FeatureFillet(195, r, 0, 0, None, None, None)` |
| `FeatureRevolve2` | ⚠ | — | 20 参数强类型；全参数显式 float/int/bool 转换 |
| `SaveAs4` (.SLDPRT) | ✅ | — | |
| **`SaveAs4` (.STEP)** | ❌ 4KB 空壳 | `Extension.SaveAs` | 返回成功但 STEP 无几何 — 假成功 |
| `Extension.SaveAs` (STEP/STL/DXF/PDF) | ✅ | — | ExportData 位传 `VARIANT(VT_DISPATCH, None)`，errors/warnings 传 VBR；裸 None → TYPEMISMATCH |
| `EditRebuild3` | ⚠ 属性非方法 | `_v()` 包装 | pywin32 下是 bool 属性，裸调 `()` → 'bool' not callable |
| `SelectByID2`（名称选择） | ✅ | — | Callout 位必须 `VARIANT(VT_DISPATCH, None)`（early-bound 下裸 None 也可） |
| **`SelectByID2`（坐标选面）** | ⚠ 视线射线拾取 | 程序化面选择（sw_mate） | 像鼠标点击，非 3D 最近面。零件内勉强可用（点要避开孔区、偏移面中心 20-30%）；**装配体内禁用** |
| `GetSelectedObjectCount3` | ❌ | `GetSelectedObjectCount2(-1)` | |
| **`FirstFeature` / `GetNextFeature`** | ⚠ dynamic ❌ / gen_py ✅ | gen_py 包装后可遍历特征树 | 2026-06-12 实测遍历 MateGroup 成功 |
| `GetMassProperties` | ❌ 类型不匹配 | 包围盒估算 | 所有签名都试过 |
| `SetDisplayMode` | ❌ | 用户手动 | |
| `AddComponent5` | ⚠ 仅平移 | + Transform2 PUTREF | 旋转必须额外设置（见 com-patterns 模式 3） |
| `Component2.Transform2`（写） | ⚠ PUTREF | `Invoke(78, 0, DISPATCH_PROPERTYPUTREF, 0, xf._oleobj_)` | makepy 的 put → "找不到成员" |
| `MathUtility.CreateTransform` | ⚠ dynamic ❌ | gen_py 包装 `IMathUtility` | SW 不支持 GetTypeInfo；CastTo/EnsureDispatch 全废 |
| `AddMate5` | ✅ 15 参数 | — | err=1 成功；**同零件两面 → err=0 静默失败**；errorStatus 传 VBR |
| `GetBodies3` | ⚠ | 解包 tuple | early-bound 返回 `(bodies, info)`；装配组件下 `GetBody()` 常 None |
| `ISurface.CylinderParams` / `PlaneParams` | ✅ | — | **零件局部系坐标**（非世界系）；PlaneParams = [nx,ny,nz, px,py,pz] |
| `IEntity.Select4` | ✅ | — | 程序化面选择的最后一步 |
| `GetComponents` | ⚠ dynamic 枚举失败 | gen_py `IAssemblyDoc` 包装后枚举 ✅ | dynamic 下 "object does not support enumeration" |
| `FixComponent` | ✅ | — | 先 `Component2.Select4(False, None, False)` |
| `Motion CreateMotionStudy/Activate/Calculate` | ⚠ 属性歧义 | callable 检查包装 | |

## 枚举速查

```python
# swMateType_e
COINCIDENT=0  CONCENTRIC=1  PERPENDICULAR=2  PARALLEL=3  TANGENT=4  DISTANCE=5  ANGLE=6  GEAR=10(注: 本项目实测 6 也建出了齿轮配合, 以 AddMate5 返回非 None+复验为准)  LOCK=16
# swDocumentTypes_e:  PART=1  ASSEMBLY=2  DRAWING=3
# OpenDoc6 options:   SILENT=1  READONLY=2
# GetUserPreferenceStringValue 模板键:  PART=8  ASSEMBLY=9  DRAWING=10  (部分版本 24/25/26 为模板目录)
```

## 关键 DISPID

| 接口.成员 | DISPID | 用法 |
|-----------|:------:|------|
| `Component2.Transform2` | 78 | PROPERTYPUTREF 写位姿 |

## SW 类型库

```
GUID: {83A33D31-27C5-11CE-BFD4-00400513BB57}, 版本 (0, 34) 对应 SW2026
tlb:  <SW安装目录>\SOLIDWORKS\sldworks.tlb   (例: D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb)
```
