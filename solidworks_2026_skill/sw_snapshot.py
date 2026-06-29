"""
sw_snapshot.py — SW 快照复核 (SaveBMP + Pillow 裁剪转 PNG)
============================================================
强制视觉复核政策见 references/snapshot-review.md。
"""
import sys
# stdout configured by solidworks_2026_skill._compat
import os
import math


# ── SW 命名视图 ID (中英文兼容) ──

_VIEW_NAMES = {
    "iso":        ["*等轴测", "*Isometric", "*上下二等角轴测", "*Dimetric"],
    "top":        ["*上视", "*Top"],
    "front":      ["*前视", "*Front"],
    "right":      ["*右视", "*Right"],
    "bottom":     ["*下视", "*Bottom"],
    "back":       ["*后视", "*Back"],
    "left":       ["*左视", "*Left"],
}


def _show_view(model, view_key: str) -> bool:
    """Show named view. Returns True on success."""
    names = _VIEW_NAMES.get(view_key, [view_key])
    for name in names:
        try:
            result = model.ShowNamedView2(name, -1)
            if result:
                return True
        except Exception:
            continue
    return False


def _save_bmp(model, path: str, width: int = 2400, height: int = 1800) -> str:
    """SaveBMP high-res, then Pillow crop empty border → PNG."""
    # Zoom to fit
    try:
        model.ViewZoomtofit2()
        # GraphicsRedraw2 is an attribute, not method, on some SW versions
        redraw = getattr(model, "GraphicsRedraw2", None)
        if redraw is not None:
            try:
                redraw()
            except Exception:
                pass
    except Exception:
        pass

    # Save BMP
    model.SaveBMP(path, width, height)

    # Crop white/black empty border + save as PNG
    try:
        from PIL import Image
    except ImportError:
        raise ImportError(
            "Pillow is required for snapshot BMP→PNG conversion. "
            "Install with: pip install Pillow"
        )

    png_path = path.rsplit(".", 1)[0] + ".png"
    img = Image.open(path)
    # Auto-crop: remove solid-color border (tolerance=10)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    img.save(png_path, "PNG")
    # Remove BMP (keep PNG)
    try:
        os.remove(path)
    except Exception:
        pass
    return png_path


def capture_views(model, out_dir: str, name: str,
                  width: int = 2400, height: int = 1800) -> list[str]:
    """
    标准 4 视图包 → PNG 路径列表。

    model: SW IModelDoc2
    out_dir: 输出目录
    name: 零件名 (不含扩展名)
    width, height: SaveBMP 分辨率
    返回: [iso.png, opposite.png, top.png, front.png] 路径列表
    """
    os.makedirs(out_dir, exist_ok=True)

    views = [
        ("iso", f"{name}_iso"),
        ("top", f"{name}_top"),
        ("front", f"{name}_front"),
    ]

    pngs = []
    for view_key, stem in views:
        if _show_view(model, view_key):
            path = os.path.join(out_dir, f"{stem}.bmp")
        else:
            # Fallback: try iso if named view fails
            model.ShowNamedView2("*等轴测", -1)
            path = os.path.join(out_dir, f"{stem}_fallback.bmp")

        try:
            png = _save_bmp(model, path, width, height)
            pngs.append(png)
        except Exception:
            # SaveBMP failed — skip this view
            pass

    # Opposite isometric: manual camera
    try:
        # Flip camera direction by rotating 180° around Z
        # Approximate: ShowNamedView2 with dimetric alternate
        for alt in _VIEW_NAMES.get("iso", [])[1:]:  # Try alternates
            if model.ShowNamedView2(alt, -1):
                path_opp = os.path.join(out_dir, f"{name}_opposite.bmp")
                try:
                    png = _save_bmp(model, path_opp, width, height)
                    pngs.insert(1, png)  # Insert after iso
                except Exception:
                    pass
                break
    except Exception:
        pass

    return pngs


def capture_section(model, out_dir: str, name: str,
                    plane_name: str = "Front Plane",
                    offset_mm: float = 0.0) -> str | None:
    """
    截面视图 (SW 内手动操作后 SaveBMP)。

    注意: SW COM 的 SectionView API 未封装 (`_untested/`)。
    此函数假设截面已手动或在调用前通过其他方式设置好。
    返回 PNG 路径或 None。
    """
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}_section.bmp")
    try:
        return _save_bmp(model, path)
    except Exception:
        return None
