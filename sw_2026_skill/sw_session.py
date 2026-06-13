"""
sw_session.py — SW2026 会话管理 (with 模式 + 清场 + 面数追踪 + COM 模式四件套)
==============================================================================
来源: UR-SEU-2026 swlib.py (35+ 零件实战验证)。
铁律内置:
  1. FeatureCut3 26参数 Flip=F/Dir=F/NormalCut=F, None 必 raise
  2. 开工 CloseAllDocuments, 收工 QuitDoc
  3. 每特征面数追踪
  4. GetActiveObject 优先 (Dispatch 每次开新 SW 实例)
注意: SW 类的草图/特征接口用 **毫米** (内部转米); 底层 sw_part.py 用米。
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os
import glob
import math
import time
import pythoncom
from win32com.client import GetActiveObject, VARIANT

SW_TYPELIB = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
DISPID_TRANSFORM2 = 78


def VN():
    """空对象位 VARIANT (Callout/ExportData) — 裸 None 会 TYPEMISMATCH"""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def VBR():
    """byref int 输出 VARIANT (errors/warnings)"""
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def mm(value):
    """毫米 → 米 (SW API 单位)"""
    return value / 1000.0


M = mm  # legacy alias — use mm()


def deg(value):
    return value * math.pi / 180.0


def _v(x):
    """pywin32 属性/方法歧义兼容 (EditRebuild3/GetTitle 可能是属性)"""
    return x() if callable(x) else x


def connect(visible=True, wait_seconds=3):
    """连接 SW。GetActiveObject 优先 — Dispatch 每次开新实例 (一天积压17个的教训)。"""
    pythoncom.CoInitialize()
    try:
        return GetActiveObject("SldWorks.Application")
    except pythoncom.com_error:
        from win32com.client import dynamic
        sw = dynamic.Dispatch("SldWorks.Application")
        sw.Visible = visible
        time.sleep(wait_seconds)
        return sw


def find_template(pattern="*.prtdot"):
    """模板查找: 注册表键可能为空/幽灵路径 → glob 兜底"""
    for d in (r"C:\ProgramData\SolidWorks\SOLIDWORKS *\templates",):
        hits = glob.glob(os.path.join(d, pattern))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"找不到 SW 模板: {pattern}")


# ── COM 模式四件套 (references/com-patterns.md) ──

def genmod():
    """gen_py 模块。SW 不支持 GetTypeInfo → CastTo/EnsureDispatch 全废,
    必须手动包装: genmod().IXxx(obj._oleobj_)"""
    import win32com.client.gencache as gc
    try:
        return gc.GetModuleForTypelib(SW_TYPELIB, 0, 34, 0)
    except Exception:
        gc.MakeModuleForTypelib(SW_TYPELIB, 0, 0, 34)
        return gc.GetModuleForTypelib(SW_TYPELIB, 0, 34, 0)


def early(obj, iface):
    """dynamic dispatch → early-bound 接口包装。
    用途: MathUtility.CreateTransform / Component2 / FirstFeature 等 dynamic 失败的成员"""
    return getattr(genmod(), iface)(obj._oleobj_)


def put_object_property(com_obj, dispid, value_dispatch):
    """对象属性赋值 — 必须 DISPATCH_PROPERTYPUTREF (makepy 的 put 会"找不到成员")
    例: put_object_property(comp, DISPID_TRANSFORM2, xform)"""
    com_obj._oleobj_.Invoke(dispid, 0, pythoncom.DISPATCH_PROPERTYPUTREF, 0,
                            value_dispatch._oleobj_)


def untuple(ret):
    """early-bound 方法 (GetBodies3 等) 返回 (data, info) tuple 的兼容解包"""
    return ret[0] if isinstance(ret, tuple) else ret


class SW:
    """SolidWorks 零件建模会话。with 语句保证窗口清理。坐标/尺寸全部毫米。"""

    def __init__(self, part_name="part"):
        self.part_name = part_name
        self.faces_log = []

    def __enter__(self):
        self.sw = connect()
        self.sw.CloseAllDocuments(True)          # 铁律: 清场
        tpl = find_template("*.prtdot")
        self.model = self.sw.NewDocument(tpl, 0, 0, 0) or _v(self.sw.ActiveDoc)
        if self.model is None:
            raise RuntimeError("NewDocument 失败 (模板路径/幽灵模板?)")
        self.ext = self.model.Extension
        self.skm = self.model.SketchManager
        self.fm = self.model.FeatureManager
        print(f"[{self.part_name}] SW 会话开始, 已清场")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.sw.QuitDoc(_v(self.model.GetTitle))   # 铁律: 关窗口
            print(f"[{self.part_name}] 窗口已关")
        except Exception:
            pass
        return False

    # ── 面数追踪 (铁律 3: 防假成功 L2) ──
    def faces(self):
        bodies = self.model.GetBodies2(0, True)
        return sum(_v(b.GetFaceCount) for b in bodies) if bodies else 0

    def check_faces(self, label, min_delta=1):
        n = self.faces()
        prev = self.faces_log[-1][1] if self.faces_log else 0
        self.faces_log.append((label, n))
        if n < prev + min_delta:
            raise RuntimeError(f"{label}: 面数 {prev}→{n}, 特征可能未生效!")
        print(f"   ✓ {label} faces={n}")

    # ── 选择 ──
    def plane(self, names=("前视基准面", "Front Plane")):
        for nm in names:
            if self.ext.SelectByID2(nm, "PLANE", 0, 0, 0, False, 0, VN(), 0):
                return
        raise RuntimeError(f"选基准面失败: {names}")

    def face(self, x, y, z, label=""):
        """坐标选面 (mm)。⚠ 仅零件内可用; 点必须避开孔区、偏离面中心 20-30%。
        装配体内禁用 — 视线射线拾取会选错面 (用 sw_mate 程序化选择)。"""
        if not self.ext.SelectByID2("", "FACE", M(x), M(y), M(z), False, 0, VN(), 0):
            raise RuntimeError(f"选面失败 {label} ({x},{y},{z})mm")

    # ── 草图 (毫米) ──
    def sketch_on_plane(self, names=("上视基准面", "Top Plane")):
        self.plane(names)
        self.model.InsertSketch2(True)
        self.model.ClearSelection2(True)

    def sketch_on_face(self, x, y, z, label=""):
        self.model.ClearSelection2(True)
        self.face(x, y, z, label)
        self.model.InsertSketch2(True)
        self.model.ClearSelection2(True)

    def rect(self, cx, cy, w, h):
        """中心矩形 (mm)"""
        self.skm.CreateCenterRectangle(M(cx), M(cy), 0, M(cx + w / 2), M(cy + h / 2), 0)

    def circle(self, cx, cy, d):
        """圆 (mm, 直径!)"""
        self.skm.CreateCircleByRadius(M(cx), M(cy), 0, M(d / 2))

    def circle4(self, half_pitch, d, rotate45=False):
        """4 孔阵列 (单草图策略 — 规避 CircularPattern4 ❌)"""
        if rotate45:
            r = half_pitch * math.sqrt(2)
            pts = [(r, 0), (-r, 0), (0, r), (0, -r)]
        else:
            pts = [(half_pitch, half_pitch), (-half_pitch, half_pitch),
                   (half_pitch, -half_pitch), (-half_pitch, -half_pitch)]
        for cx, cy in pts:
            self.circle(cx, cy, d)

    def circle_pcd(self, pcd_d, hole_d, n=4, start_deg=45, cx=0, cy=0):
        """节圆均布孔 (单草图策略)"""
        for k in range(n):
            a = math.radians(start_deg + 360 / n * k)
            self.circle(cx + pcd_d / 2 * math.cos(a), cy + pcd_d / 2 * math.sin(a), hole_d)

    def line(self, x1, y1, x2, y2):
        self.skm.CreateLine(M(x1), M(y1), 0, M(x2), M(y2), 0)

    def exit_sketch(self):
        self.model.InsertSketch2(True)

    # ── 特征 (已验证签名) ──
    def extrude(self, depth, reverse=False):
        """FeatureExtrusion3 — 23 参数 (一个不能多/少)"""
        f = self.fm.FeatureExtrusion3(
            True, reverse, False, 0, 0, M(depth), 0.0,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False,
            True, False, True, 0, 0.0, False)
        if f is None:
            raise RuntimeError(f"FeatureExtrusion3 None (d={depth})")
        return f

    def cut(self, depth=0, through_all=False):
        """FeatureCut3 26 参数 — 铁律 Flip=F/NormalCut=F (违反 → 静默失败/反切)。
        Dir 自动重试: 底面草图法向翻转时 Dir=False 朝空气切 → None → 换 Dir=True。"""
        t1 = 1 if through_all else 0
        d1 = 0.001 if through_all else M(depth)
        for direction in (False, True):
            f = self.fm.FeatureCut3(
                True, False, direction, t1, 0, d1, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                False,  # NormalCut=False 铁律!
                True, True, True, True, False,
                0, 0.0, False)
            if f is not None:
                if direction:
                    print("     (cut: Dir 翻转生效)")
                return f
        raise RuntimeError(f"FeatureCut3 双向均 None (d={depth},thru={through_all})")

    def fillet_edges(self, edges_mm, r):
        """边圆角。edges: [(x,y,z)mm 边中点]"""
        self.model.ClearSelection2(True)
        n = 0
        for x, y, z in edges_mm:
            if self.ext.SelectByID2("", "EDGE", M(x), M(y), M(z), True, 1, VN(), 0):
                n += 1
        if n == 0:
            raise RuntimeError("圆角: 0 边选中")
        f = self.fm.FeatureFillet(195, M(r), 0, 0, None, None, None)
        if f is None:
            raise RuntimeError("FeatureFillet None")
        return f

    # ── 保存 (SLDPRT + STEP 成对; 先删旧文件防文件锁 err=1) ──
    def save(self, out_dir, name):
        os.makedirs(out_dir, exist_ok=True)
        sld = os.path.join(out_dir, f"{name}.SLDPRT")
        stp = os.path.join(out_dir, f"{name}.STEP")
        for p in (sld, stp):
            if os.path.exists(p):
                os.remove(p)
        _v(self.model.EditRebuild3)
        ok1 = self.ext.SaveAs(sld, 0, 1, VN(), VBR(), VBR())
        ok2 = self.ext.SaveAs(stp, 0, 1, VN(), VBR(), VBR())  # SaveAs4 STEP 是 4KB 空壳, 禁用
        if not (ok1 and ok2):
            raise RuntimeError(f"保存失败 sld={ok1} stp={ok2}")
        print(f"   ✓ 已保存 {name}.SLDPRT + .STEP")
        return sld, stp
