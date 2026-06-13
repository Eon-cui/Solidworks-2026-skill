"""
sw_verify.py — STEP 几何验收 + 面数验证 + 装配位姿验证 + 7D3S 自动评分
=====================================================================
铁律 3: 控制台 OK ≠ 特征生效。验收强度匹配交付物维度:
  零件   → verify_step (圆柱面半径分布 + 外径/包围盒)
  装配体 → verify_assembly_poses (ITEM_DEFINED_TRANSFORMATION 第一 placement)
  特征   → count_faces (建模过程中用 sw_session.SW.check_faces)

换算: 1 孔 = 2 半圆柱面 (内部已 //2); 1 圆角 = 1 圆柱面。
"""
import sys
# stdout configured by sw_2026_skill._compat
import os
import re
import time
import hashlib
from collections import Counter


# ── 零件级: STEP 圆柱面半径分布 ──

def verify_step(step_path, expected_holes, bbox=None, max_circle=None, tol=0.6):
    """
    expected_holes: [(radius_mm, count, name), ...]   1 孔 = 2 半圆柱面 (已换算)
    bbox: (dx,dy,dz) 期望包围盒 — ⚠ 圆盘类零件圆周无显式点, 勿用
    max_circle: 期望最大圆半径 mm (盘类外径验证, 替代 bbox)
    返回 (ok, report)
    """
    with open(step_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    cyls = re.findall(
        r"CYLINDRICAL_SURFACE\s*\(\s*'[^']*'\s*,\s*#\d+\s*,\s*([\d.E+-]+)\s*\)", text)
    radii = Counter(round(float(r), 2) for r in cyls)

    lines, ok = [], True
    for r, n_want, name in expected_holes:
        got = radii.get(round(r, 2), 0) // 2
        good = got == n_want
        ok = ok and good
        lines.append(f"  {name} R{r}: {got}/{n_want} {'✅' if good else '❌'}")

    if max_circle is not None:
        circles = re.findall(r"CIRCLE\s*\(\s*'[^']*'\s*,\s*#\d+\s*,\s*([\d.E+-]+)\s*\)", text)
        rmax = max((float(c) for c in circles), default=0)
        good = abs(rmax - max_circle) < tol
        ok = ok and good
        lines.append(f"  最大圆 R{rmax:.1f} (期望{max_circle}) {'✅' if good else '❌'}")

    if bbox:
        pts = re.findall(
            r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([^)]+)\s*\)\s*\)", text)
        xs, ys, zs = [], [], []
        for m_ in pts:
            try:
                nums = [float(x) for x in m_.split(",")]
                if len(nums) >= 3:
                    xs.append(nums[0]); ys.append(nums[1]); zs.append(nums[2])
            except ValueError:
                pass
        got_box = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        good = all(abs(g - w) < tol for g, w in zip(sorted(got_box), sorted(bbox)))
        ok = ok and good
        lines.append(f"  BBox: {got_box[0]:.1f}×{got_box[1]:.1f}×{got_box[2]:.1f} "
                     f"(期望{bbox[0]}×{bbox[1]}×{bbox[2]}) {'✅' if good else '❌'}")

    report = "\n".join(lines) + f"\n  ═══ {'✅ PASS' if ok else '❌ FAIL'} ═══"
    return ok, report


def count_faces(model):
    """活动零件实体面数 (建模中 L2 防御)。"""
    def _v(x): return x() if callable(x) else x
    bodies = model.GetBodies2(0, True)
    return sum(_v(b.GetFaceCount) for b in bodies) if bodies else 0


# ── 装配级: STEP 位姿验证 ──

def _parse_step_entities(text):
    ents = {}
    for m in re.finditer(r"#(\d+)\s*=\s*(\w+)\s*\((.*)\)\s*;", text):
        ents[int(m.group(1))] = (m.group(2), m.group(3))
    return ents


def _placement(ents, pid):
    typ, body = ents.get(pid, ("", ""))
    if typ != "AXIS2_PLACEMENT_3D":
        return None
    refs = [int(x) for x in re.findall(r"#(\d+)", body)]
    _, cbody = ents.get(refs[0], ("", ""))
    cm = re.search(r"\(\s*([\d.E+-]+)\s*,\s*([\d.E+-]+)\s*,\s*([\d.E+-]+)\s*\)", cbody)
    if not cm:
        return None
    origin = tuple(float(cm.group(i)) for i in (1, 2, 3))
    axis = None
    if len(refs) > 1:
        _, dbody = ents.get(refs[1], ("", ""))
        dm = re.search(r"\(\s*([\d.E+-]+)\s*,\s*([\d.E+-]+)\s*,\s*([\d.E+-]+)\s*\)", dbody)
        if dm:
            axis = tuple(float(dm.group(i)) for i in (1, 2, 3))
    return origin, axis


