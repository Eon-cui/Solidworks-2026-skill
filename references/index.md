# References Index

## Planning

| File | Topic |
|------|-------|
| [sw-brief.md](sw-brief.md) | Pre-modeling structured brief — write before any `with SW()` |
| [assembly-design-ledger.md](assembly-design-ledger.md) | Five-ledger assembly planning — fill before `add_mates.py` |

## Core

| File | Topic |
|------|-------|
| [allowed-apis.md](allowed-apis.md) | SW COM API compatibility matrix + anti-patterns |
| [com-api-table.md](com-api-table.md) | Full SW2026 COM API test status |
| [com-patterns.md](com-patterns.md) | VARIANT/gen_py/PUTREF/makepy patterns |
| [troubleshooting.md](troubleshooting.md) | 27 known issues by symptom + structured repair protocol |

## Workflows

| File | Topic |
|------|-------|
| [part-modeling.md](part-modeling.md) | Part modeling workflow |
| [assembly.md](assembly.md) | Assembly + mate workflow |
| [verification.md](verification.md) | Validation Pipeline (6-stage) + STEP verification + 7D3S |

## Verification

| File | Topic |
|------|-------|
| [snapshot-review.md](snapshot-review.md) | Mandatory SaveBMP+Pillow visual review |
| [selector-reference-system.md](selector-reference-system.md) | STEP cylinder discovery → `#h1`/`#b1` labels |

## External

| File | Topic |
|------|-------|
| [step-parts-integration.md](step-parts-integration.md) | step.parts API bridge — purchasable component STEP download |

## Upstream (wzyn20051216/solidworks-automation-skill, MIT, in `_untested/upstream/`)

| File | Topic | Tested? |
|------|-------|:------:|
| `_untested/upstream/api-lookup.md` | API verification process | No |
| `_untested/upstream/advanced.md` | Sheet metal, weldments, FEA | No |
| `_untested/upstream/appearance.md` | Material presets | No |
| `_untested/upstream/cnc-fillet-chamfer-lessons.md` | CNC filleting | No |
| `_untested/upstream/drawing.md` | Drawing API | No |
| `_untested/upstream/motion-study.md` | Motion study API | No |
| `_untested/upstream/review.md` | Review workflow | No |
| `_untested/upstream/threaded-hole-lessons.md` | Threaded hole API | No |

## Migration

| File | Topic |
|------|-------|
| [parent-imports.md](parent-imports.md) | scripts/ → sw_2026_skill/ impact analysis |
