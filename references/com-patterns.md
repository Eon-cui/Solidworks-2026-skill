# COM 调用模式四件套（SW2026 实测）

> "找不到成员"/TYPEMISMATCH 时按本文档顺序排查。诊断顺序：**VARIANT 包裹 → gen_py 包装 → PUTREF → 才怀疑 API 不存在**。

## 模式 1：VARIANT 全包裹

任何给 SW COM 的"可选对象"参数（Callout/ExportData）和 byref 输出参数（errors/warnings），裸传 `None`/`0` → DISP_E_TYPEMISMATCH (-2147352571)。

```python
import pythoncom
from win32com.client import VARIANT

VN  = lambda: VARIANT(pythoncom.VT_DISPATCH, None)            # 空对象位
VBR = lambda: VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0) # byref int 输出

ext.SelectByID2(name, "PLANE", 0, 0, 0, False, 0, VN(), 0)
ext.SaveAs(path, 0, 1, VN(), VBR(), VBR())
model = sw.OpenDoc6(path, 1, 0, "", VBR(), VBR())
```

⚠ **early-bound 反转**：SW 重启后 `GetActiveObject` 可能拿到 early-bound 对象，此时 byref 参数要传**裸 int**（返回值变 tuple），Callout 传裸 `None`。兼容写法：

```python
ret = sw.OpenDoc6(path, 2, 0, "", 0, 0)
model = ret[0] if isinstance(ret, tuple) else ret
```

## 模式 2：gen_py 手动包装（dynamic dispatch "找不到成员"时）

SW 不支持 `GetTypeInfo` → `win32com.client.CastTo` / `gencache.EnsureDispatch` **全部失败**。唯一正路：

```python
import win32com.client.gencache as gc
SW_TYPELIB = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
MOD = gc.GetModuleForTypelib(SW_TYPELIB, 0, 34, 0)   # SW2026 = 版本(0,34)

mu   = MOD.IMathUtility(sw.GetMathUtility()._oleobj_)   # CreateTransform 复活
ce   = MOD.IComponent2(comp._oleobj_)                   # Name2/GetBodies3 复活
asm_e= MOD.IAssemblyDoc(model._oleobj_)                 # GetComponents 枚举复活
fe   = MOD.IFace2(face._oleobj_)
se   = MOD.ISurface(fe.GetSurface()._oleobj_)
```

首次使用前生成 gen_py 模块（一次性）：

```python
import pythoncom
from win32com.client import gencache
tlb = pythoncom.LoadTypeLib(r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb")
gencache.MakeModuleForTypelib(SW_TYPELIB, 0, 0, 34)
# 生成后可在 gen_py 目录直接搜 "def FeatureCut3" 读真实签名+参数名
```

## 模式 3：PUTREF 对象属性赋值（makepy put 失败时）

对象类型的属性（如 `Component2.Transform2`）用 makepy 的 PROPERTYPUT 赋值 → "找不到成员"。必须 PUTREF：

```python
import pythoncom
DISPID_TRANSFORM2 = 78
comp._oleobj_.Invoke(DISPID_TRANSFORM2, 0, pythoncom.DISPATCH_PROPERTYPUTREF, 0, xform._oleobj_)
```

通用封装见 `sw_session.put_object_property(com_obj, dispid, value_dispatch)`。

## 模式 4：makepy 读真实签名（参数不确定时）

盲试参数个数不可靠 — "不报错"的组合可能语义错位（FeatureCut3 的 P2 事故根因）。

```bash
# gen_py 模块生成后（模式 2），在其目录搜方法名:
# C:\Users\<u>\AppData\Local\Temp\gen_py\3.x\83A33D31-...\
grep -rn "def FeatureCut3" <gen_py目录>
```

读出参数名后做**最小复现**（1 个测试零件、try/finally QuitDoc），方向类布尔参数做矩阵穷举，确认每个语义，再用于生产。

## 模式 5：pywin32 属性/方法歧义

`EditRebuild3`/`GetTitle`/`GetProcessID`/`GetFaceCount` 等在 pywin32 下可能解析为属性值：

```python
def _v(x):
    return x() if callable(x) else x

_v(model.EditRebuild3)        # 而不是 model.EditRebuild3()
title = _v(model.GetTitle)
```

## MathTransform 约定（装配位姿）

16 元素**行约定**数组，平移单位**米**：

```
[r11, r12, r13,  r21, r22, r23,  r31, r32, r33,  tx, ty, tz,  scale=1.0,  0, 0, 0]
p_world = p_local · R + t      # 行向量左乘
```

```python
arr = [*R[0], *R[1], *R[2], tx_m, ty_m, tz_m, 1.0, 0.0, 0.0, 0.0]
xf = mu.CreateTransform(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in arr]))
```

完整封装：`sw_assembly.add_component_posed(asm, sw, path, R_rows, t_mm)`。
