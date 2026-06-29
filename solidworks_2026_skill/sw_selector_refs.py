"""
sw_selector_refs.py — STEP 圆柱面选择器发现
=============================================
复用 sw_verify._parse_step_entities + _placement，
从 STEP 中自动发现圆柱面并按几何features分配 #h1/#b1 标签。

只做圆柱面 (CYLINDRICAL_SURFACE)，不做平面 (PLANE 无边界信息)。
"""
import sys
# stdout configured by solidworks_2026_skill._compat
import os
import re
import json
from collections import defaultdict

from solidworks_2026_skill.sw_verify import _parse_step_entities, _placement


# ── 启发式阈值 ──

HOLE_MAX_RADIUS = 20.0  # 半径 < 此值 = 孔 (h)


def discover_refs(step_path: str) -> dict:
    """
    STEP → entity map → CYLINDRICAL_SURFACE → _placement → 标签。

    返回:
      { "h1": {"radius": r, "origin": (x,y,z), "axis": (dx,dy,dz)},
        "b1": {...}, ... }

    排序: (radius, axis_idx, coord) — 同半径同轴同坐标方向定序。
    axis_idx: 0=X, 1=Y, 2=Z (轴向最近主轴的索引)
    """
    with open(step_path, encoding="utf-8", errors="ignore") as f:
        ents = _parse_step_entities(f.read())

    cylinders = []
    for eid, (typ, body) in ents.items():
        if typ != "CYLINDRICAL_SURFACE":
            continue
        m = re.match(r"\s*'[^']*'\s*,\s*#(\d+)\s*,\s*([\d.E+\-]+)\s*", body)
        if not m:
            continue
        axis2_id = int(m.group(1))
        radius = float(m.group(2))
        placement = _placement(ents, axis2_id)
        if placement is None:
            continue
        origin, axis = placement
        if origin is None:
            continue
        # Determine dominant axis index
        if axis is not None:
            ax = tuple(abs(float(v)) for v in axis)
            axis_idx = ax.index(max(ax)) if max(ax) > 0.9 else 1
        else:
            axis_idx = 1  # default Y-up
        cylinders.append({
            "radius": round(radius, 2),
            "origin": tuple(round(float(o), 4) for o in origin),
            "axis": tuple(round(float(a), 4) for a in axis) if axis else None,
            "axis_idx": axis_idx,
        })

    # Deduplicate: 1 hole = 2 semi-cylindrical faces → group by (radius, origin±tol)
    def _dedup_key(c, tol=0.5):
        ax = c["axis_idx"]
        return (c["radius"], ax, round(c["origin"][ax], 1),
                tuple(round(c["origin"][i], 1) for i in range(3) if i != ax))

    seen = set()
    unique = []
    for c in cylinders:
        dk = _dedup_key(c)
        if dk not in seen:
            seen.add(dk)
            unique.append(c)

    # Group: hole (< threshold) vs boss (>= threshold)
    holes = [c for c in unique if c["radius"] < HOLE_MAX_RADIUS]
    bosses = [c for c in unique if c["radius"] >= HOLE_MAX_RADIUS]

    # Sort key: (radius, axis_idx, coordinate along axis, other coordinates)
    def _sort_key(c):
        ax = c["axis_idx"]
        coord_along = c["origin"][ax]
        other_coords = tuple(c["origin"][i] for i in range(3) if i != ax)
        return (c["radius"], ax, round(coord_along, 2), other_coords)

    holes.sort(key=_sort_key)
    bosses.sort(key=_sort_key)

    refs = {}
    for i, h in enumerate(holes, 1):
        refs[f"h{i}"] = {k: v for k, v in h.items() if k != "axis_idx"}
    for i, b in enumerate(bosses, 1):
        refs[f"b{i}"] = {k: v for k, v in b.items() if k != "axis_idx"}

    return refs


def write_refs_json(refs: dict, out_path: str) -> None:
    """写 part_refs.json 侧车文件。"""
    out_path = os.path.splitext(out_path)[0] + "_refs.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(refs, f, indent=2, ensure_ascii=False)
    print(f"  wrote {len(refs)} refs → {out_path}")


def load_refs(json_path: str) -> dict:
    """读 part_refs.json。"""
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def format_ref(part_name: str, ref_type: str, index: int) -> str:
    """格式化选择器引用字符串。

    ref_type: 'h' (孔) 或 'b' (凸台)
    index: 序号 (1-based)
    返回: "JointHousing#h1"
    """
    return f"{part_name}#{ref_type}{index}"
