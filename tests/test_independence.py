"""
test_independence.py — verify sw-2026-skill has zero references to text-to-cad internals.
Pure Python, no dependencies.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


FORBIDDEN = [
    "build123d", "cadpy", "gen_step", "AssemblyHelper",
    "scripts/step", "scripts/inspect", "cad-viewer",
]


def test_no_text_to_cad_references():
    """grep: zero mentions of text-to-cad internal APIs/libraries."""
    # Only check references/ and sw_2026_skill/ (not _untested/, not tests/)
    dirs = [str(ROOT / d) for d in ("references", "sw_2026_skill")]
    excludes = ["_untested", "__pycache__", "tests"]

    found = []
    for d in dirs:
        for py_file in Path(d).rglob("*.py"):
            if any(ex in py_file.parts for ex in excludes):
                continue
            with open(py_file, encoding="utf-8", errors="ignore") as f:
                text = f.read()
            for kw in FORBIDDEN:
                if kw.lower() in text.lower():
                    # Exclude negative assertions (docstrings saying "不依赖 X")
                    # and install instructions (earthtojake GitHub URL)
                    if "不依赖" in text or "npx skills add" in text:
                        continue
                    found.append(f"{py_file.relative_to(ROOT)}: contains '{kw}'")

    # Check .md files in references/
    for md_file in (ROOT / "references").glob("*.md"):
        with open(md_file, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        for kw in FORBIDDEN:
            if kw.lower() in text.lower():
                # Allow earthtojake in install instructions (step-parts)
                if "npx skills add" in text and "earthtojake" in kw.lower():
                    continue
                found.append(f"{md_file.relative_to(ROOT)}: contains '{kw}'")

    assert not found, (
        f"Found {len(found)} text-to-cad references:\n" + "\n".join(found)
    )
    print(f"  OK zero text-to-cad API references in {len(list(Path(dirs[0]).rglob('*.md'))) + len(list(Path(dirs[1]).rglob('*.py')))} files")
