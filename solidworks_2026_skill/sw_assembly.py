"""
sw_assembly.py — 装配体操作 (SW2026 修复版)
============================================
vs 开源版核心差异:
  1. ★ add_component_posed(): AddComponent5 只给平移 → Transform2 必须
     DISPATCH_PROPERTYPUTREF 补旋转 (开源版裸 AddComponent4 → 姿态全错事故)
  2. apply_component_transform: 开源版 `component.Transform2 = t` 赋值在
     makepy 下"找不到成员" → PUTREF 版
  3. 保留开源版验证可用的: resolve_component / find_largest_cylinder_face /
     add_mate5_checked / gear mate / features树遍历

精确 mate (多实例/同半径多孔/局部坐标过滤) → 用 sw_mate.py。
"""
import sys
# stdout configured by solidworks_2026_skill._compat
import glob
import os
import math
import pythoncom
from win32com.client import VARIANT

try:
    from ._com_helpers import VN, VBR, M, _v, genmod, early, put_object_property, untuple, DISPID_TRANSFORM2, get_com_member
except ImportError:
    from _com_helpers import VN, VBR, M, _v, genmod, early, put_object_property, untuple, DISPID_TRANSFORM2, get_com_member

SW_MATE_COINCIDENT = 0
SW_MATE_CONCENTRIC = 1
SW_MATE_PARALLEL = 3
SW_MATE_DISTANCE = 5
SW_MATE_GEAR = 6
SW_MATE_LOCK = 16
SW_ADD_MATE_ERROR_NO_ERROR = 1


def new_assembly(sw):
    """新建装配体 (模板 glob 兜底)。"""
    hits = glob.glob(r"C:\ProgramData\SolidWorks\SOLIDWORKS *\templates\*.asmdot")
    if not hits:
        raise FileNotFoundError("Assembly template *.asmdot not found")
    asm = sw.NewDocument(hits[0], 0, 0, 0) or _v(sw.ActiveDoc)
    if asm is None:
        raise RuntimeError("NewDocument(assembly) failed")
    return asm


# ── ★ 位姿级插入 (核心修复) ──

def make_transform(sw, R_rows, t_mm):
    """构造 MathTransform。R_rows: 3×3 行约定 (p_world = p_local·R + t), t_mm 毫米。
    数组: [r11..r33, tx,ty,tz(米!), scale=1, 0,0,0]。
    MathUtility 必须 gen_py 包装 (dynamic 下 CreateTransform 找不到成员)。"""
    mu = early(sw.GetMathUtility(), "IMathUtility")
    arr = ([float(R_rows[i][j]) for i in range(3) for j in range(3)]
           + [M(t_mm[0]), M(t_mm[1]), M(t_mm[2]), 1.0, 0.0, 0.0, 0.0])
    return mu.CreateTransform(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, arr))


def add_component_posed(asm, sw, path, R_rows, t_mm):
    """插入组件并设置完整位姿。
    AddComponent5 只接受平移 → Transform2 PUTREF (DISPID 78) 补旋转。
    返回 IComponent2; Failed raise。"""
    comp = asm.AddComponent5(path, 0, "", False, "", M(t_mm[0]), M(t_mm[1]), M(t_mm[2]))
    if comp is None:
        raise RuntimeError(f"AddComponent5 failed: {path}")
    put_object_property(comp, DISPID_TRANSFORM2, make_transform(sw, R_rows, t_mm))
    return comp


def apply_component_transform(comp, sw, R_rows, t_mm):
    """修改已有组件位姿 (PUTREF 版 — 开源版的 `comp.Transform2 = t` 会找不到成员)。"""
    put_object_property(comp, DISPID_TRANSFORM2, make_transform(sw, R_rows, t_mm))


def preload_parts(sw, paths):
    """批量插入前预打开零件 (大幅提速)。返回打开数。"""
    opened = set()
    for p in paths:
        if p not in opened and os.path.exists(p):
            sw.OpenDoc6(p, 1, 1, "", 0, 0)
            opened.add(p)
    return len(opened)


# ── 组件解析 (开源版保留) ──

def resolve_component(component, state=2):
    """组件解析为 FullyResolved(2); 失败回退 Resolved(3)。轻化组件 GetModelDoc2 会 None。"""
    if component is None:
        raise ValueError("Component must not be None/empty")
    try:
        return component.SetSuppression2(state)
    except Exception:
        if state != 3:
            return component.SetSuppression2(3)
        raise


def get_component_model(component, resolve=True):
    if resolve:
        resolve_component(component)
    model = get_com_member(component, "GetModelDoc2")
    if model is None:
        raise RuntimeError(f"Component not resolved: {get_com_member(component, 'Name2')}")
    return model


def get_assembly_entity(component, feature_or_face):
    """零件内对象 → 当前组件实例的装配体上下文 (GetCorresponding)。"""
    entity = component.GetCorresponding(feature_or_face)
    if entity is None:
        raise RuntimeError(f"Failed to map assembly context: {get_com_member(component, 'Name2')}")
    return entity


