"""
sw_part.py — 零件建模 (草图 + 特征, SW2026 修复版, 单位: 米)
=============================================================
vs 开源版修复:
  1. extrude_cut: FeatureCut4 ❌ → FeatureCut3 26 参数验证签名 (Flip/Dir/NormalCut=False)
  2. circular_pattern: FeatureCircularPattern4 ❌ → FeatureCircularPattern2;
     但首选单草图策略 (sketch_holes_pcd / sketch_4_holes_rect)
  3. 全部特征函数: 返回 None 必须由调用方检查 (本模块打印警告)

毫米接口 + 面数追踪 → 用 sw_session.SW 类 (推荐)。
"""
import sys
# stdout configured by solidworks_2026_skill._compat
import math
from contextlib import contextmanager

try:
    from .sw_preflight import import_com_dependencies
except ImportError:
    from sw_preflight import import_com_dependencies

pythoncom, _win32com, VARIANT = import_com_dependencies()

PLANE_NAME_ALIASES = {
    "Front Plane": ["Front Plane", "前视基准面"],
    "Top Plane": ["Top Plane", "上视基准面"],
    "Right Plane": ["Right Plane", "右视基准面"],
    "前视基准面": ["前视基准面", "Front Plane"],
    "上视基准面": ["上视基准面", "Top Plane"],
    "右视基准面": ["右视基准面", "Right Plane"],
}

SKETCH_NAME_PREFIX_ALIASES = {"Sketch": "草图", "草图": "Sketch"}


# ============================================================
# 选择封装
# ============================================================

def _empty_callout():
    """SelectByID2 的 Callout 位 — 裸 None 会 TYPEMISMATCH (铁律 4)。"""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _select_by_id(extension, entity_name, entity_type, append=False, mark=0):
    return extension.SelectByID2(
        entity_name, entity_type, 0, 0, 0, append, mark, _empty_callout(), 0)


def _get_plane_name_candidates(plane_name):
    return PLANE_NAME_ALIASES.get(plane_name, [plane_name])


def _get_sketch_name_candidates(sketch_name):
    candidates = [sketch_name]
    for prefix, alias in SKETCH_NAME_PREFIX_ALIASES.items():
        if sketch_name.startswith(prefix):
            alias_name = alias + sketch_name[len(prefix):]
            if alias_name not in candidates:
                candidates.append(alias_name)
    return candidates


def _select_first_candidate(extension, candidate_names, entity_type, append=False, mark=0):
    for name in candidate_names:
        if _select_by_id(extension, name, entity_type, append=append, mark=mark):
            return name
    return None


def _get_selection_count(model):
    sel = model.SelectionManager
    member = getattr(sel, "GetSelectedObjectCount2")
    return member(-1) if callable(member) else int(member)


def _ensure_sketch_selected(model, sketch_name):
    if _get_selection_count(model) > 0:
        return "__current_selection__"
    selected = _select_first_candidate(
        model.Extension, _get_sketch_name_candidates(sketch_name), "SKETCH")
    if not selected:
        raise ValueError(f"无法选择草图: {sketch_name}")
    return selected


def select_face_verified(model, x_m, y_m, z_m, label=""):
    """坐标选面 + SelectionManager 计数复核。
    ⚠ 仅零件内可用 (装配体内是视线射线拾取 → 用 sw_mate)。
    点要避开孔区、偏离面中心 20-30%。"""
    ok = model.Extension.SelectByID2("", "FACE", x_m, y_m, z_m, False, 0, _empty_callout(), 0)
    if not ok:
        print(f"     !! {label}: SelectByID2 False ({x_m:.4f},{y_m:.4f},{z_m:.4f})")
        return False
    if _get_selection_count(model) == 0:
        print(f"     !! {label}: count=0")
        return False
    return True


# ============================================================
# 草图操作 (米)
# ============================================================

def start_sketch(model, plane_name="Front Plane"):
    """在基准面上开草图 (中英文名自动兼容)。"""
    model.ClearSelection2(True)
    selected = _select_first_candidate(
        model.Extension, _get_plane_name_candidates(plane_name), "PLANE")
    if selected:
        model.SketchManager.InsertSketch(True)
        return selected
    raise ValueError(f"无法选择基准面: {plane_name}")


def end_sketch(model):
    model.SketchManager.InsertSketch(True)


@contextmanager
def sketch(model, plane_name="Front Plane"):
    """with sketch(model, "Front Plane") as name: ..."""
    start_sketch(model, plane_name)
    try:
        yield current_sketch_name(model)
    finally:
        end_sketch(model)


