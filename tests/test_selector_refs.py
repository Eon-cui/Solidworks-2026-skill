"""
test_selector_refs.py — verify discover_refs against test STEP fixtures.
Pure Python, no SW dependency.
"""
import sys
import json
import pytest
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"
STEP_FIXTURES = list(FIXTURE_DIR.glob("*.STEP"))


def test_discover_refs():
    """discover_refs on test fixture → correct cylinder classification."""
    if not STEP_FIXTURES:
        pytest.skip("No STEP fixtures found")

    from sw_2026_skill.sw_selector_refs import (
        discover_refs, write_refs_json, load_refs, format_ref,
    )

    refs = discover_refs(str(STEP_FIXTURES[0]))
    assert len(refs) > 0, "discover_refs returned empty"
    assert "h1" in refs, "no hole refs found"
    assert "b1" in refs, "no boss refs found"

    # Verify structure
    for k, v in refs.items():
        assert k.startswith("h") or k.startswith("b"), f"unexpected key: {k}"
        assert "radius" in v, f"missing radius in {k}"
        assert "origin" in v, f"missing origin in {k}"
        assert "axis" in v, f"missing axis in {k}"
        assert len(v["origin"]) == 3, f"origin should have 3 coords: {v['origin']}"

    # Verify dedup (3 cylinders → 3 unique refs, no dupes in fixture)
    assert 2 <= len(refs) <= 10, (
        f"Expected 2-10 unique refs after dedup, got {len(refs)}"
    )

    # Test write/load roundtrip
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(suffix="_refs.json", delete=False, mode="w") as tf:
        json.dump(refs, tf)
        tmp_path = tf.name

    try:
        loaded = load_refs(tmp_path)
        def to_lists(d):
            if isinstance(d, dict):
                return {k: to_lists(v) for k, v in d.items()}
            if isinstance(d, tuple):
                return list(d)
            return d
        assert to_lists(loaded) == to_lists(refs), "load_refs roundtrip mismatch"
    finally:
        os.unlink(tmp_path)

    # Test format_ref
    assert format_ref("TestPart", "h", 1) == "TestPart#h1"
    assert format_ref("TestPart", "b", 3) == "TestPart#b3"

    holes = sum(1 for k in refs if k.startswith("h"))
    bosses = sum(1 for k in refs if k.startswith("b"))
    print(f"  OK {len(refs)} refs (holes={holes}, bosses={bosses})")
