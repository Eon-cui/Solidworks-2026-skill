"""
sw_mate.py — 程序化面选择 mate 自动化 (SW2026 装配实战验证)
============================================================
铁律 7: SelectByID2 坐标拾取 = 视线射线 (鼠标语义), 装配体内必选错 →
正路: GetBodies3(tuple!) → GetFaces → ISurface 参数匹配 → IEntity.Select4

来源: UR-SEU-2026 add_mates.py (43 配合全部成功, 复验位姿零漂移)。

坑速查:
  - AddMate5 err=1 才是成功; 同零件两面 → err=0 静默失败
  - 同心 mate 只锁径向, 轴向自由 — 转动副 = 同心 + 贴合/距离
  - CylinderParams/PlaneParams 是零件局部系坐标
  - align=2 (closest) 让解算器保持当前位置
"""
import sys
# stdout configured by sw_2026_skill._compat
try:
    from .sw_session import genmod, untuple, _v
except ImportError:
    from sw_session import genmod, untuple, _v

SW_MATE_COINCIDENT = 0
SW_MATE_CONCENTRIC = 1
SW_MATE_DISTANCE = 5
SW_MATE_GEAR = 6
SW_MATE_LOCK = 16


def get_components(asm_model):
    """枚举装配组件 → {Name2: IComponent2(gen_py 包装)}。
    dynamic 下 GetComponents 不可枚举 → 必须 IAssemblyDoc 包装。"""
    MOD = genmod()
    asm_e = MOD.IAssemblyDoc(asm_model._oleobj_)
    comps = {}
    for c in asm_e.GetComponents(False):
        ce = MOD.IComponent2(c._oleobj_)
        comps[ce.Name2] = ce
    return comps


def _iter_faces(comp_e):
    """组件 body 的全部面 (gen_py IFace2)。GetBodies3 early-bound 返回 tuple!"""
    MOD = genmod()
    body = None
    try:
        body = comp_e.GetBody()       # 装配组件下常 None
    except Exception:
        pass
    if body is None:
        bodies = untuple(comp_e.GetBodies3(0, 0))
        if not bodies:
            return
        body = bodies[0]
    be = MOD.IBody2(body._oleobj_)
    faces = be.GetFaces()
    if not faces:
        return
    for f in faces:
        yield MOD.IFace2(f._oleobj_)


def find_cyl_face(comp_e, radius_mm, tol=0.05):
    """按半径找圆柱面 (零件内半径唯一时用)。返回 IFace2 或 None。"""
    MOD = genmod()
    for fe in _iter_faces(comp_e):
        s = MOD.ISurface(fe.GetSurface()._oleobj_)
        if s.IsCylinder() and abs(s.CylinderParams[6] * 1000 - radius_mm) < tol:
            return fe
    return None


def find_cyl_face_at(comp_e, radius_mm, axis_idx, pos_mm, tol=0.05, pos_tol=1.0):
    """同半径多孔: 按轴线**局部坐标**第 axis_idx 维区分 (CylinderParams 是零件局部系!)。
    CylinderParams = [ox,oy,oz, ax,ay,az, r] (米)。"""
    MOD = genmod()
    for fe in _iter_faces(comp_e):
        s = MOD.ISurface(fe.GetSurface()._oleobj_)
        if s.IsCylinder():
            cp = s.CylinderParams
            if abs(cp[6] * 1000 - radius_mm) < tol and abs(cp[axis_idx] * 1000 - pos_mm) < pos_tol:
                return fe
    return None


def find_plane_face(comp_e, axis_idx, pos_mm, tol=0.1):
    """找平面: 法向 ∥ 局部轴 axis_idx (0=X,1=Y,2=Z) 且根点该维 ≈ pos_mm。
    PlaneParams = [nx,ny,nz, px,py,pz] (零件局部系, 米)。"""
    MOD = genmod()
    for fe in _iter_faces(comp_e):
        s = MOD.ISurface(fe.GetSurface()._oleobj_)
        if s.IsPlane():
            pp = s.PlaneParams
            if abs(abs(pp[axis_idx]) - 1.0) < 0.01 and abs(pp[3 + axis_idx] * 1000 - pos_mm) < tol:
                return fe
    return None


def any_face(comp_e):
    """任意一个面 (LOCK mate 用 — LOCK 锁组件相对位姿, 面只是选择载体)"""
    for fe in _iter_faces(comp_e):
        return fe
    return None


def _select_pair(asm_model, face_a, face_b):
    MOD = genmod()
    asm_model.ClearSelection2(True)
    s1 = MOD.IEntity(face_a._oleobj_).Select4(False, None)
    s2 = MOD.IEntity(face_b._oleobj_).Select4(True, None)
    if not (s1 and s2):
        raise RuntimeError(f"Select4 失败 {s1}/{s2}")


