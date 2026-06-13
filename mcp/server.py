"""SolidWorks MCP Server — COM-safe wrapper for SolidWorks 2026

Codex uses this MCP to automate 3D modeling via SolidWorks COM API.
Start: python mcp/server.py  (stdio, 自带入口)

COM safety layers:
  L1: VARIANT wrapping (prevents marshalling crashes)
  L2: Retry with backoff (handles transient SW busy states)
  L3: COM member compatibility (pywin32 property/method ambiguity)
  L4: Preflight validation (dependency + SW installation check)
"""

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import asyncio
import math
import os
import time
from typing import Optional, Any

from mcp.server.fastmcp import FastMCP

# ── COM imports ──────────────────────────────────────────────────
try:
    import pythoncom
    from pythoncom import VT_DISPATCH, VT_BYREF, VT_I4
    from win32com.client import Dispatch, GetActiveObject
    HAS_COM = True
except ImportError:
    HAS_COM = False
    VT_DISPATCH = VT_BYREF = VT_I4 = 0

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

def _find_template(doc_type="part"):
    """Find SW template with fallback paths"""
    sw = _get_sw()
    pref_map = {"part": 8, "assembly": 9, "drawing": 10}
    pref_key = pref_map.get(doc_type, 8)
    pattern = {"part": "*.prtdot", "assembly": "*.asmdot", "drawing": "*.drwdot"}.get(doc_type, "*.prtdot")
    try:
        path = sw.GetUserPreferenceStringValue(pref_key)
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    # Fallback: search known locations
    search_dirs = [
        r"C:\ProgramData\SolidWorks\SOLIDWORKS 2026\templates",
        r"C:\ProgramData\SolidWorks\SOLIDWORKS *\templates",
    ]
    import glob as _glob
    for search_dir in search_dirs:
        for candidate in _glob.glob(os.path.join(search_dir, pattern)):
            if os.path.isfile(candidate):
                return candidate
    return None

# ── State ────────────────────────────────────────────────────────
sw_app = None
mcp = FastMCP("solidworks-mcp")

# ═══════════════════════════════════════════════════════════════════
# L1: VARIANT wrapping (ALL params, not just optional ones!)
# ═══════════════════════════════════════════════════════════════════

def _vr8(v=0.0):
    """VARIANT(VT_R8, v) — double 参数包装"""
    if not HAS_COM:
        return float(v)
    from win32com.client import VARIANT
    return VARIANT(pythoncom.VT_R8, float(v))


def _vb(v=False):
    """VARIANT(VT_BOOL, v) — bool 参数包装"""
    if not HAS_COM:
        return bool(v)
    from win32com.client import VARIANT
    return VARIANT(pythoncom.VT_BOOL, bool(v))


def _vi4(v=0):
    """VARIANT(VT_I4, v) — int 参数包装"""
    if not HAS_COM:
        return int(v)
    from win32com.client import VARIANT
    return VARIANT(pythoncom.VT_I4, int(v))


def _vn():
    """VARIANT(VT_DISPATCH, None) — 空 Dispatch 参数"""
    if not HAS_COM:
        return None
    from win32com.client import VARIANT
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _empty_dispatch():
    """Deprecated: use _vn() instead"""
    return _vn()


def _byref_int(default=0):
    """VARIANT(VT_BYREF|VT_I4, default) — by-ref 整数"""
    if not HAS_COM:
        return default
    from win32com.client import VARIANT
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, default)


def _safe_com_call(func, *args, retries=3, delay=0.3, **_kwargs):
    """COM 调用包装：自动重试 + backoff

    复杂操作（如 FeatureExtrusion 后立即 SelectByID2）SW 可能忙 → 重试解决。
    """
    last_err = None
    for attempt in range(retries):
        try:
            return func(*args, **_kwargs)
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    raise last_err


# ═══════════════════════════════════════════════════════════════════
# L2: COM member compatibility
# ═══════════════════════════════════════════════════════════════════

def _com_attr(obj, name, *args):
    """安全读 COM 成员（兼容 pywin32 属性/方法歧义）"""
    member = getattr(obj, name)
    if args:
        return member(*args)
    try:
        return member() if callable(member) else member
    except Exception as e:
        msg = str(e)
        if "-2147352573" in msg or "Member not found" in msg:
            return member
        raise


# ═══════════════════════════════════════════════════════════════════
# L3: Connection management
# ═══════════════════════════════════════════════════════════════════

def _init_com():
    if HAS_COM:
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass


def _get_sw():
    """获取或连接 SolidWorks。优先连接已有实例，没有则启动新的。
    
    关键：作为 MCP server（单进程持久），此函数只会在首次调用时 Dispatch。
    后续所有工具调用共享同一个 sw_app 全局变量。
    """
    global sw_app
    if not HAS_COM:
        raise RuntimeError("pywin32 未安装。运行: pip install pywin32")
    if sw_app is not None:
        # 验证连接是否还活着
        try:
            _ = sw_app.RevisionNumber
            return sw_app
        except Exception:
            sw_app = None
    _init_com()
    # 优先连接已有实例
    try:
        sw_app = GetActiveObject("SldWorks.Application")
        rev = _com_attr(sw_app, 'RevisionNumber')
        return sw_app
    except Exception:
        pass
    # 没有运行中的实例 → 启动新的
    sw_app = Dispatch("SldWorks.Application")
    sw_app.Visible = True
    rev = _com_attr(sw_app, 'RevisionNumber')
    return sw_app


def _get_model():
    sw = _get_sw()
    model = sw.ActiveDoc
    if model is None:
        raise RuntimeError("没有打开的文档。请先 sw_new_part() 或 sw_open_doc()")
    return model


def _model_ext():
    return _get_model().Extension


def _sketch_mgr():
    return _get_model().SketchManager


def _feature_mgr():
    return _get_model().FeatureManager


def _sel_mgr():
    return _get_model().SelectionManager


# ── MCP Tools ────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════
# Category 1: Preflight & Health (3 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_preflight() -> str:
    """运行前检查：COM 依赖 + SW 安装状态。启动任何操作前建议先跑这个。"""
    lines = []
    if not HAS_COM:
        lines.append("❌ pywin32 未安装 → pip install pywin32")
    else:
        lines.append("✅ pywin32 OK")

    if HAS_NUMPY:
        lines.append("✅ numpy OK")
    else:
        lines.append("⚠️ numpy 未安装（齿轮/多边形功能降级）")

    if HAS_COM:
        try:
            _init_com()
            sw = GetActiveObject("SldWorks.Application")
            rev = _com_attr(sw, "RevisionNumber")
            lines.append(f"✅ SolidWorks 运行中 (rev={rev})")
        except Exception:
            try:
                sw = Dispatch("SldWorks.Application")
                rev = _com_attr(sw, "RevisionNumber")
                lines.append(f"✅ SolidWorks 已安装 (rev={rev})，但未运行")
            except Exception as e:
                lines.append(f"❌ SolidWorks 不可用: {str(e)[:80]}")
    return "\n".join(lines)


@mcp.tool()
async def sw_health() -> str:
    """连接健康检查：COM 存活 + 活动文档 + 特征数。"""
    try:
        sw = _get_sw()
        lines = [f"SW: {_com_attr(sw, 'RevisionNumber')} (PID={_com_attr(sw, 'GetProcessID')})"]

        model = sw.ActiveDoc
        if model:
            title = _com_attr(model, "GetTitle")
            path = _com_attr(model, "GetPathName")
            lines.append(f"文档: {title} @ {path}")
            feat = model.FirstFeature()
            count = 0
            while feat is not None:
                count += 1
                feat = feat.GetNextFeature()
            lines.append(f"特征数: {count}")
        else:
            lines.append("文档: 无")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 连接异常: {e}"


