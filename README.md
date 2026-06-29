# solidworks-2026-skill

> SolidWorks 2026 Python COM automation toolkit — part modeling, assembly, mates,
> verification & export. Battle-tested through UR-SEU-2026 5-DOF robotic arm project.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20SW%202026-lightgrey)]()

## What

Python package + 121-tool MCP server for automating SolidWorks 2026 via COM API.
Every function backed by STEP-level geometric verification — no "console OK" trust.

- **Part modeling** — sketch, extrude, cut (FeatureCut3 verified signature), fillet, pattern
- **Assembly** — pose-level component insertion (AddComponent5 + Transform2 PUTREF)
- **Mates** — programmatic face selection (concentric, coincident, distance, gear, lock)
- **Verification** — STEP parsing with cylindrical face radius distribution (7D3S scoring)
- **Export** — STEP, STL, IGES, PDF, DXF via Extension.SaveAs
- **MCP server** — 121 tools for AI-driven CAD (Claude Desktop, Codex, Cursor)

## Quick Start

```bash
# Install
cd solidworks-2026-skill
pip install -e .

# Verify
python -c "from solidworks_2026_skill import SW, __version__; print(__version__)"

# Use in scripts
from solidworks_2026_skill import SW, verify_step

with SW("MyPart") as s:
    s.sketch_on_plane()
    s.circle(0, 0, 44)
    s.exit_sketch()
    s.extrude(6)
    s.check_faces("base")
    s.sketch_on_plane(("Front Plane", "前视基准面"))
    s.circle(0, 0, 10)
    s.exit_sketch()
    s.cut(through_all=True)
    s.check_faces("hole")
    s.save(r".", "MyPart")

ok, report = verify_step("MyPart.STEP",
    expected_holes=[(5.0, 1, "center hole")],
    max_circle=22)
print(report)
assert ok
```

## Requirements

- **OS:** Windows (SolidWorks is Windows-only)
- **SolidWorks:** 2026 (2024+ mostly compatible, verify FeatureCut3 signature)
- **Python:** 3.10+
- **Dependencies:** `pywin32>=305`, optional: `mcp>=1.0` (for MCP server)

## Security Model

- **MCP:** stdio transport — only local processes can interact. No network exposure.
- **File output:** restricted to `SW_OUTPUT_DIR` (default `./output/`). Path traversal blocked.
- **COM:** runs with the same privileges as the SolidWorks process.

## Module Map

| Need | Module | Docs |
|------|--------|------|
| Session + modeling (mm) | `solidworks_2026_skill.sw_session` | [SKILL.md](SKILL.md) |
| Low-level features (m) | `solidworks_2026_skill.sw_part` | [part-modeling.md](references/part-modeling.md) |
| Assembly pose insertion | `solidworks_2026_skill.sw_assembly` | [assembly.md](references/assembly.md) |
| Programmatic mates | `solidworks_2026_skill.sw_mate` | [assembly.md](references/assembly.md) |
| STEP verification + 7D3S | `solidworks_2026_skill.sw_verify` | [verification.md](references/verification.md) |
| Cross-part interface check | `solidworks_2026_skill.sw_check_interfaces` | [verification.md](references/verification.md) |
| Export (STEP/STL/PDF/DXF) | `solidworks_2026_skill.sw_export` | — |
| Environment preflight | `solidworks_2026_skill.sw_preflight` | [troubleshooting.md](references/troubleshooting.md) |
| VBA macro guard | `solidworks_2026_skill.sw_macro_guard` | — |
| MCP server (121 tools) | `mcp/server.py` | [SKILL.md](SKILL.md) |
| ⚠ Drawing / Motion / Appearance / Review | `solidworks_2026_skill._untested/` | [upstream/](references/upstream/) |

⚠ = from upstream, untested with UR-SEU-2026. Use at own risk.

## Known Limitations

See [SKILL.md](SKILL.md) for full list. Key ones:

- `CreateSpline`, `FeatureCut4`, `FeatureCircularPattern4` — broken in Python COM
- `GetMassProperties` — type mismatch
- In-assembly face selection — must use programmatic GetFaces, not SelectByID2

## Upstream Attribution

Forked from [wzyn20051216/solidworks-automation-skill](https://github.com/wzyn20051216/solidworks-automation-skill) (MIT).
References in `references/upstream/` and untested modules in `solidworks_2026_skill/_untested/` derive from that work.

## License

MIT — see [LICENSE](LICENSE) for full text.
