"""
sw_session.py — SW2026 会话管理 (with 模式 + 清场 + 面数追踪 + COM 模式四件套)
==============================================================================
来源: UR-SEU-2026 swlib.py (35+ 零件实战验证)。
铁律内置:
  1. FeatureCut3 26参数 Flip=F/Dir=F/NormalCut=F, None 必 raise
  2. 开工 CloseAllDocuments, 收工 QuitDoc
  3. 每features面数追踪
  4. GetActiveObject 优先 (Dispatch 每次开新 SW 实例)
注意: SW 类的草图/features接口用 **毫米** (内部转米); 底层 sw_part.py 用米。
"""
import sys
# stdout configured by solidworks_2026_skill._compat
import os
import math
import time
import pythoncom
from win32com.client import GetActiveObject, VARIANT
from solidworks_2026_skill._com_helpers import (
    VN, VBR, mm, deg, _v, genmod, early, put_object_property, untuple,
    SW_TYPELIB, DISPID_TRANSFORM2,
)
M = mm  # legacy alias — 保持向后兼容

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


# ── COM 模式四件套 (references/com-patterns.md) ──
# VN/VBR/mm/deg/_v/genmod/early/put_object_property/untuple 从 _com_helpers 导入


class SW:
    """SolidWorks 零件建模会话。with 语句保证窗口清理。坐标/尺寸全部毫米。"""

    def __init__(self, part_name="part"):
        self.part_name = part_name
        self.faces_log = []

    def __enter__(self):
        self.sw = connect()
        self.sw.CloseAllDocuments(True)          # 铁律: 清场
        from solidworks_2026_skill.sw_connect import find_template as _find_tpl
        tpl = _find_tpl(self.sw, "part")
        self.model = self.sw.NewDocument(tpl, 0, 0, 0) or _v(self.sw.ActiveDoc)
        if self.model is None:
            raise RuntimeError("NewDocument failed (bad template path?)")
        self.ext = self.model.Extension
        self.skm = self.model.SketchManager
        self.fm = self.model.FeatureManager
        print(f"[{self.part_name}] SW session started, cleaned")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.sw.QuitDoc(_v(self.model.GetTitle))   # 铁律: 关窗口
            print(f"[{self.part_name}] window closed")
        except Exception:
            pass
        finally:
            try:
                pythoncom.CoUninitialize()
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
            raise RuntimeError(f"{label}: faces {prev}→{n}, delta={n-prev} — feature may be ineffective!")
        print(f"   ✓ {label} faces={n}")

    # ── 选择 ──
    def plane(self, names=("Front Plane", "Top Plane", "Right Plane",
                        "前视基准面", "上视基准面", "右视基准面")):
        for nm in names:
            if self.ext.SelectByID2(nm, "PLANE", 0, 0, 0, False, 0, VN(), 0):
                return
        raise RuntimeError(f"Plane selection failed: {names}")

    def face(self, x, y, z, label=""):
        """坐标选面 (mm)。内置 13 点重试: 中心→4向偏置→8向偏置。
        ⚠ 仅零件内可用; 装配体内禁用 (用 sw_mate 程序化选择)。"""
        offsets = [
            (0, 0, 0), (10, 0, 0), (-10, 0, 0), (0, 0, 10), (0, 0, -10),
            (20, 0, 0), (-20, 0, 0), (0, 0, 20), (0, 0, -20),
            (20, 0, 20), (-20, 0, -20), (20, 0, -20), (-20, 0, 20),
        ]
        for dx, dy, dz in offsets:
            xx, yy, zz = M(x + dx), M(y + dy), M(z + dz)
            if self.ext.SelectByID2("", "FACE", xx, yy, zz, False, 0, VN(), 0):
                if dx != 0 or dy != 0 or dz != 0:
                    print(f"     (face: offset ({dx},{dy},{dz})mm hit)")
                return
        raise RuntimeError(f"Face selection failed: {label} at ({x},{y},{z})mm")

    # ── 草图 (毫米) ──
    def sketch_on_plane(self, names=("上视基准面", "Top Plane")):
        self.plane(names)
        self.model.InsertSketch2(True)
        self.model.ClearSelection2(True)

    def sketch_on_face(self, x, y, z, label=""):
        """在零件面上开草图。⚠ Prefer sketch_on_plane() for new features.
        This method uses coordinate ray-casting which may miss faces if the
        point lands on a hole or edge. See troubleshooting.md §I for help."""
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

    # ── features (参数来自 _com_signatures 单一事实来源) ──
    def extrude(self, depth, reverse=False):
        """FeatureExtrusion3。参数委托 _com_signatures.feature_extrusion3_params。
        NOTE: 不委托 sw_part.extrude_boss — 后者需要 sketch_name 且 direction≠reverse 语义。"""
        from solidworks_2026_skill._com_signatures import feature_extrusion3_params
        params = feature_extrusion3_params(depth_m=M(depth), reverse=reverse, merge=True)
        f = self.fm.FeatureExtrusion3(*params)
        if f is None:
            raise RuntimeError(f"FeatureExtrusion3 None (d={depth})")
        return f

    def cut(self, depth=0, through_all=False):
        """FeatureCut3 — 参数委托 _com_signatures.feature_cut3_params。
        4 路重试: (flip, direction) 矩阵。Flip=True 仅最后手段(可能反切主体!)
        NOTE: 不委托 sw_part.extrude_cut — 后者需要 sketch_name 且无方向重试。"""
        from solidworks_2026_skill._com_signatures import feature_cut3_params
        d_m = M(depth)
        for flip, direction in [(False,False), (False,True), (True,False), (True,True)]:
            params = feature_cut3_params(
                through_all=through_all, depth_m=d_m,
                flip=flip, normal_cut=False, dir_flag=direction)
            f = self.fm.FeatureCut3(*params)
            if f is not None:
                if flip or direction:
                    print(f"     (cut: flip={flip} dir={direction})")
                if flip:
                    print("     ⚠ Flip=True activated — verify geometry with verify_step!")
                return f
        raise RuntimeError(f"FeatureCut3 failed all 4 directions (d={depth}, thru={through_all})")

    def fillet_edges(self, edges_mm, r):
        """边圆角。edges: [(x,y,z)mm 边中点]"""
        self.model.ClearSelection2(True)
        n = 0
        for x, y, z in edges_mm:
            if self.ext.SelectByID2("", "EDGE", M(x), M(y), M(z), True, 1, VN(), 0):
                n += 1
        if n == 0:
            raise RuntimeError("Fillet: 0 edges selected")
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
            raise RuntimeError(f"Save failed: sldprt={ok1} step={ok2}")
        print(f"   ✓ Saved {name}.SLDPRT + .STEP")
        return sld, stp

    def snapshot(self, out_dir: str, name: str) -> list[str]:
        """强制视觉复核 — 标准 4 视图 PNG。依赖 Pillow。"""
        from solidworks_2026_skill.sw_snapshot import capture_views
        return capture_views(self.model, out_dir, name)