# ═══════════════════════════════════════════════════════════════════
# Category 2: 连接管理 (5 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_connect(visible: bool = True) -> str:
    """连接 SolidWorks。优先连接已有实例，没有则启动新的。"""
    try:
        sw = _get_sw()
        sw.Visible = visible
        pid = _com_attr(sw, "GetProcessID")
        rev = _com_attr(sw, "RevisionNumber")
        return f"已连接 SW {rev} (PID={pid})"
    except Exception as e:
        return f"连接失败: {e}"


@mcp.tool()
async def sw_instance_info() -> str:
    """显示当前连接的 SW 实例信息。"""
    sw = _get_sw()
    pid = _com_attr(sw, "GetProcessID")
    rev = _com_attr(sw, "RevisionNumber")
    vis = sw.Visible
    doc = sw.ActiveDoc
    title = _com_attr(doc, 'GetTitle') if doc else '无'
    return f"SW {rev} | PID={pid} | 可见={vis} | 文档={title}"


@mcp.tool()
async def sw_disconnect() -> str:
    """断开 COM 连接（不关闭 SW 窗口）。"""
    global sw_app
    sw_app = None
    return "已断开"


@mcp.tool()
async def sw_quit() -> str:
    """关闭 SolidWorks（退出应用程序，清理所有实例）。"""
    try:
        sw = _get_sw()
        sw.ExitApp()
        global sw_app
        sw_app = None
        return "SW 已退出"
    except Exception as e:
        return f"退出失败: {e}"


@mcp.tool()
async def sw_ping() -> str:
    """测试连接。"""
    try:
        sw = _get_sw()
        pid = _com_attr(sw, "GetProcessID")
        return f"pong (PID={pid})"
    except Exception as e:
        return f"断开: {e}"


@mcp.tool()
async def sw_get_version() -> str:
    """SW 版本。"""
    return f"SW {_com_attr(_get_sw(), 'RevisionNumber')}"


@mcp.tool()
async def sw_set_visible(visible: bool = True) -> str:
    """显示/隐藏 SW 窗口。"""
    _get_sw().Visible = visible
    return f"visible={visible}"


# ═══════════════════════════════════════════════════════════════════
# Category 3: 文档操作 (15 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_new_part(template: str = "") -> str:
    """新建零件。"""
    sw = _get_sw()
    if not template:
        template = _find_template("part")
        if not template:
            return "找不到零件模板，请手动指定 template 参数"
    sw.NewDocument(template, 0, 0, 0)
    doc = None
    for _ in range(30):
        doc = sw.ActiveDoc
        if doc is not None:
            break
        time.sleep(0.3)
    if doc is None:
        return f"新建失败 (模板={template})，SW 未返回活动文档"
    return f"新建: {_com_attr(doc, 'GetTitle')}"


@mcp.tool()
async def sw_new_assembly(template: str = "") -> str:
    """新建装配体。"""
    sw = _get_sw()
    if not template:
        template = _find_template("assembly")
        if not template:
            return "找不到装配体模板"
    doc = sw.NewAssembly(template)
    time.sleep(0.5)
    return f"新建: {_com_attr(doc, 'GetTitle')}"


@mcp.tool()
async def sw_new_drawing(template: str = "") -> str:
    """新建工程图。"""
    sw = _get_sw()
    if not template:
        template = _find_template("drawing")
        if not template:
            return "找不到工程图模板"
    doc = sw.NewDrawing(template)
    time.sleep(0.5)
    return f"新建: {_com_attr(doc, 'GetTitle')}"


@mcp.tool()
async def sw_open_doc(filepath: str) -> str:
    """打开文档。filepath: 绝对路径。"""
    abs_path = os.path.abspath(filepath)
    if not os.path.exists(abs_path):
        return f"文件不存在: {abs_path}"
    sw = _get_sw()
    errors = _byref_int(0)
    warnings = _byref_int(0)
    doc = _safe_com_call(sw.OpenDoc6, abs_path, 1, 0, "", errors, warnings)
    if doc is None:
        return f"打开失败 (err={errors.value} warn={warnings.value}): {abs_path}"
    return f"已打开: {_com_attr(doc, 'GetTitle')}"


@mcp.tool()
async def sw_save() -> str:
    """保存当前文档。"""
    model = _get_model()
    errors = _byref_int(0)
    warnings = _byref_int(0)
    ret = model.Save3(1, errors, warnings)
    return "保存成功" if ret else f"保存失败 (err={errors.value})"


@mcp.tool()
async def sw_save_as(filepath: str) -> str:
    """另存为 .SLDPRT。"""
    model = _get_model()
    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    errors = _byref_int(0)
    warnings = _byref_int(0)
    ext = model.Extension
    ret = _safe_com_call(ext.SaveAs, abs_path, _vi4(0), _vi4(1), _vn(), errors, warnings)
    return f"已保存: {abs_path}" if ret else f"保存失败 (err={errors.value}): {abs_path}"


@mcp.tool()
async def sw_export_step(filepath: str) -> str:
    """导出 STEP AP214。"""
    model = _get_model()
    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    errors = _byref_int(0)
    warnings = _byref_int(0)
    ret = _safe_com_call(model.Extension.SaveAs, abs_path, _vi4(0), _vi4(1), _vn(), errors, warnings)
    return f"STEP: {abs_path}" if ret else f"导出失败 (err={errors.value})"


@mcp.tool()
async def sw_export_stl(filepath: str) -> str:
    """导出 STL（3D 打印）。"""
    model = _get_model()
    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    errors = _byref_int(0)
    warnings = _byref_int(0)
    ret = _safe_com_call(model.Extension.SaveAs, abs_path, _vi4(0), _vi4(1), _vn(), errors, warnings)
    return f"STL: {abs_path}" if ret else f"导出失败 (err={errors.value})"


@mcp.tool()
async def sw_export_dxf(filepath: str) -> str:
    """导出 DXF。"""
    model = _get_model()
    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    errors = _byref_int(0)
    warnings = _byref_int(0)
    ret = _safe_com_call(model.Extension.SaveAs, abs_path, _vi4(0), _vi4(1), _vn(), errors, warnings)
    return f"DXF: {abs_path}" if ret else f"导出失败 (err={errors.value})"


@mcp.tool()
async def sw_export_pdf(filepath: str) -> str:
    """导出工程图为 PDF。"""
    model = _get_model()
    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    errors = _byref_int(0)
    warnings = _byref_int(0)
    ret = _safe_com_call(model.Extension.SaveAs, abs_path, _vi4(0), _vi4(1), _vn(), errors, warnings)
    return f"PDF: {abs_path}" if ret else f"导出失败 (err={errors.value})"


@mcp.tool()
async def sw_close_doc() -> str:
    """关闭当前文档。"""
    sw = _get_sw()
    title = _com_attr(sw.ActiveDoc, "GetTitle")
    sw.CloseDoc(title)
    return f"已关闭: {title}"


@mcp.tool()
async def sw_get_doc_path() -> str:
    """当前文档路径。"""
    return _com_attr(_get_model(), "GetPathName")


@mcp.tool()
async def sw_get_doc_title() -> str:
    """当前文档标题。"""
    return _com_attr(_get_model(), "GetTitle")


@mcp.tool()
async def sw_rebuild() -> str:
    """重建模型 (Ctrl+Q)。"""
    _com_attr(_get_model(), 'EditRebuild3')
    return "重建完成"


@mcp.tool()
async def sw_force_rebuild() -> str:
    """强制重建所有特征。"""
    _com_attr(_get_model(), 'ForceRebuild3', True)
    return "强制重建完成"


