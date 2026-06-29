# Changelog

## [1.0.0] — 2026-06-13

### Added
- Python package `solidworks_2026_skill` (pip installable)
- 121-tool MCP server (`mcp/server.py`)
- MIT License
- Tool annotations (18 read-only tools)
- `_validate_output_path()` path traversal prevention
- `_untested/` isolation for 4 upstream modules
- `_compat.py` centralized stdout config
- `sw_preflight.get_sw_templates_dir/get_sw_install_dir/get_sw_tlb_path`
- `references/allowed-apis.md` + `references/parent-imports.md`

### Changed
- `scripts/` → `solidworks_2026_skill/` (Python package rename)
- `time.sleep` → `await asyncio.sleep` (8 async locations)
- `_vn`/`_byref_int` delegate to `solidworks_2026_skill.sw_session`
- 13× `except: pass` → `traceback.print_exc()`
- SKILL.md description: process summary → trigger conditions (CSO)

### Fixed
- `EditRebuild3` no-op in `sw_gear_create`
- `sw_review.run_review()` write-twice bug
- `sw_motion.py` hardcoded E: drive path removed
- `_byref_int` fallback now returns `.value`-capable object

### Removed
- `FIT_HOLE`, `FIT_SHAFT`, `FIT_PRESS` dead constants
- `VIEW_MAP` unused dictionary
- `M()` duplicate (now alias of `mm()`)
- `safe_get_com_member` duplicate (now alias)
- All inline `import re/json/glob` → module level
- `__pycache__/` directories
