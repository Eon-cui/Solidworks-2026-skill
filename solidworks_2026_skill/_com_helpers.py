"""COM helpers — single source of truth for VARIANT wrapping, gen_py dispatch, unit conversion, and safe COM access.
Used by: sw_session, sw_assembly, sw_mate, sw_connect, mcp/server.py
"""
import math
import pythoncom
from win32com.client import VARIANT

# ── SW 类型库常量 ──

SW_TYPELIB = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
DISPID_TRANSFORM2 = 78

# ── VARIANT 工厂 ──

def VN():
    """空对象位 VARIANT (Callout/ExportData) — 裸 None 会 TYPEMISMATCH"""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def VBR():
    """byref int 输出 VARIANT (errors/warnings)"""
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


# ── 单位转换 ──

def mm(value):
    """毫米 -> 米 (SW API 单位)"""
    return value / 1000.0


M = mm  # legacy alias — use mm()


def deg(value):
    """角度 -> 弧度"""
    return value * math.pi / 180.0


# ── COM 安全访问 ──

def _v(x):
    """pywin32 属性/方法歧义兼容 (EditRebuild3/GetTitle 可能是属性)"""
    return x() if callable(x) else x


def get_com_member(obj, attr_name, *args):
    """
    兼容 pywin32 中"同一成员在不同环境下可能是属性也可能是方法"的情况。

    参数:
        obj: COM 对象
        attr_name: 成员名称
        *args: 当成员可调用时传入的参数

    返回:
        成员值或调用结果
    """
    member = getattr(obj, attr_name)
    if args:
        return member(*args)
    try:
        return member() if callable(member) else member
    except Exception as exc:
        message = str(exc)
        if "-2147352573" in message or "找不到成员" in message or "Member not found" in message:
            return member
        raise


safe_get_com_member = get_com_member  # legacy alias — use get_com_member()


# ── gen_py 早绑定 ──

def genmod():
    """gen_py 模块。SW 不支持 GetTypeInfo -> CastTo/EnsureDispatch 全废,
    必须手动包装: genmod().IXxx(obj._oleobj_)"""
    import win32com.client.gencache as gc
    try:
        return gc.GetModuleForTypelib(SW_TYPELIB, 0, 34, 0)
    except Exception:
        gc.MakeModuleForTypelib(SW_TYPELIB, 0, 0, 34)
        return gc.GetModuleForTypelib(SW_TYPELIB, 0, 34, 0)


def early(obj, iface):
    """dynamic dispatch -> early-bound 接口包装。
    用途: MathUtility.CreateTransform / Component2 / FirstFeature 等 dynamic 失败的成员"""
    return getattr(genmod(), iface)(obj._oleobj_)


def put_object_property(com_obj, dispid, value_dispatch):
    """对象属性赋值 — 必须 DISPATCH_PROPERTYPUTREF (makepy 的 put 会"找不到成员")
    例: put_object_property(comp, DISPID_TRANSFORM2, xform)"""
    com_obj._oleobj_.Invoke(dispid, 0, pythoncom.DISPATCH_PROPERTYPUTREF, 0,
                            value_dispatch._oleobj_)


# ── 杂项 ──

def untuple(ret):
    """early-bound 方法 (GetBodies3 等) 返回 (data, info) tuple 的兼容解包"""
    return ret[0] if isinstance(ret, tuple) else ret
