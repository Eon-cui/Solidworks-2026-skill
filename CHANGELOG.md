# Changelog

## [1.2.0] — 2026-06-29

### Added
- `face()` 13-point coordinate retry (center → 4-way → 8-way offsets)
- `TestL3ErrorMessages` regression tests for error message format
- `plane()` defaults: English-first names (Front/Top/Right + Chinese fallback)

### Changed
- **All runtime messages English** (~55 raises/prints/returns across 7 modules)
- `sketch_on_face()` docstring warns users to prefer `sketch_on_plane()`
- `connect()` now thin wrapper around `connect_solidworks()` (backward compat)
- `DOC_TYPE_LABELS`: Chinese → English
- Quick Start examples: `sketch_on_face` → plane-based workflow (SKILL.md + README.md)

### Fixed
- README.md Quick Start: `expected_holes` mismatch (no hole but asserted one)
- `sw_connect.py` sed artifacts (`.unknown.` / `.GetPathName.` f-string breakage)

## [1.1.0] — 2026-06-29

### Added
- `_com_helpers.py`: VN/VBR/mm/_v/genmod unified (14 symbols, 4→1)
- `_com_signatures.py`: FeatureCut3/FeatureExtrusion3 param factory (3→1)
- `mcp/` moved into `solidworks_2026_skill/` (wheel-included)
- `_validate_output_path()` wired into 6 MCP output tools
- `CoUninitialize()` paired in `SW.__exit__` + MCP atexit
- Plane/View bilingual fallback in MCP server
- L1-L3 test suite (26 tests)

### Changed
- All module imports → `_com_helpers` single source
- `SW.cut`/`SW.extrude` → delegate to `_com_signatures`
- `sw_part.py` / `sw_macro_guard.py` → `_untested/` (dead code)
- Pillow import lazy + user-friendly error

### Fixed
- `sw_step_parts.py`: 3 P0 bugs (import path, method name, VARIANT wrapping)
- `pyproject.toml`: `comtypes>=1.2.0` dependency + mcp entry point
- `sw_export.py`: `create_empty_dispatch_variant` → `VN`
- `references/assembly.md` import paths
- `CODE_OF_CONDUCT.md`: full Contributor Covenant 2.1

## [1.0.1] — 2026-06-29 (Phase 1 P0 fixes)

### Fixed
- `sw_step_parts.py`: VBR/VN import → `sw_session`, `rect_center` → `rect`, VARIANT wrapping
- `pyproject.toml`: mcp entry point fixed, `comtypes>=1.2.0` added
- Test suite: built-in STEP fixture, `import pytest`

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
