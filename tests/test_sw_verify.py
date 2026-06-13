"""Tests for sw_verify — STEP parsing + 7D3S scoring (API verified)."""
from sw_2026_skill.sw_verify import (
    _parse_step_entities,
    verdict_7d3s,
    md5_of,
)


class TestParseStepEntities:
    def test_parses_cylinder(self):
        step = "#1=CYLINDRICAL_SURFACE('',#2,10.0);"
        ents = _parse_step_entities(step)
        assert 1 in ents
        typ, body = ents[1]
        assert typ == "CYLINDRICAL_SURFACE"
        assert "10.0" in body

    def test_parses_cartesian_point(self):
        step = "#1=CARTESIAN_POINT('',(1.5,2.5,3.5));"
        ents = _parse_step_entities(step)
        typ, body = ents[1]
        assert typ == "CARTESIAN_POINT"

    def test_parses_direction(self):
        step = "#1=DIRECTION('',(0.,1.,0.));"
        ents = _parse_step_entities(step)
        typ, body = ents[1]
        assert typ == "DIRECTION"

    def test_multiple_entities(self):
        step = """
#1=CARTESIAN_POINT('',(0.,0.,0.));
#2=DIRECTION('',(0.,1.,0.));
#3=CYLINDRICAL_SURFACE('',#4,15.0);
"""
        ents = _parse_step_entities(step)
        assert len(ents) == 3


class Test7D3SScoring:
    def test_verdict_pass(self):
        scores = {"D1": 5, "D2": 5, "D3": 4, "D4": 4, "D5": 5, "D6": 4, "D7": 4}
        tag, detail = verdict_7d3s(scores)
        assert tag in ("PASS-EXCELLENT", "PASS")

    def test_verdict_reject_zero(self):
        scores = {"D1": 0, "D2": 5, "D3": 5, "D4": 5, "D5": 5, "D6": 5, "D7": 5}
        tag, detail = verdict_7d3s(scores)
        assert tag == "REJECT"
        assert "D1" in detail

    def test_verdict_low_score(self):
        scores = {"D1": 2, "D2": 2, "D3": 2, "D4": 2, "D5": 2, "D6": 2, "D7": 2}
        tag, detail = verdict_7d3s(scores)
        assert tag == "REJECT"


class TestMd5:
    def test_known_hash(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
            f.write(b"hello")
            path = f.name
        try:
            h = md5_of(path)
            assert h == "5d41402abc4b2a76b9719d911017c592"
        finally:
            os.unlink(path)
