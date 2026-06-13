"""Tests for sw_check_interfaces — cross-part interface checking (API verified)."""
import math
from sw_2026_skill.sw_check_interfaces import pcd_and_angle, Checker


class TestPcdAndAngle:
    def test_four_points_square(self):
        pts = [(10, 0), (0, 10), (-10, 0), (0, -10)]
        pcd, angle = pcd_and_angle(pts)
        assert abs(pcd - 20.0) < 0.1
        assert 0 <= angle < 90

    def test_four_points_diagonal(self):
        pts = [(10, 10), (-10, 10), (-10, -10), (10, -10)]
        pcd, angle = pcd_and_angle(pts)
        assert abs(pcd - math.sqrt(2) * 20.0) < 0.5

    def test_three_points(self):
        pts = [(10, 0), (-5, 8.66), (-5, -8.66)]
        pcd, angle = pcd_and_angle(pts)
        assert abs(pcd - 20.0) < 0.5


class TestChecker:
    def test_eq_pass(self):
        c = Checker()
        ok = c.eq("test", 10.0, 10.0, tol=0.01)
        assert ok

    def test_eq_fail(self):
        c = Checker()
        ok = c.eq("test", 10.0, 11.0, tol=0.01)
        assert not ok

    def test_true_pass(self):
        c = Checker()
        ok = c.true("should pass", True)
        assert ok

    def test_true_fail(self):
        c = Checker()
        ok = c.true("should fail", False)
        assert not ok

    def test_report_all_pass(self):
        c = Checker()
        c.eq("a", 5.0, 5.0)
        c.true("b", True)
        assert c.report() is True

    def test_report_with_fail(self):
        c = Checker()
        c.eq("a", 5.0, 5.0)
        c.eq("b", 3.0, 4.0)
        assert c.report() is False
