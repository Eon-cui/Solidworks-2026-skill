"""
test_syntax.py — compile all solidworks_2026_skill Python files.
Does NOT import them (avoids pywin32/SW dependency).
"""
import sys
import py_compile
from pathlib import Path

ROOT = Path(__file__).parent.parent
PKG = ROOT / "solidworks_2026_skill"

EXCLUDE = {"_untested", "__pycache__", "tests"}


def test_all_py_files_compile():
    py_files = sorted(
        f for f in PKG.rglob("*.py")
        if not any(ex in f.parts for ex in EXCLUDE)
        and f.name != "__init__.py"  # tested separately
    )
    assert py_files, "No .py files found"

    failed = []
    for f in py_files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            failed.append(f"{f.relative_to(ROOT)}: {e}")

    assert not failed, f"{len(failed)} files fail compile:\n" + "\n".join(failed)
    print(f"  OK {len(py_files)} .py files compile clean")


def test_init_imports_matches_files():
    """__init__.py __all__ entries vs actual modules."""
    import ast, re

    init_path = PKG / "__init__.py"
    with open(init_path, encoding="utf-8") as f:
        init_src = f.read()

    # Extract __all__ entries
    tree = ast.parse(init_src)
    all_entries = []
    for node in ast.walk(tree):
        if isinstance(node, ast.List):
            all_entries = [
                e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            break

    # Verify each has a lazy import branch or existing public API
    existing_modules = {
        f.stem for f in PKG.glob("*.py")
        if f.name not in ("__init__.py", "_compat.py")
    }

    # Known public API from existing modules
    public_api = {
        "SW": "sw_session", "VN": "sw_session", "VBR": "sw_session",
        "genmod": "sw_session", "early": "sw_session", "put_object_property": "sw_session",
        "connect_solidworks": "sw_connect", "find_template": "sw_connect",
        "verify_step": "sw_verify", "verify_assembly_poses": "sw_verify",
        "count_faces": "sw_verify", "score_s1": "sw_verify", "score_s2": "sw_verify",
        "verdict_7d3s": "sw_verify", "run_validation_pipeline": "sw_verify",
        "Checker": "sw_check_interfaces",
        "discover_refs": "sw_selector_refs", "write_refs_json": "sw_selector_refs",
        "load_refs": "sw_selector_refs", "format_ref": "sw_selector_refs",
        "capture_views": "sw_snapshot",
        "is_step_parts_installed": "sw_step_parts",
        "search_standard_part": "sw_step_parts",
        "download_and_import": "sw_step_parts",
        "create_placeholder_and_record_miss": "sw_step_parts",
        "get_sw_templates_dir": "sw_preflight",
        "get_sw_install_dir": "sw_preflight",
    }

    missing = []
    for entry in all_entries:
        if entry not in public_api:
            missing.append(entry)
        else:
            module_name = public_api[entry]
            if module_name not in existing_modules:
                missing.append(f"{entry} → {module_name}.py NOT FOUND")

    assert not missing, f"__all__ entries without module:\n" + "\n".join(missing)
    print(f"  OK {len(all_entries)} __all__ entries match modules")
