"""Untested / dead-code modules preserved for reference.

Upstream (wzyn20051216/solidworks-automation-skill, MIT):
  sw_appearance, sw_drawing, sw_motion, sw_review — NOT verified with
  UR-SEU-2026 project. API signatures may be incorrect.

Native skill modules (lost all importers, moved 2026-06-29):
  sw_part.py — low-level part modeling (meter interface, sketches + features).
    sw_session.SW (mm) supersedes it; extrude_midplane is unique to this module.
  sw_macro_guard.py — VBA macro generation guard (LLM prompt/validate/template CLI).
    Standalone tool; no internal callers.

Use at your own risk.
"""

import warnings

warnings.warn(
    "solidworks_2026_skill._untested: modules from upstream solidworks-automation-skill, "
    "NOT tested with UR-SEU-2026. API signatures may be incorrect.",
    ImportWarning,
    stacklevel=2,
)