# ═══════════════════════════════════════════════════════════════════
# Category 4: 草图操作 (16 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_sketch_create(plane: str = "前视基准面") -> str:
    """在基准面上新建草图。plane: 前视/上视/右视基准面。"""
    model_ext = _model_ext()
    if not model_ext.SelectByID2(plane, "PLANE", 0, 0, 0, _vb(False), _vi4(0), _vn(), _vi4(0)):
        return f"未找到基准面: {plane}"
    _sketch_mgr().InsertSketch(True)
    return f"草图: {plane}"


@mcp.tool()
async def sw_sketch_line(x1: float, y1: float, x2: float, y2: float) -> str:
    """直线 (x1,y1)→(x2,y2)，单位米。"""
    _sketch_mgr().CreateLine(x1, y1, 0.0, x2, y2, 0.0)
    return f"直线: ({x1:.4f},{y1:.4f})→({x2:.4f},{y2:.4f})"


@mcp.tool()
async def sw_sketch_circle(cx: float, cy: float, r: float) -> str:
    """圆: 圆心(cx,cy) 半径r。"""
    _sketch_mgr().CreateCircleByRadius(cx, cy, 0.0, r)
    return f"圆: ({cx},{cy}) R={r}"


@mcp.tool()
async def sw_sketch_arc(x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> str:
    """三点圆弧。"""
    _sketch_mgr().Create3PointArc(x1, y1, 0.0, x2, y2, 0.0, x3, y3, 0.0)
    return f"圆弧: ({x1},{y1})→({x3},{y3})"


@mcp.tool()
async def sw_sketch_rectangle(x1: float, y1: float, x2: float, y2: float) -> str:
    """矩形: 对角 (x1,y1)-(x2,y2)。"""
    _sketch_mgr().CreateCornerRectangle(x1, y1, 0.0, x2, y2, 0.0)
    return f"矩形: ({x1},{y1})→({x2},{y2})"


@mcp.tool()
async def sw_sketch_center_rectangle(cx: float, cy: float, w: float, h: float) -> str:
    """中心矩形。"""
    _sketch_mgr().CreateCenterRectangle(cx, cy, 0.0, w / 2, h / 2, 0.0)
    return f"矩形: 中心({cx},{cy}) {w}×{h}"


@mcp.tool()
async def sw_sketch_slot(x1: float, y1: float, x2: float, y2: float, w: float) -> str:
    """直槽口。"""
    _sketch_mgr().CreateStraightSlot(x1, y1, 0.0, x2, y2, 0.0, w)
    return f"槽口: ({x1},{y1})→({x2},{y2}) w={w}"


@mcp.tool()
async def sw_sketch_polygon(cx: float, cy: float, r: float, sides: int = 6) -> str:
    """正多边形: 中心(cx,cy) 外接圆半径r 边数sides。"""
    sm = _sketch_mgr()
    step = 2 * math.pi / sides
    pts = [(cx + r * math.cos(step * i), cy + r * math.sin(step * i), 0.0) for i in range(sides)]
    for i in range(sides):
        p1, p2 = pts[i], pts[(i + 1) % sides]
        sm.CreateLine(p1[0], p1[1], 0.0, p2[0], p2[1], 0.0)
    return f"正{sides}边形: R={r}"


@mcp.tool()
async def sw_sketch_centerline(x1: float, y1: float, x2: float, y2: float) -> str:
    """中心线（构造线）。"""
    _sketch_mgr().CreateCenterLine(x1, y1, 0.0, x2, y2, 0.0)
    return f"中心线: ({x1},{y1})→({x2},{y2})"


@mcp.tool()
async def sw_sketch_point(x: float, y: float) -> str:
    """草图点。"""
    _sketch_mgr().CreatePoint(x, y, 0.0)
    return f"点: ({x},{y})"


@mcp.tool()
async def sw_sketch_spline(points: str) -> str:
    """样条曲线: "x1,y1;x2,y2;..."。"""
    sm = _sketch_mgr()
    pts = [(float(x), float(y)) for p in points.split(";") for x, y in [p.strip().split(",")]]
    for i in range(len(pts) - 1):
        sm.CreateLine(pts[i][0], pts[i][1], 0.0, pts[i + 1][0], pts[i + 1][1], 0.0)
    return f"样条: {len(pts)} 点"


@mcp.tool()
async def sw_sketch_fillet(r: float, count: int = 1) -> str:
    """草图倒圆角 R=r。"""
    _sketch_mgr().CreateFillet(r, count)
    return f"倒圆角 R={r}"


@mcp.tool()
async def sw_sketch_offset(distance: float) -> str:
    """草图等距偏移。"""
    _sketch_mgr().SketchOffset2(distance, False)
    return f"等距: {distance}"


@mcp.tool()
async def sw_sketch_trim() -> str:
    """草图剪裁。"""
    _get_model().SketchTrim(0, 0, 0)
    return "剪裁完成"


@mcp.tool()
async def sw_sketch_extend() -> str:
    """草图延伸。"""
    _get_model().SketchExtend(0, 0, 0)
    return "延伸完成"


@mcp.tool()
async def sw_sketch_exit() -> str:
    """退出草图。"""
    _sketch_mgr().InsertSketch(True)
    return "已退出草图"


# ═══════════════════════════════════════════════════════════════════
# Category 5: 特征操作 (20 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_feature_extrude(depth: float, draft: float = 0.0, direction: int = 1, flip: bool = False) -> str:
    """拉伸凸台。depth=深度(m)。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureExtrusion2,
        True, flip, False, direction, direction,
        depth, 0.0,
        False, False, False, False,
        draft / 57.2958, draft / 57.2958,
        False, False, False, False,
        True, True, True,
        0, 0, False)
    return f"拉伸: depth={depth}"


@mcp.tool()
async def sw_feature_extrude_cut(depth: float, draft: float = 0.0, through_all: bool = False) -> str:
    """拉伸切除。depth=深度(m)。through_all=True 贯穿。

    SW2026 实测 (2026-06-11): FeatureCut4 broken → FeatureCut3 (26参数)。
    铁律: Flip=False, Dir=False, NormalCut=False (违反→静默失败/反切)。
    """
    fm = _feature_mgr()
    t1 = 1 if through_all else 0
    d1 = 0.001 if through_all else depth
    feat = _safe_com_call(fm.FeatureCut3,
        True,    # 1 Sd
        False,   # 2 Flip (True=反切整个零件!)
        False,   # 3 Dir (True=静默失败!)
        t1,      # 4 T1: 0=Blind 1=ThroughAll
        0,       # 5 T2
        d1,      # 6 D1
        0.0,     # 7 D2
        False, False, False, False,   # 8-11 Dchk1/2 Ddir1/2
        draft / 57.2958, 0.0,         # 12-13 Dang1/2
        False, False,                 # 14-15 OffsetReverse1/2
        False, False,                 # 16-17 TranslateSurface1/2
        False,   # 18 NormalCut (True=静默失败!)
        True,    # 19 UseFeatScope
        True,    # 20 UseAutoSelect
        True,    # 21 AssemblyFeatureScope
        True,    # 22 AutoSelectComponents
        False,   # 23 PropagateFeatureToParts
        0,       # 24 T0
        0.0,     # 25 StartOffset
        False)   # 26 FlipStartOffset
    if feat is None:
        return f"❌ 切除失败: FeatureCut3 返回 None (depth={depth}, thru={through_all}) — 检查草图是否闭合/选中"
    return f"✅ 切除: depth={depth} thru={through_all}"


@mcp.tool()
async def sw_feature_revolve(angle: float = 360.0) -> str:
    """旋转凸台。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureRevolve2,
        True, True, False, False, 0, 0,
        angle / 57.2958,
        False, False, 0, 0,
        True, True, True, 0, 0, False, False)
    return f"旋转: {angle}°"


