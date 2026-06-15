"""
test_selector_refs.py — verify discover_refs against actual STEP files.
Pure Python, no SW dependency.
"""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent  # project root

# STEP test fixture: Base.STEP from 01_打印件
STEP_FIXTURES = list((ROOT / "02_Design_设计稿" / "01_打印件").glob("*.STEP"))


def test_discover_refs_base():
    """discover_refs(Base.STEP) → 12 unique cylinders (after dedup from 26 raw)."""
    if not STEP_FIXTURES:
        pytest.skip("No STEP fixtures found")

    base = [f for f in STEP_FIXTURES if f.name == "Base.STEP"]
    if not base:
        pytest.skip("Base.STEP not found")

    # Add sw-2026-skill/ to path so 'sw_2026_skill' package is importable
    skill_root = str(ROOT / "sw-2026-skill")
    if skill_root not in sys.path:
        sys.path.insert(0, skill_root)
    from sw_2026_skill.sw_selector_refs import discover_refs, write_refs_json, load_refs, format_ref

    refs = discover_refs(str(base[0]))
    assert len(refs) > 0, "discover_refs returned empty"
    assert "h1" in refs, "no hole refs found"
    assert "b1" in refs, "no boss refs found"

    # Verify structure
    for k, v in refs.items():
        assert k.startswith("h") or k.startswith("b")
        assert "radius" in v
        assert "origin" in v
        assert "axis" in v
        assert len(v["origin"]) == 3

    # Verify dedup (26 raw cylinders → ~12 after dedup)
    assert 8 <= len(refs) <= 20, (
        f"Expected 8-20 unique refs after dedup, got {len(refs)}"
    )

    # Test write/load roundtrip (JSON serializes tuples→lists)
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix="_refs.json", delete=False, mode="w") as tf:
        json.dump(refs, tf)
        tmp_path = tf.name

    try:
        loaded = load_refs(tmp_path)
        # Normalize: JSON roundtrip converts tuples to lists
        def to_lists(d):
            if isinstance(d, dict):
                return {k: to_lists(v) for k, v in d.items()}
            if isinstance(d, tuple):
                return list(d)
            return d
        assert to_lists(loaded) == to_lists(refs), "load_refs roundtrip mismatch (tuple→list OK)"
    finally:
        os.unlink(tmp_path)

    # Test format_ref
    assert format_ref("Base", "h", 1) == "Base#h1"
    assert format_ref("JointHousing", "b", 3) == "JointHousing#b3"

    print(f"  OK {len(refs)} refs from Base.STEP (holes={sum(1 for k in refs if k.startswith('h'))}, bosses={sum(1 for k in refs if k.startswith('b'))})")