def read_assembly_poses(step_path):
    """装配 STEP → [(origin_mm, z_axis), ...]。
    坑: 组件位姿在 ITEM_DEFINED_TRANSFORMATION 的**第一个** placement (第二个是恒等参考系)。"""
    with open(step_path, encoding="utf-8", errors="ignore") as f:
        ents = _parse_step_entities(f.read())
    poses = []
    for eid, (typ, body) in ents.items():
        if typ != "ITEM_DEFINED_TRANSFORMATION":
            continue
        refs = [int(x) for x in re.findall(r"#(\d+)", body)]
        if refs:
            pa = _placement(ents, refs[0])
            if pa:
                poses.append(pa)
    return poses


def verify_assembly_poses(step_path, expected, tol_mm=0.1, tol_axis=0.01):
    """
    expected: [(label, R_rows_3x3, t_mm), ...]  — 与装配 LAYOUT 同源
    比对: origin ±tol_mm + 组件局部 Z 轴世界方向 (R 第三行) ±tol_axis
    返回 (n_match, n_all, report)
    """
    poses = read_assembly_poses(step_path)
    lines = [f"  STEP 装配位姿: {len(poses)} 个"]
    n_match, used = 0, set()
    for label, R, t in expected:
        zrow = tuple(float(v) for v in R[2])
        found = False
        for i, (origin, axis) in enumerate(poses):
            if i in used:
                continue
            if all(abs(origin[k] - t[k]) < tol_mm for k in range(3)):
                if axis is None or all(abs(axis[k] - zrow[k]) < tol_axis for k in range(3)):
                    used.add(i)
                    found = True
                    break
        n_match += found
        if not found:
            lines.append(f"  ❌ {label}: 期望 t={t} z={zrow} 未匹配")
    lines.append(f"  位姿匹配: {n_match}/{len(expected)} "
                 + ("✅ PASS" if n_match == len(expected) else "❌ FAIL"))
    return n_match, len(expected), "\n".join(lines)


# ── 7D3S 自动评分 (S1 文件级 / S2 STEP 几何级) ──

def score_s1(sldprt_path, gen_seconds=None, md5_list=None):
    """S1 → D4 文件有效性 / D5 建模效率 / D6 可重复性 (能算多少算多少)"""
    scores = {}
    if not os.path.exists(sldprt_path):
        scores["D4"] = 0
    else:
        kb = os.path.getsize(sldprt_path) / 1024
        scores["D4"] = 5 if kb >= 100 else 4 if kb >= 50 else 2 if kb > 10 else 1
    if gen_seconds is not None:
        t = gen_seconds
        scores["D5"] = 5 if t < 10 else 4 if t < 30 else 3 if t < 60 else 2 if t < 120 else 1
    if md5_list:
        if len(set(md5_list)) == 1 and len(md5_list) >= 3:
            scores["D6"] = 5
        elif len(md5_list) >= 2:
            scores["D6"] = 2
        else:
            scores["D6"] = 1
    return scores


def score_s2(step_path, expected_od_mm=None, expected_thick_mm=None):
    """S2 → D1 几何完整性 / D2 尺寸精度"""
    scores = {}
    try:
        with open(step_path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return {"D1": 0, "D2": 0}
    n_pts = text.count("CARTESIAN_POINT")
    has_shell = "CLOSED_SHELL" in text
    if has_shell and n_pts > 1000:
        scores["D1"] = 5
    elif has_shell and n_pts > 50:
        scores["D1"] = 4
    elif has_shell:
        scores["D1"] = 3
    elif n_pts:
        scores["D1"] = 2
    else:
        scores["D1"] = 1
    if expected_od_mm is not None:
        circles = [float(c) for c in re.findall(
            r"CIRCLE\s*\(\s*'[^']*'\s*,\s*#\d+\s*,\s*([\d.E+-]+)\s*\)", text)]
        dev = abs(max(circles, default=0) * 2 - expected_od_mm)
        scores["D2"] = (5 if dev < 0.2 else 4 if dev < 0.5 else 3 if dev < 1.0
                        else 2 if dev < 2.0 else 1 if dev < 5.0 else 0)
    return scores


def verdict_7d3s(scores):
    """一票否决 + 总分判定。scores: {D1..D7: int}。"""
    if any(v == 0 for v in scores.values()):
        return "REJECT", "一票否决: " + ",".join(k for k, v in scores.items() if v == 0)
    total = sum(scores.values())
    full = 5 * len(scores)
    if len(scores) == 7:
        tag = ("PASS-EXCELLENT" if total >= 28 else "PASS" if total >= 24
               else "CONDITIONAL" if total >= 18 else "REJECT")
    else:
        tag = "PARTIAL"  # 未评满 7 维只给参考分
    return tag, f"{total}/{full}"


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
