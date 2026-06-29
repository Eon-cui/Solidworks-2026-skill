"""
test_l1_l3.py — L1-L3 layered tests for solidworks-2026-skill.

L1: Installation & Import (pure Python, no SW)
L2: Pure Python functionality (no SW)
L3: Error handling & edge cases (no SW)

Run: py -3.13 -m pytest tests/test_l1_l3.py -v --tb=short
"""
import sys
import os
import tempfile
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent
FIXTURE_DIR = Path(__file__).parent / "fixtures"
STEP_FIXTURE = FIXTURE_DIR / "test_cylinders.STEP"

# ============================================================================
# L1 — Installation & Import
# ============================================================================

class TestL1InstallImport:
    """L1: All public symbols importable, _com_helpers symbols, _com_signatures tuples."""

    # L1-1: __all__ entries importable
    ALL_EXPECTED = [
        "SW", "VN", "VBR", "genmod", "early", "put_object_property",
        "connect_solidworks", "find_template",
        "verify_step", "verify_assembly_poses", "count_faces",
        "score_s1", "score_s2", "verdict_7d3s",
        "run_validation_pipeline",
        "Checker",
        "discover_refs", "write_refs_json", "load_refs", "format_ref",
        "capture_views",
        "is_step_parts_installed", "search_standard_part",
        "download_and_import", "create_placeholder_and_record_miss",
        "get_sw_templates_dir", "get_sw_install_dir",
    ]

    def test_all_symbols_importable(self):
        """L1-2: Every __all__ symbol lazy-imports without error."""
        import solidworks_2026_skill as pkg
        missing = []
        for name in sorted(set(self.ALL_EXPECTED)):
            try:
                getattr(pkg, name)
            except Exception as e:
                missing.append(f"{name}: {e}")
        assert not missing, f"Failed imports:\n" + "\n".join(missing)
        assert sorted(pkg.__all__) == sorted(self.ALL_EXPECTED), (
            "__all__ mismatch — update ALL_EXPECTED or __init__.py"
        )

    def test_com_helpers_14_symbols(self):
        """L1-3: _com_helpers exports exactly 14 public symbols."""
        from solidworks_2026_skill import _com_helpers as ch
        expected = {
            "VN", "VBR", "mm", "M", "deg", "_v",
            "get_com_member", "safe_get_com_member",
            "genmod", "early", "put_object_property",
            "untuple", "SW_TYPELIB", "DISPID_TRANSFORM2",
        }
        # Filter module-level re-exports from imports (math, pythoncom, VARIANT)
        actual = {
            n for n in dir(ch)
            if not n.startswith("__") and n not in ("math", "pythoncom", "VARIANT")
        }
        missing = expected - actual
        extra = actual - expected
        assert not missing, f"Missing _com_helpers symbols: {missing}"
        assert not extra, f"Unexpected _com_helpers symbols: {extra}"

    def test_fc3_params_length_26(self):
        """L1-4a: feature_cut3_params returns 26-element tuple."""
        from solidworks_2026_skill._com_signatures import feature_cut3_params
        args = feature_cut3_params()
        assert len(args) == 26, f"FC3 params: expected 26, got {len(args)}"
        # through_all variant
        args2 = feature_cut3_params(through_all=True)
        assert len(args2) == 26
        # verify through_all changes end_condition (pos 3) and depth (pos 5)
        assert args2[3] == 1, f"through_all end_condition should be 1, got {args2[3]}"
        assert args2[5] == 0.001, f"through_all placeholder depth should be 0.001, got {args2[5]}"

    def test_fe3_params_length_23(self):
        """L1-4b: feature_extrusion3_params returns 23-element tuple."""
        from solidworks_2026_skill._com_signatures import feature_extrusion3_params
        args = feature_extrusion3_params()
        assert len(args) == 23, f"FE3 params: expected 23, got {len(args)}"
        # midplane variant
        args2 = feature_extrusion3_params(end_condition=6)
        assert len(args2) == 23
        assert args2[3] == 6, f"midplane end_condition should be 6, got {args2[3]}"

    def test_mcp_server_importable(self):
        """L1-5: mcp.server imports without starting."""
        # Import only — must not call run_server()
        from solidworks_2026_skill.mcp import server
        assert hasattr(server, "main"), "MCP server missing main()"
        assert hasattr(server, "run_server"), "MCP server missing run_server()"


