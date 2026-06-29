"""
sw_check_interfaces.py — 跨零件接口交叉校验 (STEP 解析, 不需要 SW 运行)
======================================================================
场景: 接口参数 (PCD/孔径/方距) 散落在多个零件 — 人工比对不可靠。
模式: 每个零件 STEP 解析圆柱面轴心 → 按半径+轴向取孔心 → 算 PCD/角度 → 配对断言。

铁律: 接口检查必须随设计版本同跑 (改接口 → build 脚本+期望值+文档三处同步 → 跑校验)。
陈年失配案例: 孔从 A 零件移到 B 零件后, 校验脚本 3 个版本还在查 A — 一直"假 PASS"。

用法 (写你自己的 check 脚本):
    from sw_check_interfaces import cyl_axes, hole_centers, pcd_and_angle, Checker
    ck = Checker()
    a = cyl_axes("PartA.STEP")
    pcd, ang = pcd_and_angle(hole_centers(a, 1.75, "Y"))
    ck.eq("PartA 输出 PCD", pcd, 36)
    ck.eq("PartA 角度", ang, 45, tol=0.5)
    ck.report()
"""
import sys
# stdout configured by solidworks_2026_skill._compat
import re
import math

_AXIS_IDX = {"X": (3, (1, 2)), "Y": (4, (0, 2)), "Z": (5, (0, 1))}


def cyl_axes(step_path):
    """STEP → [(radius_mm, cx, cy, cz, ax, ay, az), ...] 全部圆柱面轴。"""
    with open(step_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    ents = {}
    for m in re.finditer(r"#(\d+)\s*=\s*(\w+)\s*\((.*)\)\s*;", text):
        ents[int(m.group(1))] = (m.group(2), m.group(3))
    out = []
    for eid, (typ, body) in ents.items():
        if typ != "CYLINDRICAL_SURFACE":
            continue
        m = re.match(r"\s*'[^']*'\s*,\s*#(\d+)\s*,\s*([\d.E+-]+)", body)
        if not m:
            continue
        place_id, radius = int(m.group(1)), float(m.group(2))
        ptyp, pbody = ents.get(place_id, ("", ""))
        if ptyp != "AXIS2_PLACEMENT_3D":
            continue
        refs = [int(x) for x in re.findall(r"#(\d+)", pbody)]
        if len(refs) < 2:
            continue
        _, cbody = ents.get(refs[0], ("", ""))
        cm = re.search(r"\(\s*([\d.E+-]+)\s*,\s*([\d.E+-]+)\s*,\s*([\d.E+-]+)\s*\)", cbody)
        _, dbody = ents.get(refs[1], ("", ""))
        dm = re.search(r"\(\s*([\d.E+-]+)\s*,\s*([\d.E+-]+)\s*,\s*([\d.E+-]+)\s*\)", dbody)
        if not (cm and dm):
            continue
        cx, cy, cz = (float(cm.group(i)) for i in (1, 2, 3))
        dx, dy, dz = (float(dm.group(i)) for i in (1, 2, 3))
        out.append((round(radius, 2), cx, cy, cz, dx, dy, dz))
    return out


def hole_centers(axes, r_mm, axis="Y", near=None, within=None, tol=0.01, merge=0.2):
    """指定半径+轴向的孔心 2D 投影坐标 (去重: 1 孔 2 半圆柱面同轴心)。
    axes: cyl_axes() 输出 | axis: 孔轴方向 "X"/"Y"/"Z"
    near/within: 只取距 near 点 within 半径内的孔 (区分 IN/OUT 孔群)"""
    di, (i1, i2) = _AXIS_IDX[axis]
    pts = []
    for r, cx, cy, cz, dx, dy, dz in axes:
        if abs(r - r_mm) >= tol:
            continue
        d = (dx, dy, dz)
        if abs(abs(d[di - 3]) - 1.0) > 0.01:
            continue
        c = (cx, cy, cz)
        p = (c[i1], c[i2])
        if near is not None and within is not None:
            if math.dist(p, near) > within:
                continue
        if not any(math.dist(p, q) < merge for q in pts):
            pts.append(p)
    return pts


def pcd_and_angle(pts):
    """孔群 → (节圆直径, 起始角度°)。孔群质心为圆心。"""
    if not pts:
        return None, None
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    rs = [math.dist(p, (cx, cy)) for p in pts]
    pcd = round(sum(rs) / len(rs) * 2, 2)
    angs = sorted(round(math.degrees(math.atan2(p[1] - cy, p[0] - cx))) % 90 for p in pts)
    return pcd, angs[0] if angs else None


class Checker:
    """断言收集器 + 报告。"""

    def __init__(self, title="接口交叉校验"):
        self.title = title
        self.results = []
        print("═" * 62 + f"\n {title}\n" + "═" * 62)

    def eq(self, label, got, want, tol=0.1):
        ok = got is not None and abs(got - want) <= tol
        self.results.append(ok)
        print(f"  {'✅' if ok else '❌'} {label}: {got} (期望 {want})")
        return ok

    def true(self, label, cond):
        self.results.append(bool(cond))
        print(f"  {'✅' if cond else '❌'} {label}")
        return bool(cond)

    def section(self, name):
        print(f"\n[{name}]")

    def report(self):
        n, total = sum(self.results), len(self.results)
        ok = n == total
        print("\n" + "═" * 62)
        print(f" 结果: {n}/{total} " + ("✅ 全部接口配对一致" if ok else "❌ 有失配!"))
        print("═" * 62)
        return ok