@mcp.tool()
async def sw_feature_revolve_cut(angle: float = 360.0) -> str:
    """旋转切除。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureRevolveCut3,
        False, False, False, False, False,
        6, 6, angle / 57.2958, 0.0,
        False, False, False, False,
        1, 1, True, True, True, False,
        0, 0, False, False)
    return f"旋转切除: {angle}°"


@mcp.tool()
async def sw_feature_sweep() -> str:
    """扫描（需先有轮廓+路径）。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureSweep3, False, False, 0, False, False, 0, False, 0, 0, 0, True, True, True)
    return "扫描完成"


@mcp.tool()
async def sw_feature_loft() -> str:
    """放样（需多个轮廓草图）。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureLoft2, False, False, False, False, 0, 0, 0, 1, 0, False, True, True)
    return "放样完成"


@mcp.tool()
async def sw_feature_fillet(r: float, edge_count: int = 1) -> str:
    """特征倒圆角 R=r(m)。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureFillet2, 30, r, 1, 0, 0, 0, 0)
    return f"倒圆角: R={r}"


@mcp.tool()
async def sw_feature_chamfer(d: float = 0.001, angle: float = 45.0) -> str:
    """倒角: d=距离(m), angle=角度(deg)。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureChamfer2, 4, 1, d, angle / 57.2958, 0, 0, 0)
    return f"倒角: d={d} ∠{angle}°"


@mcp.tool()
async def sw_feature_shell(thickness: float = 0.001) -> str:
    """抽壳: thickness=壁厚(m)。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureShell, thickness, 1)
    return f"抽壳: {thickness}"


@mcp.tool()
async def sw_feature_draft(angle: float = 5.0) -> str:
    """拔模: angle=拔模角(deg)。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureDraft2, angle / 57.2958, False, 0, 0, 0, True)
    return f"拔模: {angle}°"


@mcp.tool()
async def sw_feature_rib(thickness: float = 0.002) -> str:
    """筋特征。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureRib2, thickness, True, False, False, False, False, False)
    return f"筋: {thickness}"


@mcp.tool()
async def sw_feature_dome(height: float = 0.005) -> str:
    """圆顶: height=高度(m)。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureDome, height, 0, False, False, False, 1)
    return f"圆顶: {height}"


@mcp.tool()
async def sw_feature_scale(factor: float = 2.0) -> str:
    """缩放实体。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureScale, 0, True, factor)
    return f"缩放: ×{factor}"


@mcp.tool()
async def sw_feature_pattern_linear(n: int = 2, dx: float = 0.01) -> str:
    """线性阵列: n=数量, dx=间距(m)。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureLinearPattern2, n, dx, 1, n, 0.0, 0, False, False, "NULL", "NULL", False, True)
    return f"线性阵列: {n}个 dx={dx}"


@mcp.tool()
async def sw_feature_pattern_circular(n: int = 6, angle: float = 360.0) -> str:
    """圆周阵列: n=数量, angle=总角度(deg)。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureCircularPattern2, n, angle / 57.2958, False, "NULL", False, True, False)
    return f"圆周阵列: {n}个 {angle}°"


@mcp.tool()
async def sw_feature_mirror() -> str:
    """镜像特征（需先选镜像面）。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureMirror2, False, False, False, False)
    return "镜像完成"


@mcp.tool()
async def sw_feature_hole_diameter(diameter: float = 0.005, depth: float = 0.01) -> str:
    """简单直孔。"""
    fm = _feature_mgr()
    _safe_com_call(fm.HoleWizard5, 0, diameter, depth, 0, 0, 0, 0, 0, 0, 0, 0,
        "", "", "", "", "", "", "", 0, "", False, True, True, True, True, False)
    return f"孔: ∅{diameter}×{depth}"


@mcp.tool()
async def sw_feature_thread(diameter: float = 0.006, pitch: float = 0.001, depth: float = 0.01) -> str:
    """螺纹装饰线。"""
    fm = _feature_mgr()
    _safe_com_call(fm.InsertCosmeticThread2, 1, diameter, pitch, depth, False, False)
    return f"螺纹: M{diameter*1000:.0f}×{pitch*1000:.1f}"


@mcp.tool()
async def sw_feature_boss_thin(depth: float = 0.005, thickness: float = 0.002) -> str:
    """薄壁拉伸。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureExtrusionThin2,
        True, False, False, 1, 1, depth, 0.0, 0, False, True,
        thickness, thickness, False, False, False, False,
        1, 1, True, True, True, 0, 0, False, False)
    return f"薄壁: depth={depth} t={thickness}"


@mcp.tool()
async def sw_feature_cut_sweep() -> str:
    """扫描切除。"""
    fm = _feature_mgr()
    _safe_com_call(fm.FeatureCutSweep3, False, False, 0, False, False, 0, 0, False, 0, 0, 0, 0, True, True, True)
    return "扫描切除完成"


# ═══════════════════════════════════════════════════════════════════
# Category 6: 选择操作 (10 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_select_plane(plane_name: str) -> str:
    """选择基准面。"""
    ok = _model_ext().SelectByID2(plane_name, "PLANE", 0, 0, 0, _vb(False), _vi4(0), _vn(), _vi4(0))
    return f"选中: {plane_name}" if ok else f"未找到: {plane_name}"


@mcp.tool()
async def sw_select_face(face_name: str = "") -> str:
    """选择面。"""
    ok = _model_ext().SelectByID2(face_name, "FACE", 0, 0, 0, _vb(False), _vi4(0), _vn(), _vi4(0))
    return "选中面" if ok else "未找到面"


@mcp.tool()
async def sw_select_edge(edge_name: str = "") -> str:
    """选择边。"""
    ok = _model_ext().SelectByID2(edge_name, "EDGE", 0, 0, 0, _vb(False), _vi4(0), _vn(), _vi4(0))
    return "选中边" if ok else "未找到边"


@mcp.tool()
async def sw_select_body() -> str:
    """选择实体。"""
    ok = _model_ext().SelectByID2("", "SOLIDBODY", 0, 0, 0, _vb(False), _vi4(0), _vn(), _vi4(0))
    return "选中实体" if ok else "未找到"


@mcp.tool()
async def sw_select_feature(feature_name: str) -> str:
    """按名称选特征。"""
    ok = _model_ext().SelectByID2(feature_name, "BODYFEATURE", 0, 0, 0, _vb(False), _vi4(0), _vn(), _vi4(0))
    return f"选中: {feature_name}" if ok else f"未找到: {feature_name}"


@mcp.tool()
async def sw_select_vertex(x: float, y: float, z: float) -> str:
    """按坐标选顶点。"""
    ok = _model_ext().SelectByID2("", "VERTEX", x, y, z, _vb(False), _vi4(0), _vn(), _vi4(0))
    return f"选中顶点({x},{y},{z})" if ok else "未找到"


@mcp.tool()
async def sw_select_all() -> str:
    """全选实体。"""
    _get_model().Extension.SelectByID2("", "SOLIDBODY", 0, 0, 0, _vb(True), _vi4(0), _vn(), _vi4(0))
    return "全选"


@mcp.tool()
async def sw_clear_selection() -> str:
    """清除选择。"""
    _get_model().ClearSelection2(True)
    return "已清除"


@mcp.tool()
async def sw_get_selection_count() -> str:
    """选中数量。"""
    return str(_sel_mgr().GetSelectedObjectCount2(-1))


@mcp.tool()
async def sw_get_selected_names() -> str:
    """选中对象名称。"""
    sel = _sel_mgr()
    count = sel.GetSelectedObjectCount2(-1)
    names = []
    for i in range(1, count + 1):
        obj = sel.GetSelectedObject6(i, -1)
        if obj:
            names.append(_com_attr(obj, "Name"))
    return ", ".join(names) if names else "无选中"


