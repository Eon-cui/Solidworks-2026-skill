"""Tests for sw_preflight — environment checks (pure Python, no SW)."""
import platform
from sw_2026_skill.sw_preflight import _is_windows, get_sw_install_dir, get_sw_templates_dir, get_sw_tlb_path


class TestIsWindows:
    def test_returns_bool(self):
        result = _is_windows()
        assert isinstance(result, bool)

    def test_matches_platform(self):
        assert _is_windows() == (platform.system() == "Windows")


class TestPathResolution:
    def test_get_sw_install_dir_returns_string(self):
        result = get_sw_install_dir()
        assert isinstance(result, str)

    def test_get_sw_templates_dir_returns_string(self):
        result = get_sw_templates_dir()
        assert isinstance(result, str)

    def test_get_sw_tlb_path_returns_string(self):
        result = get_sw_tlb_path("nonexistent_file_xyz123.tlb")
        assert isinstance(result, str)
        # On non-SW machine, should be empty
        if not _is_windows():
            assert result == ""

    def test_extra_dirs_parameter_accepted(self):
        result = get_sw_templates_dir(extra_dirs=["C:/nonexistent_xyz123"])
        assert isinstance(result, str)
