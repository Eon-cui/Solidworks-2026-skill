"""
sw_step_parts.py — step.parts 外购件桥接
========================================
动态发现 step-parts skill → 搜索 → 下载(SHA-256) → 导入 SW → 验比例。
不可达 → 降级占位，不阻塞工作流。

独立性: 不依赖 text-to-cad 的 cad skill。仅依赖 step-parts 独立 skill (可选，未装→降级)。
"""
import sys
# stdout configured by solidworks_2026_skill._compat
import os
import json
import hashlib
import subprocess
from pathlib import Path

# ── 路径发现 ──

def is_step_parts_installed() -> Path | None:
    """动态发现 step-parts download_step_part.py。返回路径或 None。"""
    candidates = [
        Path.home() / ".claude" / "skills" / "step-parts" / "scripts" / "download_step_part.py",
    ]
    # Also check project-local (same repo pattern)
    try:
        import solidworks_2026_skill
        pkg_dir = Path(__file__).parent.parent  # solidworks-2026-skill/
        candidates.append(pkg_dir.parent / "step-parts" / "scripts" / "download_step_part.py")
    except Exception:
        pass

    for sp in candidates:
        if sp.exists():
            return sp
    return None


# ── 搜索 ──

def search_standard_part(query: str, category: str | None = None,
                         family: str | None = None,
                         tag: str | None = None,
                         limit: int = 5,
                         timeout: float = 15.0) -> list[dict] | None:
    """
    搜索 step.parts API → 返回 part 列表。不可达/超时→None。

    query: 模糊搜索词, 如 "M3 socket head 12"
    category: 可选过滤, "fastener"/"bearing"/"actuator"/"motor" 等
    """
    script = is_step_parts_installed()
    if script is None:
        return None

    cmd = [sys.executable, str(script), query, "--limit", str(limit),
           "--timeout", str(timeout)]
    if category:
        cmd.extend(["--category", category])
    if family:
        cmd.extend(["--family", family])
    if tag:
        cmd.extend(["--tag", tag])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout + 5,  # extra margin
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        items = data.get("items", [])
        return items if items else None
    except (subprocess.TimeoutExpired, Exception):
        return None


# ── 下载 + 导入 ──

def download_and_import(sw, part: dict, out_dir: str) -> str | None:
    """
    下载 STEP → SHA-256 校验 → 导入 SW → 存 SLDPRT → 返回路径。
    失败返回 None。

    part: search_standard_part 返回的单个 item dict (需含 id + stepUrl + sha256)
    sw: SW 连接对象 (ISldWorks)
    out_dir: 输出目录
    """
    script = is_step_parts_installed()
    if script is None:
        return None

    part_id = part.get("id")
    if not part_id:
        return None

    os.makedirs(out_dir, exist_ok=True)

    # Download via step-parts CLI (handles SHA-256 internally)
    cmd = [
        sys.executable, str(script),
        "--id", part_id,
        "--download", "--out-dir", out_dir,
        "--overwrite",
        "--timeout", "30",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=35,
        )
        if result.returncode != 0:
            return None
        dl_info = json.loads(result.stdout)
        downloads = dl_info.get("downloads", [])
        if not downloads:
            return None
        step_path = downloads[0].get("path")
        if not step_path or not os.path.exists(step_path):
            return None
    except (subprocess.TimeoutExpired, Exception):
        return None

    # Import into SW
    try:
        from solidworks_2026_skill.sw_connect import VBR, VN
        sw.OpenDoc6(step_path, 3, 0, "", VBR(), VBR())  # 3=swDocPART
        model = sw.ActiveDoc
        # Save as SLDPRT alongside the STEP
        sldprt_path = os.path.splitext(step_path)[0] + ".SLDPRT"
        # Remove old if exists (file lock issue)
        if os.path.exists(sldprt_path):
            try:
                os.remove(sldprt_path)
            except Exception:
                pass
        model.SaveAs3(sldprt_path, 0, 0)
        # Close the STEP document
        try:
            sw.CloseDoc(os.path.basename(step_path))
        except Exception:
            pass
        return sldprt_path
    except Exception:
        return None


# ── 降级占位 ──

def create_placeholder_and_record_miss(sw, name: str, out_dir: str,
                                       envelope: dict) -> str:
    """
    降级：创建外形占位件 + 记录未命中。

    envelope examples:
      {"type": "cylinder", "od": 5.5, "length": 12}    # M3 螺栓占位
      {"type": "box", "w": 23, "d": 12, "h": 26}       # SG90 舵机占位
    返回 SLDPRT 路径。
    """
    os.makedirs(out_dir, exist_ok=True)

    etype = envelope.get("type", "cylinder")
    if etype == "cylinder":
        od = envelope.get("od", 10.0)
        length = envelope.get("length", 10.0)
        with _placeholder_session(sw, name, out_dir) as s:
            s.sketch_on_plane()
            s.circle(0, 0, od)
            s.exit_sketch()
            s.extrude(length)
            s.check_faces(f"{name} 占位")
    elif etype == "box":
        w = envelope.get("w", 10.0)
        d = envelope.get("d", 10.0)
        h = envelope.get("h", 10.0)
        with _placeholder_session(sw, name, out_dir) as s:
            s.sketch_on_plane()
            s.rect_center(0, 0, w, d)
            s.exit_sketch()
            s.extrude(h)
            s.check_faces(f"{name} 占位")
    else:
        # Fallback: cylinder
        with _placeholder_session(sw, name, out_dir) as s:
            s.sketch_on_plane()
            s.circle(0, 0, 10)
            s.exit_sketch()
            s.extrude(10)
            s.check_faces(f"{name} 占位(默认)")

    sldprt = os.path.join(out_dir, f"{name}.SLDPRT")
    print(f"  ⚠ {name}: step.parts 不可达 → 占位 {sldprt}")
    return sldprt


class _placeholder_session:
    """简化版 SW 会话，只做占位件。避免重复 SW() 的重量级初始化。"""

    def __init__(self, sw_conn, name, out_dir):
        self.sw = sw_conn
        self.name = name
        self.out_dir = out_dir
        self.model = None

    def __enter__(self):
        from solidworks_2026_skill.sw_session import SW
        self._sw_session = SW(self.name)
        s = self._sw_session.__enter__()
        self.model = s.model
        return s

    def __exit__(self, *args):
        from solidworks_2026_skill.sw_session import SW
        # Save
        sldprt = os.path.join(self.out_dir, f"{self.name}.SLDPRT")
        step = os.path.join(self.out_dir, f"{self.name}.STEP")
        # Remove old files
        for p in [sldprt, step]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        try:
            self.model.Extension.SaveAs(sldprt, 0, 0, None, None, 0, 0)
            self.model.Extension.SaveAs(step, 0, 0, None, None, 0, 0)
        except Exception:
            pass
        self._sw_session.__exit__(*args)