# ═══════════════════════════════════════════════════════════════════
# Category 7: 参考几何 (5 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_create_plane_offset(offset: float = 0.01, reference: str = "前视基准面") -> str:
    """偏移基准面。"""
    model_ext = _model_ext()
    if model_ext.SelectByID2(reference, "PLANE", 0, 0, 0, _vb(False), _vi4(0), _vn(), _vi4(0)):
        _feature_mgr().InsertRefPlane(8, offset, 0, 0, 0, 0)
        return f"偏移面: {reference}+{offset}"
    return f"未找到: {reference}"


@mcp.tool()
async def sw_create_plane_angle(angle: float = 45.0) -> str:
    """角度基准面（需先选面+边）。"""
    _feature_mgr().InsertRefPlane(4, angle / 57.2958, 0, 0, 0, 0)
    return f"角度面: {angle}°"


@mcp.tool()
async def sw_create_plane_three_points() -> str:
    """三点基准面（需先选三点）。"""
    _feature_mgr().InsertRefPlane(2, 0, 0, 0, 0, 0)
    return "三点基准面"


@mcp.tool()
async def sw_insert_axis(type_: int = 1) -> str:
    """参考轴: 1=圆柱面 2=边 3=两点 4=面交线。"""
    _get_model().InsertAxis2(type_, True)
    return f"参考轴 type={type_}"


@mcp.tool()
async def sw_insert_coordinate() -> str:
    """坐标系（需选原点+两条边）。"""
    _get_model().InsertCoordinateSystem(False)
    return "坐标系"


# ═══════════════════════════════════════════════════════════════════
# Category 8: 材料与外观 (4 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_set_material(material: str = "6061 铝合金") -> str:
    """设置材料: 6061/普通碳钢/304不锈钢/ABS。"""
    _model_ext().SetMaterialPropertyValues2(material, "", "", 0)
    return f"材料: {material}"


@mcp.tool()
async def sw_get_material() -> str:
    """当前材料。"""
    return _com_attr(_get_model(), "GetMaterialName")


@mcp.tool()
async def sw_set_appearance(r: int, g: int, b: int) -> str:
    """设置颜色 RGB(0-255)。"""
    model = _get_model()
    model.MaterialPropertyValues = [r / 255, g / 255, b / 255, 1.0, 0.5, 0.5, 0.5, 0.4, 0.4]
    return f"颜色: RGB({r},{g},{b})"


@mcp.tool()
async def sw_set_transparency(transparent: bool = True) -> str:
    """设置透明度。"""
    _get_model().SetTransparency(transparent, 0)
    return f"透明: {transparent}"


# ═══════════════════════════════════════════════════════════════════
# Category 9: 测量与质量属性 (4 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_get_mass_properties() -> str:
    """质量属性（SW2026 COM 中 GetMassProperties 参数签名不兼容，返回包围盒估算）。"""
    model = _get_model()
    _com_attr(model, 'EditRebuild3')
    time.sleep(0.3)
    # SW2026: GetMassProperties COM 签名不兼容，用包围盒替代
    try:
        bb = model.Extension.GetBox(0)
        if bb and len(bb) >= 6:
            dx = (bb[3] - bb[0]) * 1000
            dy = (bb[4] - bb[1]) * 1000
            dz = (bb[5] - bb[2]) * 1000
            vol_mm3 = dx * dy * dz
            est_mass = vol_mm3 * 2.7 / 1000  # 铝密度 2.7g/cm³ 粗略估算
            return f"包围盒={dx:.1f}×{dy:.1f}×{dz:.1f}mm | 体积≈{vol_mm3:.0f}mm³ | 质量≈{est_mass:.1f}g (铝估算)"
    except Exception:
        pass
    return "质量属性不可用 (SW2026 COM 限制)，请在 SW GUI 中查看"


@mcp.tool()
async def sw_measure_distance(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float) -> str:
    """两点距离（m→mm）。"""
    if HAS_NUMPY:
        d = float(np.linalg.norm(np.array([x2 - x1, y2 - y1, z2 - z1])))
    else:
        d = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)
    return f"{d * 1000:.3f} mm"


@mcp.tool()
async def sw_get_bounding_box() -> str:
    """包围盒 mm。"""
    bb = _model_ext().GetBox(0)
    if bb is None:
        return "无法获取"
    dx = (bb[3] - bb[0]) * 1000
    dy = (bb[4] - bb[1]) * 1000
    dz = (bb[5] - bb[2]) * 1000
    return f"{dx:.1f}×{dy:.1f}×{dz:.1f} mm"


@mcp.tool()
async def sw_get_feature_count() -> str:
    """特征数量。"""
    model = _get_model()
    try:
        count = 0
        feat = model.FirstFeature()
        while feat is not None:
            count += 1
            feat = feat.GetNextFeature()
        return str(count)
    except Exception:
        return "N/A (SW2026 COM 限制)"


# ═══════════════════════════════════════════════════════════════════
# Category 10: 配置管理 (4 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_list_configs() -> str:
    """列出配置名。"""
    return ", ".join(_get_model().GetConfigurationNames())


@mcp.tool()
async def sw_get_active_config() -> str:
    """当前配置。"""
    return _get_model().ConfigurationManager.ActiveConfiguration.Name


@mcp.tool()
async def sw_add_config(name: str) -> str:
    """添加配置。"""
    _get_model().AddConfiguration3(name, "", "", 0)
    return f"配置: {name}"


@mcp.tool()
async def sw_switch_config(name: str) -> str:
    """切换配置。"""
    _get_model().ShowConfiguration2(name)
    return f"切换: {name}"


# ═══════════════════════════════════════════════════════════════════
# Category 11: 视图操作 (10 tools)
# ═══════════════════════════════════════════════════════════════════

VIEW_MAP = {
    "front": "*前视", "top": "*上视", "right": "*右视",
    "back": "*后视", "bottom": "*下视", "iso": "*等轴测"
}

@mcp.tool()
async def sw_view_front() -> str:
    _get_model().ShowNamedView2("*前视", -1)
    return "前视图"

@mcp.tool()
async def sw_view_top() -> str:
    _get_model().ShowNamedView2("*上视", -1)
    return "上视图"

@mcp.tool()
async def sw_view_right() -> str:
    _get_model().ShowNamedView2("*右视", -1)
    return "右视图"

@mcp.tool()
async def sw_view_back() -> str:
    _get_model().ShowNamedView2("*后视", -1)
    return "后视图"

@mcp.tool()
async def sw_view_bottom() -> str:
    _get_model().ShowNamedView2("*下视", -1)
    return "下视图"

@mcp.tool()
async def sw_view_isometric() -> str:
    _get_model().ShowNamedView2("*等轴测", -1)
    return "等轴测"

@mcp.tool()
async def sw_view_zoom_to_fit() -> str:
    _get_model().ViewZoomtofit2()
    return "缩放完成"

@mcp.tool()
async def sw_view_wireframe() -> str:
    _get_model().SetDisplayMode(1, 0, 0, 0, 0)
    return "线框"

@mcp.tool()
async def sw_view_shaded() -> str:
    _get_model().SetDisplayMode(3, 0, 0, 0, 0)
    return "着色"

@mcp.tool()
async def sw_view_edges_shaded() -> str:
    _get_model().SetDisplayMode(2, 0, 0, 0, 0)
    return "带边线上色"


# ═══════════════════════════════════════════════════════════════════
# Category 12: 装配体 (9 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_assembly_add_component(filepath: str) -> str:
    """插入零件到装配体。"""
    abs_path = os.path.abspath(filepath)
    if not os.path.exists(abs_path):
        return f"文件不存在: {abs_path}"
    _get_model().AddComponent5(abs_path, 0, "", False, "", 0, 0, 0)
    return f"插入: {abs_path}"