def current_sketch_name(model, fallback="Sketch1"):
    active = model.SketchManager.ActiveSketch
    return active.Name if active else fallback


def sketch_line(model, x1, y1, x2, y2):
    return model.SketchManager.CreateLine(x1, y1, 0, x2, y2, 0)


def sketch_rectangle(model, cx, cy, w, h):
    return model.SketchManager.CreateCenterRectangle(cx, cy, 0, cx + w / 2, cy + h / 2, 0)


def sketch_corner_rectangle(model, x1, y1, x2, y2):
    return model.SketchManager.CreateCornerRectangle(x1, y1, 0, x2, y2, 0)


def sketch_circle(model, cx, cy, radius):
    return model.SketchManager.CreateCircleByRadius(cx, cy, 0, radius)


def sketch_arc(model, cx, cy, x1, y1, x2, y2, direction=1):
    return model.SketchManager.CreateArc(cx, cy, 0, x1, y1, 0, x2, y2, 0, direction)


def sketch_polygon(model, cx, cy, radius, sides=6):
    return model.SketchManager.CreatePolygon(cx, cy, 0, cx + radius, cy, 0, sides, True)


def sketch_4_holes_rect(skm, half_spacing_m, radius_m):
    """矩形 4 孔单草图 (规避 FeatureCut4/LinearPattern3 坑)。"""
    hs = half_spacing_m
    for sx, sy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        skm.CreateCircleByRadius(sx * hs, sy * hs, 0.0, radius_m)


def sketch_holes_pcd(model, pcd_radius_m, hole_radius_m, n=4, start_deg=45, cx=0.0, cy=0.0):
    """节圆均布孔单草图 (规避 CircularPattern4 ❌ 的首选方案)。"""
    for k in range(n):
        a = math.radians(start_deg + 360.0 / n * k)
        model.SketchManager.CreateCircleByRadius(
            cx + pcd_radius_m * math.cos(a), cy + pcd_radius_m * math.sin(a), 0, hole_radius_m)


# CreateSpline ❌ (SW2026 Python COM 不暴露) → 多段线近似
def sketch_polyline(model, points, close=False):
    """多段直线近似曲线 (CreateSpline 的替代)。points: [(x,y), ...] 米。"""
    segs = []
    pts = list(points) + ([points[0]] if close else [])
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        segs.append(model.SketchManager.CreateLine(x1, y1, 0, x2, y2, 0))
    return segs


def add_dimension(model, x, y):
    return model.AddDimension2(x, y, 0)


# ============================================================
# 特征操作 (返回 None = 失败, 调用方必查!)
# ============================================================

def extrude_boss(model, sketch_name, depth, direction=True, merge=True):
    """凸台拉伸 (FeatureExtrusion3, 23 参数)。返回 None 必查。"""
    _ensure_sketch_selected(model, sketch_name)
    feat = model.FeatureManager.FeatureExtrusion3(
        True, False, direction, 0, 0, depth, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        merge, False, True, 0, 0.0, False)
    if feat is None:
        print(f"⚠ FeatureExtrusion3 返回 None (depth={depth})")
    return feat


def extrude_cut(model, sketch_name, depth, flip=False):
    """切除拉伸 — FeatureCut3 26 参数 (FeatureCut4 全参数组合静默失败, 禁用)。
    铁律: Dir=False, NormalCut=False (True → 静默失败返回 None);
          flip=True 会反切掉零件主体, 慎用。
    depth=0 表示完全贯穿。返回 None = 失败, 调用方必查!"""
    _ensure_sketch_selected(model, sketch_name)
    if depth == 0:
        end_condition, depth = 1, 0.001       # swEndCondThroughAll
    else:
        end_condition = 0                      # swEndCondBlind

    feat = model.FeatureManager.FeatureCut3(
        True,           # 1 Sd
        flip,           # 2 Flip (True=反切!)
        False,          # 3 Dir (True=静默失败!)
        end_condition,  # 4 T1
        0,              # 5 T2
        depth,          # 6 D1
        0.0,            # 7 D2
        False, False, False, False,   # 8-11 Dchk/Ddir
        0.0, 0.0,                     # 12-13 Dang
        False, False,                 # 14-15 OffsetReverse
        False, False,                 # 16-17 TranslateSurface
        False,          # 18 NormalCut (True=静默失败!)
        True, True, True, True, False,  # 19-23 scope/autoselect
        0, 0.0, False)  # 24-26 T0/StartOffset/FlipStartOffset
    if feat is None:
        print(f"⚠ FeatureCut3 返回 None (depth={depth}) — 切除未生效! "
              "检查草图闭合/选中/方向 (底面草图可重试 sw_session.SW.cut 的 Dir 翻转)")
    return feat


