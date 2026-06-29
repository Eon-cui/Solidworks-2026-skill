# Allowed APIs & Anti-Patterns

> Phase 0.3+0.4 产出。所有代码修改的约束源。修改 `.py` 前必查此表。

## ✅ Available APIs

| API | Python COM | Notes |
|-----|:----------:|-------|
| NewDocument | ✅ | 模板路径空时 glob 自动查找 gb_part.prtdot |
| InsertSketch2 | ✅ | |
| CreateLine, CreateCircleByRadius, Create3PointArc | ✅ | |
| FeatureExtrusion3 | ✅ | SW2026 推荐 v3 |
| FeatureCut3 | ✅ | **26 参数。铁律: Flip=False, Dir=False, NormalCut=False。返回值必查 None** |
| FeatureCircularPattern2 | ✅ | 降级替代 v4 |
| SaveAs4 (.SLDPRT) | ✅ | |
| Extension.SaveAs (STEP/STL/DXF/PDF) | ✅ | 需 empty VARIANT Dispatch + byref int |
| OpenDoc6 | ✅ | 需 byref VARIANT 包装 errors/warnings |
| EditRebuild3 | ⚠ | pywin32 下是属性非方法，用 `_com_attr(model, 'EditRebuild3')` 调用 |
| SelectByID2 | ⚠ | 坐标拾取=视线射线(鼠标语义)，非 3D 最近面。装配 mate 选面必须程序化 |
| AddComponent5 | ⚠ | 只给平移，旋转必须 Transform2 PUTREF |
| AddMate5 | ⚠ | err=1 成功，err=0 失败(同零件两面) |
| GetBodies3 | ⚠ | early-bound 返回 (bodies, info) tuple |

## ❌ Disabled APIs

| API | Reason | Alternative |
|-----|--------|-------------|
| CreateSpline | Python COM AttributeError | 多段线近似(≤20 齿) / VBA macro |
| FeatureCut4 | 全参数组合静默失败 | FeatureCut3 |
| FeatureCircularPattern4 | 全参数组合静默失败 | FeatureCircularPattern2 / 单草图画全部实体 |
| SaveAs4 (STEP) | 4KB 空壳 | Extension.SaveAs |
| GetMassProperties | 类型不匹配 | 包围盒估算 |
| SetDisplayMode | 不支持 | 用户手动 |

## Anti-Patterns (DO NOT)

1. **不用 FeatureCut4** → 静默失败，用 FeatureCut3
2. **不凭记忆猜 COM 签名** → 先 makepy 读真实签名 (`references/com-patterns.md` 模式 4)
3. **不裸传 None** → VARIANT(VT_DISPATCH, None) 包裹
4. **不坐标选面(装配体)** → 程序化 `GetBodies3→GetFaces→CylinderParams→IEntity.Select4`
5. **不信任控制台 OK** → STEP 几何验收 (`verify_step`)
6. **async 函数不用 time.sleep** → `await asyncio.sleep()`
7. **不重复 solidworks_2026_skill/ 代码到 server.py** → `from solidworks_2026_skill import ...`

## Tool Annotation Mappings

| Tool Category | readOnlyHint | destructiveHint | idempotentHint | openWorldHint |
|---------------|:------------:|:---------------:|:--------------:|:-------------:|
| Default (all tools) | False | True | False | True |
| Query/Verify/View (24 tools) | True | False | True | False |