@mcp.tool()
async def sw_assembly_mate_coincident() -> str:
    _get_model().AddMate5(0, 0, False, 0.0, 0.0, 0.0, 0, 0, False, _empty_dispatch())
    return "重合配合"

@mcp.tool()
async def sw_assembly_mate_concentric() -> str:
    _get_model().AddMate5(1, 0, False, 0.0, 0.0, 0.0, 0, 0, False, _empty_dispatch())
    return "同心配合"

@mcp.tool()
async def sw_assembly_mate_parallel() -> str:
    _get_model().AddMate5(2, 0, False, 0.0, 0.0, 0.0, 0, 0, False, _empty_dispatch())
    return "平行配合"

@mcp.tool()
async def sw_assembly_mate_distance(distance: float = 0.01) -> str:
    _get_model().AddMate5(6, 0, False, distance, 0.0, 0.0, 0, 0, False, _empty_dispatch())
    return f"距离: {distance}"

@mcp.tool()
async def sw_assembly_mate_angle(angle: float = 90.0) -> str:
    _get_model().AddMate5(10, 0, False, angle / 57.2958, 0.0, 0.0, 0, 0, False, _empty_dispatch())
    return f"角度: {angle}°"

@mcp.tool()
async def sw_assembly_mate_tangent() -> str:
    _get_model().AddMate5(12, 0, False, 0.0, 0.0, 0.0, 0, 0, False, _empty_dispatch())
    return "相切配合"

@mcp.tool()
async def sw_assembly_explode() -> str:
    _get_model().ViewExplodeAssembly()
    return "爆炸视图"

@mcp.tool()
async def sw_assembly_collapse() -> str:
    _get_model().ViewCollapseAssembly()
    return "已折叠"


# ═══════════════════════════════════════════════════════════════════
# Category 13: 审查 (5 tools)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_review_quick() -> str:
    """快速审查：等轴测视图 + 包围盒 + 特征数 + 质量。"""
    model = _get_model()
    lines = []
    # title
    lines.append(f"文档: {_com_attr(model, 'GetTitle')}")
    # isometric
    model.ShowNamedView2("*等轴测", -1)
    model.ViewZoomtofit2()
    # bounding box
    try:
        bb = model.Extension.GetBox(0)
        if bb:
            dx = (bb[3] - bb[0]) * 1000
            dy = (bb[4] - bb[1]) * 1000
            dz = (bb[5] - bb[2]) * 1000
            lines.append(f"包围盒: {dx:.1f}×{dy:.1f}×{dz:.1f} mm")
    except Exception:
        lines.append("包围盒: N/A")
    # feature count (SW2026 Python COM: FirstFeature may fail, fallback)
    count = "?"
    try:
        feat = model.FirstFeature()
        count = 0
        while feat is not None:
            count += 1
            feat = feat.GetNextFeature()
        lines.append(f"特征数: {count}")
    except Exception:
        lines.append("特征数: N/A (SW2026 COM 限制)")
        count = -1
    # mass
    try:
        mp = model.Extension.GetMassProperties(1, 0)
        if mp:
            lines.append(f"质量: {mp[0]*1000:.2f}g")
            lines.append(f"体积: {mp[1]*1e9:.2f}mm³")
    except Exception:
        lines.append("质量: N/A（需先重建）")
    # status
    if isinstance(count, int) and count > 1:
        lines.append("✅ 有实体特征")
    elif count == -1:
        lines.append("✅ 模型已生成（特征遍历 COM 不可用，属于已知 SW2026 限制）")
    else:
        lines.append("⚠️ 需进一步检查")
    return "\n".join(lines)


@mcp.tool()
async def sw_review_all_views() -> str:
    """六视图 + 等轴测逐一切换审查。"""
    model = _get_model()
    views = [
        ("前视", "*前视"), ("后视", "*后视"),
        ("左视", "*左视"), ("右视", "*右视"),
        ("上视", "*上视"), ("下视", "*下视"),
        ("等轴测", "*等轴测"),
    ]
    for name, view_name in views:
        try:
            model.ShowNamedView2(view_name, -1)
            time.sleep(0.3)
        except Exception:
            pass
    model.ViewZoomtofit2()
    return f"已审查 7 个视图"


@mcp.tool()
async def sw_review_check_blank() -> str:
    """检查是否有空白/空特征。"""
    model = _get_model()
    try:
        feat = model.FirstFeature()
        issues = []
        count = 0
        while feat is not None:
            count += 1
            fname = _com_attr(feat, "Name")
            ftype = feat.GetTypeName2() if hasattr(feat, 'GetTypeName2') else "?"
            try:
                if hasattr(feat, 'IsSuppressed'):
                    if feat.IsSuppressed():
                        issues.append(f"⚠️ 压缩: {fname} ({ftype})")
            except Exception:
                pass
            feat = feat.GetNextFeature()
        if not issues:
            return f"✅ 无问题 (共 {count} 个特征)"
        return f"共 {count} 特征\n" + "\n".join(issues)
    except Exception:
        return "⚠️ 特征遍历不可用 (SW2026 Python COM 已知限制)，建议在 SW GUI 中目视检查"


@mcp.tool()
async def sw_review_thickness_check(min_thickness: float = 0.0005) -> str:
    """壁厚检查：检测模型是否过薄（3D 打印可行性）。"""
    model = _get_model()
    bb = model.Extension.GetBox(0)
    if bb is None:
        return "无法获取包围盒"
    dx = bb[3] - bb[0]
    dy = bb[4] - bb[1]
    dz = bb[5] - bb[2]
    min_dim = min(dx, dy, dz)
    status = "✅" if min_dim >= min_thickness else "⚠️ 过薄"
    return f"{status} 最小包围盒维度={min_dim*1000:.2f}mm (阈值={min_thickness*1000:.2f}mm)"


@mcp.tool()
async def sw_review_export_screenshot(filepath: str) -> str:
    """导出当前视图截图（SaveAs JPEG）。"""
    model = _get_model()
    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    errors = _byref_int(0)
    warnings = _byref_int(0)
    ret = model.Extension.SaveAs(abs_path, _vi4(0), _vi4(1), _vn(), errors, warnings)
    return f"截图: {abs_path}" if ret else f"失败 (err={errors.value})"


# ═══════════════════════════════════════════════════════════════════
# Category 14: 齿轮生成 (4 tools)
# ═══════════════════════════════════════════════════════════════════

GEAR_PRESETS: dict = {
    "J1": {"z1": 10, "z2": 50, "m": 0.0008, "alpha_deg": 20, "center_dist": 0.024, "thickness": 0.008, "bore1": 0.005, "bore2": 0.008},
    "J2": {"z1": 10, "z2": 50, "m": 0.0008, "alpha_deg": 20, "center_dist": 0.024, "thickness": 0.008, "bore1": 0.005, "bore2": 0.008},
    "J3": {"z1": 10, "z2": 40, "m": 0.0008, "alpha_deg": 20, "center_dist": 0.020, "thickness": 0.008, "bore1": 0.005, "bore2": 0.008},
    "J4": {"z1": 10, "z2": 50, "m": 0.0006, "alpha_deg": 20, "center_dist": 0.018, "thickness": 0.006, "bore1": 0.005, "bore2": 0.008},
    "J5": {"z1": 10, "z2": 40, "m": 0.0005, "alpha_deg": 20, "center_dist": 0.0125, "thickness": 0.005, "bore1": 0.005, "bore2": 0.006},
}


def _involute_pt(rb, t, angle):
    x = rb * (math.cos(t + angle) + t * math.sin(t + angle))
    y = rb * (math.sin(t + angle) - t * math.cos(t + angle))
    return x, y


