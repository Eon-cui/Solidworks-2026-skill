# SolidWorks Connection Reference

> Which connect function to use and what to expect.

## Functions

| Function | Module | Returns | Use case |
|----------|--------|---------|----------|
| `connect_solidworks()` | `solidworks_2026_skill.sw_connect` | `(sw, model)` tuple | **Preferred.** Full control: GetActiveObject first, Dispatch fallback. `model` may be None if no document is open. |
| `connect()` | `solidworks_2026_skill.sw_session` | `sw` (bare SldWorks object) | **Thin wrapper** around `connect_solidworks()`. Kept for backward compatibility. New code should use `connect_solidworks()`. |

## Behavior

1. **GetActiveObject first** — tries to attach to a running SW instance
2. **Dispatch fallback** — if no instance is running, launches a new one
3. `visible=True` (default) makes the new instance visible; `wait_seconds` controls startup grace period

## Examples

```python
# Recommended
from solidworks_2026_skill.sw_connect import connect_solidworks
sw, model = connect_solidworks()
print(f"SW revision: {sw.RevisionNumber}")
if model:
    print(f"Active doc: {model.GetTitle}")

# Legacy (backward compat)
from solidworks_2026_skill.sw_session import connect
sw = connect()
```

## Common pitfalls

- `connect_solidworks()` returns a **tuple** — unpack both values even if `model` is None
- `SW.__enter__` calls `pythoncom.CoInitialize()` explicitly; `connect_solidworks()` does not
- Always `CloseAllDocuments(True)` before starting a new modeling session
