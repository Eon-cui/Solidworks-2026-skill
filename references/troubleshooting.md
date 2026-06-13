# 排障手册（27 条踩坑全集 + 开源版合并）

> 按症状查。每条给：症状 → 根因 → 修法。

## A. 调用"成功"但什么都没发生（假成功类）

| 症状 | 根因 | 修法 |
|------|------|------|
| 切除调用返回 None 不抛异常，特征没生成 | FeatureCut3 的 `NormalCut=True` 或 `Dir=True`；或用了 FeatureCut4 | 验证签名（铁律 1）；返回值必查；`sw_part.extrude_cut` |
| 切除把零件主体切没了 | `Flip=True` 反切 | Flip=False |
| 切除朝空气切（底面草图） | 草图法向翻转，Dir=False 方向朝外 | `SW.cut()` 已内置 Dir 自动重试 |
| STEP 导出"成功"但 4KB 空壳 | SaveAs4 STEP 是 COM 层 bug | `Extension.SaveAs` + VARIANT |
| mate 加了 err=0 但配合没生效 | 两个面来自同一零件（选面错误） | 程序化面选择；err=1 才是成功 |
| 装配体实例都在但姿态全错 | AddComponent5 只接受平移 | `add_component_posed`（Transform2 PUTREF） |
| 控制台全 OK 零件却缺孔 | 验收只看了控制台 | 面数追踪 + verify_step（见 verification.md） |

## B. "找不到成员" / AttributeError（dispatch 类）

| 症状 | 根因 | 修法 |
|------|------|------|
| `MathUtility.CreateTransform` 找不到成员 | SW 不支持 GetTypeInfo, dynamic 解析失败 | gen_py 包装 `IMathUtility`（com-patterns 模式 2） |
| `comp.Transform2 = xf` 找不到成员 | 对象属性需要 PUTREF | `Invoke(78, DISPATCH_PROPERTYPUTREF)`（模式 3） |
| `FirstFeature/GetNextFeature` 找不到成员 | dynamic 下不可用 | gen_py 包装后 ✅ |
| `GetComponents` 不支持枚举 | dynamic 返回对象不可迭代 | gen_py `IAssemblyDoc` 包装 |
| `CastTo`/`EnsureDispatch` 失败 | 同上根因 | 永远用 GetModuleForTypelib 手动包装 |
| `CreateSpline` AttributeError | SW2026 Python COM 不暴露 | 多段线近似 / VBA |
| `GetSelectedObjectCount3` AttributeError | 不存在 | `GetSelectedObjectCount2(-1)` |

## C. 类型不匹配 TYPEMISMATCH (-2147352571)

| 症状 | 根因 | 修法 |
|------|------|------|
| OpenDoc6/SaveAs 报 TYPEMISMATCH | byref errors/warnings 裸传 int | `VARIANT(VT_BYREF\|VT_I4, 0)` |
| SaveAs 第 4 参报错 | ExportData 裸 None | `VARIANT(VT_DISPATCH, None)` |
| SelectByID2 报错 | Callout 裸 None（dynamic 下） | `VARIANT(VT_DISPATCH, None)` |
| **同样代码 SW 重启后反而报错** | GetActiveObject 拿到 early-bound 对象 | early 下 byref 传裸 int（返回 tuple 解包）、Callout 传裸 None — 写兼容分支 |
| FeatureRevolve2 第 8 参报错 | 强类型参数隐式转换失败 | 全参数显式 float()/int()/bool() |
| `'bool' object is not callable` | EditRebuild3 等是属性 | `_v()` callable 检查包装 |
| `'tuple' object has no attribute '_oleobj_'` | GetBodies3 early-bound 返回 (bodies, info) | `ret[0] if isinstance(ret, tuple) else ret` |

## D. 选择失败 / 选错

| 症状 | 根因 | 修法 |
|------|------|------|
| SelectByID2 坐标选面返回 False | 点不在实体面上（孔区/边缘/空气） | 偏移面中心 20-30% 选点，避开孔 |
| 装配体内坐标选面选错面 | 视线射线拾取（鼠标语义） | 程序化面选择（sw_mate） |
| 基准面选择失败 | 中英文版名称不同 | 候选名列表 ["前视基准面", "Front Plane"] 依次试 |
| 圆角 0 边选中 | 边坐标不准 | 边中点坐标；append=True mark=1 |

## E. 文档 / 窗口 / 文件

| 症状 | 根因 | 修法 |
|------|------|------|
| NewDocument 返回 None | 模板路径空 / 幽灵模板（注册表指向已删文件） | `os.path.exists` 检查 + glob 兜底搜模板目录 |
| SW 窗口越积越多 | 连续 NewDocument 不关旧的；Dispatch 每次开新实例 | with SW() 模式；GetActiveObject 优先 |
| SaveAs err=1 覆盖失败 | SW 文件锁 | 保存前 `os.remove` 旧文件 / CloseAllDocuments |
| 两个 SW 版本共存 API 行为诡异 | COM 注册表被后装版本覆盖 | 查注册表 LocalServer32 真实绑定；Online Repair 重注册 |
| 重命名 SLDPRT 后装配引用全断 | 文件系统改名不更新内部引用 | SW 内 SaveAs / Pack and Go |

## F. 几何 / 数学

| 症状 | 根因 | 修法 |
|------|------|------|
| 齿轮拉伸变圆饼 | 齿根圆与齿形轮廓重叠，SW 选最简区域 | 不画齿根圆，齿根弧自身闭合 |
| 零件飞出千倍距离 | MathTransform 平移写了毫米 | 平移单位米 |
| 位姿验证 1/N 误报 FAIL | 读了 ITEM_DEFINED_TRANSFORMATION 第二个 placement（恒等系） | 读第一个 |
| 按世界坐标过滤面失败 | CylinderParams/PlaneParams 是零件局部系 | 用局部坐标过滤 |
| 拖动装配体零件飞出 | 同心 mate 不锁轴向 | 转动副 = 同心 + 轴向贴合/距离 |
| verify bbox 圆盘类总 FAIL | 圆周无显式 CARTESIAN_POINT | 用 max_circle 验外径 |

## G. 环境 / 编码

| 症状 | 根因 | 修法 |
|------|------|------|
| print 中文崩 UnicodeEncodeError | Windows GBK 终端 | 每个 .py 前两行 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` |
| 中文路径经 shell 传入变乱码 | shell stdin 走 console code page | Python 内 `os.listdir()` 匹配前缀，不从 shell 传中文 |
| bash heredoc 修补文件 `\n` 匹配失败 | heredoc 吃 `\\n` 转义 | 含反斜杠的字符串用 `chr(92)` 构造，或用编辑器工具 |
| 缺 pywin32/comtypes | 环境未装 | `python -m sw_2026_skill.sw_preflight --yes` |
| 检测不到 SW | 未安装/未注册 COM | 安装后启动一次 SW 完成注册 |

## H. 破案方法论（新坑出现时）

```
怀疑 API → makepy 读真实签名 (com-patterns 模式 4)
        → 写最小复现 (1 测试零件, try/finally QuitDoc)
        → 不行就参数/方向布尔矩阵穷举
        → 成功模式立即封装进 sw_2026_skill/ + 记入本文档
```

诊断"找不到成员"顺序：gen_py 包装 → PUTREF → 才怀疑 API 不存在。
嫌 API 复杂想绕路 = 危险信号，正路通常 3 步内可破。