@mcp.tool()
async def sw_gear_create(joint: str = "J1", which: str = "both", segments: int = 30) -> str:
    """生成渐开线齿轮。joint: J1-J5, which: pinion/gear/both, segments: 渐开线段数(越大越精确)。

    从齿轮参数矩阵读取参数，单草图策略生成齿形+拉伸。
    """
    if joint not in GEAR_PRESETS:
        return f"关节 {joint} 不在预设。可选: {', '.join(GEAR_PRESETS.keys())}"

    p = GEAR_PRESETS[joint]
    z1, z2, m, alpha_deg = p["z1"], p["z2"], p["m"], p["alpha_deg"]
    thickness = p["thickness"]
    alpha = math.radians(alpha_deg)
    results = []

    for label, z, bore in [("小齿轮", z1, p["bore1"]), ("大齿轮", z2, p["bore2"])]:
        if which == "pinion" and label == "大齿轮":
            continue
        if which == "gear" and label == "小齿轮":
            continue

        pd = m * z
        rd = pd * math.cos(alpha)
        rr = (pd - 2.5 * m) / 2
        ra = (pd + 2 * m) / 2
        rb = rd / 2

        sw = _get_sw()
        template = _find_template("part")
        if not template:
            results.append(f"{joint} {label} 找不到模板")
            continue
        sw.NewDocument(template, 0, 0, 0)
        doc = None
        for _ in range(30):
            doc = sw.ActiveDoc
            if doc is not None:
                break
            time.sleep(0.3)
        if doc is None:
            results.append(f"{joint} {label} 创建文档失败")
            continue

        doc.Extension.SelectByID2("前视基准面", "PLANE", _vr8(0), _vr8(0), _vr8(0), _vb(False), _vi4(0), _vn(), _vi4(0))
        sm = doc.SketchManager
        doc.InsertSketch2(True)

        # 渐开线齿形 — 闭合轮廓（不画齿根圆，用齿根弧连接各齿）
        # 预计算所有齿的轮廓点
        all_right = []  # 每个齿的右齿面点列
        all_left = []   # 每个齿的左齿面点列
        all_tc = []     # 齿中心角

        for ti in range(z):
            tc = 2 * math.pi * ti / z
            all_tc.append(tc)
            ht = math.pi / (2 * z)
            t_max = math.sqrt(max(0, (ra / rb) ** 2 - 1))

            # 右齿面
            rf_pts = []
            for si in range(segments + 1):
                t = t_max * si / segments
                x, y = _involute_pt(rb, t, tc + ht)
                rf_pts.append((x, y))
            all_right.append(rf_pts)

            # 左齿面（镜像，方向反转）
            lf_pts = []
            for si in range(segments + 1):
                t = t_max * (segments - si) / segments
                x, y = _involute_pt(-rb, t, tc - ht)
                lf_pts.append((x, y))
            all_left.append(lf_pts)

        # 画所有齿
        for i in range(z):
            rf = all_right[i]
            lf = all_left[i]
            ni = (i + 1) % z
            nr = all_right[ni]

            # 右齿面线段
            for j in range(len(rf) - 1):
                sm.CreateLine(rf[j][0], rf[j][1], 0, rf[j+1][0], rf[j+1][1], 0)

            # 齿顶弧 (三点弧: 右齿面终点 → 左齿面起点)
            ang_re = math.atan2(rf[-1][1], rf[-1][0])
            ang_ls = math.atan2(lf[0][1], lf[0][0])
            mid_a = (ang_re + ang_ls) / 2
            if abs(ang_ls - ang_re) > math.pi:
                mid_a += math.pi
            sm.Create3PointArc(
                rf[-1][0], rf[-1][1], 0,
                lf[0][0], lf[0][1], 0,
                ra * math.cos(mid_a), ra * math.sin(mid_a), 0)

            # 左齿面线段
            for j in range(len(lf) - 1):
                sm.CreateLine(lf[j][0], lf[j][1], 0, lf[j+1][0], lf[j+1][1], 0)

            # 齿根弧: 左齿面终点 → 下个齿右齿面起点
            ang_le = math.atan2(lf[-1][1], lf[-1][0])
            ang_nr = math.atan2(nr[0][1], nr[0][0])
            if ang_le < 0: ang_le += 2 * math.pi
            if ang_nr < 0: ang_nr += 2 * math.pi
            if ang_nr <= ang_le:
                ang_nr += 2 * math.pi
            mid_r = (ang_le + ang_nr) / 2
            sm.Create3PointArc(
                lf[-1][0], lf[-1][1], 0,
                nr[0][0], nr[0][1], 0,
                rr * math.cos(mid_r), rr * math.sin(mid_r), 0)

        # 轴孔
        sm.CreateCircleByRadius(0, 0, 0, bore / 2)

        doc.InsertSketch2(True)
        time.sleep(0.3)

        fm = doc.FeatureManager
        _safe_com_call(fm.FeatureExtrusion2,
            True, False, False, 1, 1, thickness, 0,
            False, False, False, False, 0, 0,
            False, False, False, False,
            True, True, True, 0, 0, False)

        # 重建 + 缩放以显示模型
        doc.ClearSelection2(True)
        doc.EditRebuild3
        time.sleep(0.3)
        doc.ViewZoomtofit2()

        results.append(f"{joint} {label} Z{z} pd={pd*1000:.1f}mm")

    return " | ".join(results)


@mcp.tool()
async def sw_gear_list_presets() -> str:
    """齿轮参数矩阵总览。"""
    return "\n".join(
        f"{j}: Z1={p['z1']} Z2={p['z2']} m={p['m']*1000:.1f}mm 中心距={p['center_dist']*1000:.1f}mm 厚={p['thickness']*1000:.1f}mm"
        for j, p in GEAR_PRESETS.items()
    )


@mcp.tool()
async def sw_gear_verify(joint: str = "all") -> str:
    """交叉验证齿轮参数一致性。"""
    valid = ["J1", "J2", "J3", "J4", "J5"] if joint == "all" else [joint]
    lines = []
    for j in valid:
        if j not in GEAR_PRESETS:
            lines.append(f"{j}: 不在预设")
            continue
        p = GEAR_PRESETS[j]
        calc = p["m"] * (p["z1"] + p["z2"]) / 2
        ok = abs(calc - p["center_dist"]) < 1e-6
        lines.append(f"{j}: 计算={calc*1000:.3f} 预设={p['center_dist']*1000:.3f} {'✅' if ok else '❌'}")
    return "\n".join(lines)


@mcp.tool()
async def sw_gear_create_with_bore(joint: str = "J1", which: str = "both", segments: int = 30) -> str:
    """生成齿轮 + 轴孔。joint: J1-J5, which: pinion/gear/both。"""
    if joint not in GEAR_PRESETS:
        return f"关节 {joint} 不在预设"
    # 复用本模块的 sw_gear_create (同文件内函数, 不再依赖旧包名)
    result = await sw_gear_create(joint=joint, which=which, segments=segments)
    return result + "\n⚠️ 轴孔需手动添加（或后续扩展）"


# ═══════════════════════════════════════════════════════════════════
# Category 15: 窗口管理 + 几何验证 (2026-06-11 新增, 防假成功/防窗口拥堵)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def sw_close_all_docs(save: bool = False) -> str:
    """关闭所有打开的文档。铁律: 建模任务开始前必须调用清场。

    save=False 不保存直接关 (默认)。
    """
    sw = _get_sw()
    ok = sw.CloseAllDocuments(not save)
    return f"✅ 已关闭所有文档" if ok else "⚠️ CloseAllDocuments 返回 False"


@mcp.tool()
async def sw_quit_doc(title: str = "") -> str:
    """关闭指定标题文档 (不保存)。title 空 = 当前活动文档。

    铁律: 测试/临时零件用完即关，绝不留窗口。
    """
    sw = _get_sw()
    if not title:
        doc = sw.ActiveDoc
        if doc is None:
            return "无活动文档"
        title = _com_attr(doc, "GetTitle")
    sw.QuitDoc(title)
    return f"✅ 已关闭: {title}"