def extrude_midplane(model, sketch_name, total_depth):
    """中面对称拉伸。返回 None 必查。"""
    _ensure_sketch_selected(model, sketch_name)
    feat = model.FeatureManager.FeatureExtrusion3(
        True, False, True, 6, 0, total_depth, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        True, False, True, 0, 0.0, False)
    if feat is None:
        print("⚠ FeatureExtrusion3(midplane) 返回 None")
    return feat


def revolve_boss(model, sketch_name, angle_rad):
    """旋转凸台。FeatureRevolve2 强类型 — 全参数显式转换。返回 None 必查。"""
    _ensure_sketch_selected(model, sketch_name)
    feat = model.FeatureManager.FeatureRevolve2(
        True, True, False, False, False, False,
        0, 0, float(angle_rad), float(0),
        False, False, 0.0, 0.0,
        0, 0, 0, True, True, True)
    if feat is None:
        print("⚠ FeatureRevolve2 返回 None")
    return feat


def fillet(model, radius):
    """圆角 (需预先选边)。返回 None 必查。"""
    feat = model.FeatureManager.FeatureFillet(195, radius, 0, 0, None, None, None)
    if feat is None:
        print(f"⚠ FeatureFillet 返回 None (r={radius})")
    return feat


def chamfer(model, distance, angle_deg=45):
    """倒角 (需预先选边)。返回 None 必查。"""
    angle_rad = angle_deg * math.pi / 180.0
    feat = model.FeatureManager.InsertFeatureChamfer(4, 1, distance, angle_rad, 0, 0, 0, 0)
    if feat is None:
        print(f"⚠ InsertFeatureChamfer 返回 None")
    return feat


def linear_pattern(model, feature_name, d1_x, d1_y, d1_z, d1_spacing, d1_count,
                   d2_x=0, d2_y=0, d2_z=0, d2_spacing=0, d2_count=1):
    """线性阵列。⚠ 不稳定 — 首选单草图策略 (sketch_4_holes_rect)。返回 None 必查。"""
    _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
    feat = model.FeatureManager.FeatureLinearPattern3(
        d1_spacing, d2_spacing, d1_count, d2_count, False, False,
        str(d1_x), str(d1_y), str(d1_z), str(d2_x), str(d2_y), str(d2_z),
        False, False)
    if feat is None:
        print("⚠ FeatureLinearPattern3 返回 None — 改用单草图策略")
    return feat


def circular_pattern(model, feature_name, axis_name, angle_rad, count, equal_spacing=True):
    """圆周阵列 — FeatureCircularPattern2 (Pattern4 在 Python COM 下特征选择失败, 禁用)。
    ⚠ 首选单草图策略 (sketch_holes_pcd 一次画全部实体, 零阵列依赖)。返回 None 必查。"""
    _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
    _select_by_id(model.Extension, axis_name, "AXIS", append=True, mark=1)
    feat = model.FeatureManager.FeatureCircularPattern2(
        count, angle_rad, False, "NULL", False)
    if feat is None:
        print("⚠ FeatureCircularPattern2 返回 None — 改用单草图策略 sketch_holes_pcd")
    return feat


def shell(model, thickness):
    """抽壳 (需预先选要移除的面)。返回 None 必查。"""
    feat = model.FeatureManager.InsertFeatureShell(thickness, False)
    if feat is None:
        print("⚠ InsertFeatureShell 返回 None")
    return feat


def mirror_feature(model, feature_name, mirror_plane_name):
    """镜像特征。返回 None 必查。"""
    _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
    _select_by_id(model.Extension, mirror_plane_name, "PLANE", append=True, mark=1)
    feat = model.FeatureManager.InsertMirrorFeature2(False, False, False, False, 0)
    if feat is None:
        print("⚠ InsertMirrorFeature2 返回 None")
    return feat


def rib(model, sketch_name, thickness, direction=True):
    """筋特征。返回 None 必查。"""
    _ensure_sketch_selected(model, sketch_name)
    feat = model.FeatureManager.InsertRib(
        direction, False, thickness, 0, False, False, False, 0, False)
    if feat is None:
        print("⚠ InsertRib 返回 None")
    return feat