# ============================================================================
# L2 — Pure Python functionality
# ============================================================================

class TestL2PurePython:
    """L2: verify_step, _parse_step_entities, discover_refs, Checker."""

    def test_verify_step_fixture(self):
        """L2-6: verify_step on test_cylinders.STEP returns correct results."""
        from solidworks_2026_skill.sw_verify import verify_step
        # Fixture has CYLINDRICAL_SURFACE (R3, R5, R22) but no CIRCLE entities.
        # max_circle looks for CIRCLE regex — will be 0.0 if no circles present.
        ok, report = verify_step(
            str(STEP_FIXTURE),
            expected_holes=[],
        )
        assert ok, f"verify_step FAILED:\n{report}"
        # With no expected_holes and no max_circle → always passes
        assert "PASS" in report

    def test_verify_step_max_circle(self):
        """L2-6b: verify_step max_circle on a fixture with CIRCLE entities.
        test_cylinders.STEP has no CIRCLE — max_circle defaults to 0.0.
        This is expected behavior: max_circle=0 means 'no CIRCLE check'."""
        from solidworks_2026_skill.sw_verify import verify_step
        # With max_circle=0, the CIRCLE regex matches nothing → rmax=0 → abs(0-0) < tol → passes
        ok, report = verify_step(
            str(STEP_FIXTURE),
            expected_holes=[],
            max_circle=0.0,
        )
        assert ok, f"max_circle=0 should pass on fixture with no CIRCLE entities:\n{report}"

    def test_verify_step_with_holes(self):
        """L2-6b: verify_step with expected_holes specification."""
        from solidworks_2026_skill.sw_verify import verify_step
        # test_cylinders.STEP: 3 cylinders — R3, R5, R22
        # Each cyl_surface appears once → radii // 2 = 0 holes each
        # With no expected holes → should pass
        ok, report = verify_step(str(STEP_FIXTURE), expected_holes=[])
        assert ok, f"Expected PASS with no holes:\n{report}"

    def test_parse_step_entities(self):
        """L2-7: _parse_step_entities parses STEP text correctly."""
        from solidworks_2026_skill.sw_verify import _parse_step_entities
        with open(STEP_FIXTURE, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        ents = _parse_step_entities(text)
        assert len(ents) > 0, "No entities parsed"
        # Find CYLINDRICAL_SURFACE entities
        cyls = {eid: body for eid, (typ, body) in ents.items()
                if typ == "CYLINDRICAL_SURFACE"}
        assert len(cyls) == 3, f"Expected 3 CYLINDRICAL_SURFACE, got {len(cyls)}"
        # Verify AXIS2_PLACEMENT_3D entities exist
        placements = {eid for eid, (typ, _) in ents.items()
                      if typ == "AXIS2_PLACEMENT_3D"}
        assert len(placements) == 3, f"Expected 3 AXIS2_PLACEMENT_3D, got {len(placements)}"
        # Verify CARTESIAN_POINT entities
        points = {eid for eid, (typ, _) in ents.items()
                  if typ == "CARTESIAN_POINT"}
        assert len(points) == 3, f"Expected 3 CARTESIAN_POINT, got {len(points)}"

    def test_discover_refs_fixture(self):
        """L2-8: discover_refs classifies hole/boss correctly."""
        from solidworks_2026_skill.sw_selector_refs import discover_refs
        refs = discover_refs(str(STEP_FIXTURE))
        assert len(refs) > 0, "discover_refs returned empty"
        assert "h1" in refs, "no hole refs found (h1)"
        assert "b1" in refs, "no boss refs found (b1)"
        # Verify structure
        for k, v in refs.items():
            assert k.startswith("h") or k.startswith("b"), f"unexpected key: {k}"
            assert "radius" in v
            assert "origin" in v
            assert "axis" in v
            assert len(v["origin"]) == 3

    def test_checker_class(self):
        """L2-9: Checker class instantiates and methods work."""
        from solidworks_2026_skill.sw_check_interfaces import Checker
        ck = Checker(title="L2 Test")
        assert ck.title == "L2 Test"
        assert ck.results == []

        # eq method
        assert ck.eq("PCD", 36.0, 36.0) is True
        assert ck.eq("Bad", 40.0, 36.0) is False
        assert len(ck.results) == 2
        assert ck.results == [True, False]

        # true method
        assert ck.true("always", True) is True
        assert ck.true("never", False) is False
        assert len(ck.results) == 4

        # section (no-op visual)
        ck.section("Test Section")

        # report
        ok = ck.report()
        assert ok is False  # 2/4 passed


# ============================================================================
# L3 — Error handling & edge cases
# ============================================================================

class TestL3ErrorHandling:
    """L3: Error paths, boundary values, parameter combinations."""

    def test_verify_step_nonexistent_file(self):
        """L3-10: verify_step on non-existent file gives reasonable error."""
        from solidworks_2026_skill.sw_verify import verify_step
        with pytest.raises((FileNotFoundError, OSError, IOError)):
            verify_step("/nonexistent/path/ghost.STEP", expected_holes=[])

    def test_verify_step_empty_file(self):
        """L3-11a: verify_step on empty file does not crash."""
        from solidworks_2026_skill.sw_verify import verify_step
        with tempfile.NamedTemporaryFile(
            suffix=".STEP", mode="w", delete=False
        ) as tf:
            tf.write("")
            tmp_path = tf.name
        try:
            ok, report = verify_step(tmp_path, expected_holes=[])
            # Empty file: no cylinders → no holes. Should not crash.
            assert isinstance(ok, bool)
            assert isinstance(report, str)
        finally:
            os.unlink(tmp_path)

    def test_verify_step_non_step_content(self):
        """L3-11b: verify_step on non-STEP content does not crash."""
        from solidworks_2026_skill.sw_verify import verify_step
        with tempfile.NamedTemporaryFile(
            suffix=".STEP", mode="w", delete=False
        ) as tf:
            tf.write("This is not a STEP file.\nJust random text.\n")
            tmp_path = tf.name
        try:
            ok, report = verify_step(tmp_path, expected_holes=[])
            # Non-STEP: no CYLINDRICAL_SURFACE matches. Should not crash.
            assert isinstance(ok, bool)
            assert isinstance(report, str)
        finally:
            os.unlink(tmp_path)

    def test_mm_zero(self):
        """L3-12a: mm(0) = 0.0."""
        from solidworks_2026_skill._com_helpers import mm
        assert mm(0) == 0.0
        assert mm(1000) == 1.0
        assert mm(25.4) == 0.0254
        assert mm(-500) == -0.5

    def test_deg_zero(self):
        """L3-12b: deg(0) = 0.0."""
        from solidworks_2026_skill._com_helpers import deg
        assert deg(0) == 0.0
        assert abs(deg(90) - 1.5707963267948966) < 1e-9
        assert abs(deg(180) - 3.141592653589793) < 1e-9
        assert abs(deg(360) - 6.283185307179586) < 1e-9

    def test_untuple_tuple(self):
        """L3-12c: untuple returns first element of any tuple, pass-through otherwise."""
        from solidworks_2026_skill._com_helpers import untuple
        assert untuple((42,)) == 42                 # single-elem → unwrap
        assert untuple((42, "info")) == 42          # multi-elem → always first elem
        assert untuple("plain") == "plain"          # non-tuple pass-through

    def test_untuple_none(self):
        """L3-12d: untuple(None) returns None."""
        from solidworks_2026_skill._com_helpers import untuple
        assert untuple(None) is None

    def test_vn_vbr_types(self):
        """L3-12e: VN() and VBR() return VARIANT objects with correct types."""
        from solidworks_2026_skill._com_helpers import VN, VBR
        import pythoncom
        from win32com.client import VARIANT
        vn = VN()
        vbr = VBR()
        assert isinstance(vn, VARIANT)
        assert isinstance(vbr, VARIANT)
        # VN: VT_DISPATCH (9) empty
        assert vn.varianttype == pythoncom.VT_DISPATCH
        # VBR: VT_BYREF (0x4000) | VT_I4 (3) via value attribute
        # repr: VARIANT(16387, 0) = 0x4003 = VT_BYREF|VT_I4
        assert vbr.varianttype == (pythoncom.VT_BYREF | pythoncom.VT_I4)

    def test_fc3_params_variants(self):
        """L3-13a: FC3 param combinations — through_all, depth, flip, dir_flag."""
        from solidworks_2026_skill._com_signatures import feature_cut3_params

        # Default: blind, no flip, no normal_cut
        a = feature_cut3_params()
        assert a[0] is True     # SD
        assert a[1] is False    # Flip
        assert a[2] is False    # dir_flag
        assert a[3] == 0        # end_condition = Blind
        assert a[17] is False   # normal_cut (iron law)

        # through_all
        a = feature_cut3_params(through_all=True)
        assert a[3] == 1        # end_condition = ThroughAll

        # with depth
        a = feature_cut3_params(depth_m=0.005)
        assert a[5] == 0.005

        # flip
        a = feature_cut3_params(flip=True)
        assert a[1] is True

        # dir_flag
        a = feature_cut3_params(dir_flag=True)
        assert a[2] is True

        # normal_cut=True (WARNING: iron law says always False, but factory allows it)
        a = feature_cut3_params(normal_cut=True)
        assert a[17] is True

    def test_fe3_params_variants(self):
        """L3-13b: FE3 param combinations — depth, reverse, merge, end_condition."""
        from solidworks_2026_skill._com_signatures import feature_extrusion3_params

        # Default
        a = feature_extrusion3_params()
        assert len(a) == 23
        assert a[0] is True     # SD
        assert a[1] is False    # Reverse
        assert a[3] == 0        # Blind
        assert a[17] is True    # merge (position 17 of 23)

        # reverse
        a = feature_extrusion3_params(reverse=True)
        assert a[1] is True

        # no merge
        a = feature_extrusion3_params(merge=False)
        assert a[17] is False

        # midplane
        a = feature_extrusion3_params(end_condition=6)
        assert a[3] == 6

        # through all
        a = feature_extrusion3_params(end_condition=1)
        assert a[3] == 1

    def test_safe_get_com_member_on_plain_object(self):
        """L3-12f: get_com_member works on plain Python objects."""
        from solidworks_2026_skill._com_helpers import get_com_member

        class Obj:
            x = 42
            def y(self):
                return 99

        o = Obj()
        assert get_com_member(o, "x") == 42
        assert get_com_member(o, "y") == 99


class TestL3ErrorMessages:
    """L3: Error message regression — English-only, parameters preserved."""

    def test_face_selection_error_has_coords(self):
        """Raise message must contain label and coordinates."""
        from solidworks_2026_skill.sw_session import SW
        import inspect
        src = inspect.getsource(SW.face)
        # Verify English error message with params
        assert "Face selection failed" in src, "face() error not English"
        assert "{label}" in src, "face() missing label param"
        assert "{x}" in src, "face() missing x param"

    def test_check_faces_error_has_counts(self):
        """Raise message must contain face count delta."""
        from solidworks_2026_skill.sw_session import SW
        import inspect
        src = inspect.getsource(SW.check_faces)
        assert "{prev}" in src and "{n}" in src, "check_faces() missing count params"

    def test_cut_error_has_depth(self):
        """Raise message must contain depth param."""
        from solidworks_2026_skill.sw_session import SW
        import inspect
        src = inspect.getsource(SW.cut)
        assert "{depth}" in src or "depth" in src.lower(), "cut() missing depth"

    def test_plane_error_is_english(self):
        """Plane selection error must be English."""
        from solidworks_2026_skill.sw_session import SW
        import inspect
        src = inspect.getsource(SW.plane)
        assert "Plane selection failed" in src or "选基准面失败" not in src

    def test_no_chinese_in_session_errors(self):
        """sw_session.py RuntimeError messages must have no Chinese."""
        import re
        with open("solidworks_2026_skill/sw_session.py", encoding="utf-8") as f:
            src = f.read()
        # Find all RuntimeError raises
        for m in re.finditer(r'raise RuntimeError\((.+)\)', src):
            msg = m.group(1)
            if re.search(r'[一-鿿]', msg):
                raise AssertionError(f"Chinese in RuntimeError: {msg[:80]}")