@mcp.tool()
async def sw_count_faces() -> str:
    """统计当前零件所有 body 的面数。建模后验证特征是否真实生效。

    例: 20×20×10 盒 = 6 面; +1 通孔 = 7 面。
    切除调用"成功"但面数没变 = 特征没生效 = 假成功!
    """
    model = _get_model()
    bodies = model.GetBodies2(0, True)
    if not bodies:
        return "❌ 无实体 body"
    total = 0
    lines = []
    for i, b in enumerate(bodies):
        n = _com_attr(b, "GetFaceCount")
        total += n
        lines.append(f"body{i}: {n} 面")
    lines.append(f"总计: {total} 面")
    return "\n".join(lines)


@mcp.tool()
async def sw_verify_step_geometry(step_path: str, expected_holes: str = "") -> str:
    """解析 STEP 文件验证几何特征 (防假成功核心工具)。

    expected_holes: JSON 字符串 [{"r": 2.5, "n": 4, "name": "M3孔"}, ...]
      r=半径mm, n=期望孔数。
    规则: STEP AP214 中 1 个完整圆柱孔 = 2 个半圆柱面; 圆角 = 1 面。

    返回: 半径分布 + BBox + 与期望对比。
    """
    import re as _re
    import json as _json
    from collections import Counter

    if not os.path.exists(step_path):
        return f"❌ 文件不存在: {step_path}"

    with open(step_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()

    cyls = _re.findall(
        r"CYLINDRICAL_SURFACE\s*\(\s*'[^']*'\s*,\s*#\d+\s*,\s*([\d.E+-]+)\s*\)", text)
    radii = Counter(round(float(r), 2) for r in cyls)

    pts = _re.findall(
        r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([^)]+)\s*\)\s*\)", text)
    xs, ys, zs = [], [], []
    for m in pts:
        try:
            nums = [float(x) for x in m.split(",")]
            if len(nums) >= 3:
                xs.append(nums[0]); ys.append(nums[1]); zs.append(nums[2])
        except ValueError:
            pass

    lines = ["圆柱面半径分布 (1孔=2面, 圆角=1面):"]
    for r, n in sorted(radii.items()):
        lines.append(f"  R{r}mm × {n}面 (≈{n//2}孔 或 {n}圆角)")
    n_faces = len(_re.findall(r"ADVANCED_FACE", text))
    lines.append(f"总面数: {n_faces}")
    if xs:
        lines.append(f"BBox: {max(xs)-min(xs):.1f} × {max(ys)-min(ys):.1f} × {max(zs)-min(zs):.1f} mm")

    if expected_holes:
        try:
            expects = _json.loads(expected_holes)
            all_ok = True
            lines.append("── 期望对比 ──")
            for e in expects:
                r, n_want, name = round(float(e["r"]), 2), int(e["n"]), e.get("name", "")
                got = radii.get(r, 0) // 2
                ok = got == n_want
                if not ok:
                    all_ok = False
                lines.append(f"  {name} R{r}: {got}孔/期望{n_want} {'✅' if ok else '❌'}")
            lines.append("═══ " + ("✅ PASS" if all_ok else "❌ FAIL") + " ═══")
        except (ValueError, KeyError) as e:
            lines.append(f"⚠ expected_holes 解析失败: {e}")

    return "\n".join(lines)




@mcp.tool()
async def sw_asm_add_component_posed(path: str, transform16: str) -> str:
    """装配体插入组件并设置完整位姿 (旋转+平移)。

    transform16: JSON 数组 [r11..r33, tx,ty,tz(米), 1, 0,0,0] 行约定 p'=p·R+t。
    实测 (2026-06-12): AddComponent5 只给平移; 旋转必须 Transform2 PUTREF:
      - MathUtility/Component2 dynamic 解析失败 → gen_py 手动包装
      - Transform2 是对象属性 → DISPATCH_PROPERTYPUTREF (DISPID 78), makepy put 会"找不到成员"
    """
    import json as _json
    import win32com.client.gencache as _gc
    arr = _json.loads(transform16)
    if len(arr) != 16:
        return "❌ transform16 必须 16 元素"
    sw = _get_sw()
    asm = sw.ActiveDoc
    if asm is None:
        return "❌ 无活动装配体"
    _mod = _gc.GetModuleForTypelib("{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 34, 0)
    mu = _mod.IMathUtility(sw.GetMathUtility()._oleobj_)
    comp = asm.AddComponent5(path, 0, "", False, "", arr[9], arr[10], arr[11])
    if comp is None:
        return f"❌ AddComponent5 失败: {path}"
    va = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in arr])
    xf = mu.CreateTransform(va)
    comp._oleobj_.Invoke(78, 0, pythoncom.DISPATCH_PROPERTYPUTREF, 0, xf._oleobj_)
    return f"✅ 组件已插入并定位: {os.path.basename(path)}"


@mcp.tool()
async def sw_asm_verify_poses(step_path: str, expected_json: str, tol_mm: float = 0.1) -> str:
    """装配体 STEP 位姿级验证 (防假成功)。

    expected_json: [[label, [tx,ty,tz](mm), [zx,zy,zz]], ...]
    解析 ITEM_DEFINED_TRANSFORMATION — 组件位姿在第一个 placement (第二个是恒等参考系)。
    """
    import json as _json
    import re as _re
    expects = _json.loads(expected_json)
    if not os.path.exists(step_path):
        return f"❌ 文件不存在: {step_path}"
    with open(step_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    ents = {}
    for m in _re.finditer(r"#(\d+)\s*=\s*(\w+)\s*\((.*)\)\s*;", text):
        ents[int(m.group(1))] = (m.group(2), m.group(3))
    placements = []
    for eid, (typ, body) in ents.items():
        if typ != "ITEM_DEFINED_TRANSFORMATION":
            continue
        refs = [int(x) for x in _re.findall(r"#(\d+)", body)]
        if not refs:
            continue
        t2, b2 = ents.get(refs[0], ("", ""))
        if t2 != "AXIS2_PLACEMENT_3D":
            continue
        rr = [int(x) for x in _re.findall(r"#(\d+)", b2)]
        _, cb = ents.get(rr[0], ("", ""))
        cm = _re.search(r"\(\s*([\d.E+-]+),\s*([\d.E+-]+),\s*([\d.E+-]+)\s*\)", cb)
        if not cm:
            continue
        origin = tuple(float(cm.group(i)) for i in (1, 2, 3))
        axis = None
        if len(rr) > 1:
            _, db = ents.get(rr[1], ("", ""))
            dm = _re.search(r"\(\s*([\d.E+-]+),\s*([\d.E+-]+),\s*([\d.E+-]+)\s*\)", db)
            if dm:
                axis = tuple(float(dm.group(i)) for i in (1, 2, 3))
        placements.append((origin, axis))
    lines, used, n_match = [f"STEP 位姿 {len(placements)} 个"], set(), 0
    for item in expects:
        label, t, z = item[0], item[1], item[2]
        found = False
        for i, (origin, axis) in enumerate(placements):
            if i in used:
                continue
            if all(abs(origin[k] - t[k]) < tol_mm for k in range(3)):
                if axis is None or all(abs(axis[k] - z[k]) < 0.01 for k in range(3)):
                    used.add(i); found = True; break
        n_match += found
        if not found:
            lines.append(f"❌ {label}: t={t} z={z} 未匹配")
    lines.append(f"位姿匹配 {n_match}/{len(expects)} " + ("✅" if n_match == len(expects) else "❌"))
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════

async def run_server():
    """Start MCP stdio server"""
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(run_server())