def _add_mate(asm_model, mate_type, dist_m=0.0, gear_n=0.0, gear_d=0.0):
    """AddMate5 (15 参数, align=2 closest)。返回 mate 或 raise。
    注意: err=1 成功; 同零件两面 err=0 — 必查!"""
    MOD = genmod()
    asm_e = MOD.IAssemblyDoc(asm_model._oleobj_)
    ret = asm_e.AddMate5(int(mate_type), 2, False,
                         float(dist_m), float(dist_m), float(dist_m),
                         float(gear_n), float(gear_d),
                         0, 0, 0, False, False, 0)
    mate, err = (ret if isinstance(ret, tuple) else (ret, -1))
    if mate is None:
        raise RuntimeError(f"AddMate5 None (type={mate_type}, err={err}) — "
                           "err=0 多为两面同零件 (选面错误)")
    return mate


def add_concentric(asm_model, face_a, face_b):
    """同心配合。⚠ 只锁径向 — 转动副还要 add_coincident/add_distance 锁轴向。"""
    _select_pair(asm_model, face_a, face_b)
    return _add_mate(asm_model, SW_MATE_CONCENTRIC)


def add_coincident(asm_model, face_a, face_b):
    """平面贴合 (轴向定位; 两平面 ⊥ 转轴时不限制旋转)"""
    _select_pair(asm_model, face_a, face_b)
    return _add_mate(asm_model, SW_MATE_COINCIDENT)


def add_distance(asm_model, face_a, face_b, dist_mm):
    """距离配合 (设计间隙)。align=closest → 初始位姿正确则零移动。"""
    _select_pair(asm_model, face_a, face_b)
    return _add_mate(asm_model, SW_MATE_DISTANCE, dist_m=dist_mm / 1000.0)


def add_gear(asm_model, face_a, face_b, ratio_n=1.0, ratio_d=1.0):
    """齿轮配合 (两圆柱面轴) — 转一个另一个按比例转"""
    _select_pair(asm_model, face_a, face_b)
    return _add_mate(asm_model, SW_MATE_GEAR, gear_n=ratio_n, gear_d=ratio_d)


def add_lock_group(asm_model, comps, names):
    """刚性组: 第一个为锚, 其余逐个 LOCK 到锚 (模拟螺栓连接, 拖动不散架)。
    返回成功 LOCK 数。"""
    anchor = comps.get(names[0])
    fa = any_face(anchor) if anchor else None
    if fa is None:
        raise RuntimeError(f"LOCK 锚缺失: {names[0]}")
    n = 0
    for name in names[1:]:
        ce = comps.get(name)
        fb = any_face(ce) if ce else None
        if fb is None:
            print(f"  ✗ LOCK 成员缺失: {name}")
            continue
        _select_pair(asm_model, fa, fb)
        try:
            _add_mate(asm_model, SW_MATE_LOCK)
            n += 1
        except RuntimeError as e:
            print(f"  ✗ LOCK {name}: {e}")
    return n


def fix_component(asm_model, comp_e):
    """组件固定到地 (Base 接地, 整体不漂移)"""
    MOD = genmod()
    asm_e = MOD.IAssemblyDoc(asm_model._oleobj_)
    asm_model.ClearSelection2(True)
    comp_e.Select4(False, None, False)
    asm_e.FixComponent()


def _save_as(asm_model, path):
    """SaveAs 双形态兼容: dynamic 要 VARIANT 包裹, early-bound 要裸参 (返回 tuple)。"""
    try:
        from .sw_session import VN, VBR
    except ImportError:
        from sw_session import VN, VBR
    try:
        return untuple(asm_model.Extension.SaveAs(path, 0, 1, VN(), VBR(), VBR()))
    except Exception:
        return untuple(asm_model.Extension.SaveAs(path, 0, 1, None, 0, 0))


def rebuild_and_save(asm_model, asm_path, also_step=True):
    """重建 + 保存 (含 STEP 重导供位姿复验)。EditRebuild3 是属性 → _v 包装。"""
    asm_model.ClearSelection2(True)
    _v(asm_model.EditRebuild3)
    ok1 = _save_as(asm_model, asm_path)
    ok2 = True
    if also_step:
        step = asm_path.rsplit(".", 1)[0] + ".STEP"
        ok2 = _save_as(asm_model, step)
    if not (ok1 and ok2):
        raise RuntimeError(f"保存失败 asm={ok1} step={ok2}")
    return True
