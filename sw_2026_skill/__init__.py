"""sw-2026-skill — SolidWorks 2026 Python COM automation toolkit.

Production-verified through UR-SEU-2026 5-DOF robotic arm project
(35+ parts, 32-instance assembly, 43 mates, all STEP-verified).

See ../SKILL.md for full documentation.
"""

__version__ = "1.0.0"

# Lazy imports — only load what's needed
__all__ = [
    # Session management
    "SW",
    # COM helpers
    "VN", "VBR", "genmod", "early", "put_object_property",
    # Connection
    "connect_solidworks", "find_template",
    # Verification (pure Python, no SW needed)
    "verify_step", "verify_assembly_poses", "count_faces",
    "score_s1", "score_s2", "verdict_7d3s",
    "run_validation_pipeline",
    # Interface checking (pure Python, no SW needed)
    "Checker",
    # Selector references (pure Python)
    "discover_refs", "write_refs_json", "load_refs", "format_ref",
    # Snapshot (requires SW + Pillow)
    "capture_views",
    # step.parts bridge (optional)
    "is_step_parts_installed", "search_standard_part",
    "download_and_import", "create_placeholder_and_record_miss",
    # Preflight
    "get_sw_templates_dir", "get_sw_install_dir",
]


def __getattr__(name):
    """Lazy import to avoid loading pywin32 until needed."""
    if name == "SW":
        from sw_2026_skill.sw_session import SW
        return SW
    if name in ("VN", "VBR", "genmod", "early", "put_object_property"):
        from sw_2026_skill import sw_session as _m
        return getattr(_m, name)
    if name in ("connect_solidworks", "find_template"):
        from sw_2026_skill import sw_connect as _m
        return getattr(_m, name)
    if name in ("verify_step", "verify_assembly_poses", "count_faces",
                "score_s1", "score_s2", "verdict_7d3s"):
        from sw_2026_skill import sw_verify as _m
        return getattr(_m, name)
    if name == "Checker":
        from sw_2026_skill.sw_check_interfaces import Checker
        return Checker
    if name in ("discover_refs", "write_refs_json", "load_refs", "format_ref"):
        from sw_2026_skill import sw_selector_refs as _m
        return getattr(_m, name)
    if name in ("capture_views",):
        from sw_2026_skill import sw_snapshot as _m
        return getattr(_m, name)
    if name in ("is_step_parts_installed", "search_standard_part",
                "download_and_import", "create_placeholder_and_record_miss"):
        from sw_2026_skill import sw_step_parts as _m
        return getattr(_m, name)
    if name in ("get_sw_templates_dir", "get_sw_install_dir"):
        from sw_2026_skill import sw_preflight as _m
        return getattr(_m, name)
    if name == "run_validation_pipeline":
        from sw_2026_skill import sw_verify as _m
        return getattr(_m, name)
    raise AttributeError(f"module 'sw_2026_skill' has no attribute '{name}'")