def find_largest_cylinder_face(component, min_radius=0.0, max_radius=None, resolve=True):
    """组件中半径范围内面积最大的圆柱面 → 装配上下文 IFace2。
    ⚠ 多实例同零件/同半径多孔需精确指定时 → 用 sw_mate.find_cyl_face_at。"""
    part = get_component_model(component, resolve=resolve)
    max_radius = float("inf") if max_radius is None else float(max_radius)
    best_face, best_area = None, -1.0
    bodies = get_com_member(part, "GetBodies2", 0, False) or []
    for body in bodies:
        for face in (get_com_member(body, "GetFaces") or []):
            surface = get_com_member(face, "GetSurface")
            if not surface:
                continue
            try:
                if not get_com_member(surface, "IsCylinder"):
                    continue
                radius = float(get_com_member(surface, "CylinderParams")[6])
                if radius < min_radius or radius > max_radius:
                    continue
                area = float(get_com_member(face, "GetArea"))
                if area > best_area:
                    best_area, best_face = area, face
            except Exception:
                continue
    if best_face is None:
        raise RuntimeError(f"Cylindrical face not found: {get_com_member(component, 'Name2')}")
    return get_assembly_entity(component, best_face)


def select_entities_for_mate(model, entity1, entity2, mark=1):
    model.ClearSelection2(True)
    if not entity1.Select2(False, mark):
        raise RuntimeError("Failed to select first mate entity")
    if not entity2.Select2(True, mark):
        raise RuntimeError("Failed to select second mate entity")
    count = model.SelectionManager.GetSelectedObjectCount2(-1)
    if count != 2:
        model.ClearSelection2(True)
        raise RuntimeError(f"Wrong mate selection count: {count} != 2")
    return True


def add_mate5_checked(asm_model, mate_type, align=2, flip=False, distance=0.0,
                      gear_num=0.0, gear_den=0.0, lock_rotation=False, name=None):
    """AddMate5 (15 参数) + 错误码检查。
    坑: err=1 成功; 同零件两面 → mate=None & err=0 静默Failed — 此处会 raise。"""
    error_status = VBR()
    mate = asm_model.AddMate5(
        int(mate_type), int(align), bool(flip),
        float(distance), float(distance), float(distance),
        float(gear_num), float(gear_den),
        0.0, 0.0, 0.0, False, bool(lock_rotation), 0, error_status)
    if isinstance(mate, tuple):       # early-bound 返回 (mate, err)
        mate, err = mate
    else:
        err = error_status.value
    if mate is None:
        raise RuntimeError(f"AddMate5 failed: type={mate_type}, err={err} "
                           "(err=0 often means both faces on same component)")
    if name:
        try:
            mate.Name = name
        except Exception:
            pass
    asm_model.ClearSelection2(True)
    return mate


def add_concentric_mate_by_cylinders(asm_model, comp_a, comp_b,
                                     radius_a=None, radius_b=None,
                                     name=None, lock_rotation=False):
    """两组件最大圆柱面同心 (简单两件场景)。⚠ 不锁轴向 — 转动副要补贴合/距离。"""
    radius_a = radius_a or (0.0, None)
    radius_b = radius_b or (0.0, None)
    fa = find_largest_cylinder_face(comp_a, radius_a[0], radius_a[1])
    fb = find_largest_cylinder_face(comp_b, radius_b[0], radius_b[1])
    select_entities_for_mate(asm_model, fa, fb)
    return add_mate5_checked(asm_model, SW_MATE_CONCENTRIC,
                             lock_rotation=lock_rotation, name=name)


def add_gear_mate_by_cylinders(asm_model, comp_a, comp_b, teeth_a, teeth_b,
                               radius_a=None, radius_b=None, name=None):
    if float(teeth_a) == 0 or float(teeth_b) == 0:
        raise ValueError("Gear tooth count / ratio must not be 0")
    radius_a = radius_a or (0.0, None)
    radius_b = radius_b or (0.0, None)
    fa = find_largest_cylinder_face(comp_a, radius_a[0], radius_a[1])
    fb = find_largest_cylinder_face(comp_b, radius_b[0], radius_b[1])
    select_entities_for_mate(asm_model, fa, fb)
    return add_mate5_checked(asm_model, SW_MATE_GEAR,
                             gear_num=float(teeth_a), gear_den=float(teeth_b), name=name)


# ── features树 / 验证 ──

def iter_feature_tree(model, include_subfeatures=True):
    """遍历features树。FirstFeature dynamic ❌ → gen_py 包装 ✅。"""
    MOD = genmod()
    me = MOD.IModelDoc2(model._oleobj_)
    feature = me.FirstFeature()

    def walk_sub(parent, depth):
        sub = get_com_member(parent, "GetFirstSubFeature")
        while sub:
            yield sub, depth
            if include_subfeatures:
                yield from walk_sub(sub, depth + 1)
            sub = get_com_member(sub, "GetNextSubFeature")

    while feature:
        yield feature, 0
        if include_subfeatures:
            yield from walk_sub(feature, 1)
        feature = get_com_member(feature, "GetNextFeature")


def collect_mate_feature_summary(model):
    """收集 MateGroup 及子 Mate — 验证真实配合写入features树 (不是脚本假动画)。"""
    result = []
    for feature, depth in iter_feature_tree(model):
        name = get_com_member(feature, "Name")
        type_name = str(get_com_member(feature, "GetTypeName2"))
        if type_name == "MateGroup" or type_name.startswith("Mate") or "配合" in str(name):
            result.append({"name": name, "type": type_name, "depth": depth})
    return result


def get_interference_count(asm_model):
    """干涉检查计数。"""
    itf = asm_model.InterferenceDetection
    itf.TreatSubAssembliesAsComponents = False
    itf.TreatCoincidenceAsInterference = False
    itf.Done()
    return itf.GetInterferenceCount()
