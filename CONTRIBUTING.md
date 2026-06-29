# Contributing

## Development Setup

```bash
cd solidworks-2026-skill
pip install -e ".[mcp]"
```

Requires: Windows, Python 3.10+, SolidWorks 2026, pywin32.

## Branch Model

- `master` — stable release
- Feature branches off `master`, PR to merge

## Commit Convention

```
<type>: <description>
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `checkpoint`

## COM API Verification

Before writing any SW COM code:

1. **Read the real signature** — `makepy` the type library first (see `references/com-patterns.md` pattern 4)
2. **Check Allowed APIs** — `references/allowed-apis.md` for known-broken APIs
3. **Verify with face count** — after every feature, `check_faces()` to detect silent failures
4. **STEP-verify the output** — `verify_step()` for final geometry check

## PR Checklist

- [ ] Syntax: all `.py` files parse
- [ ] Import: `from solidworks_2026_skill import SW` works
- [ ] No new `except: pass` without `traceback.print_exc()`
- [ ] No `time.sleep()` in `async def`
- [ ] All file writes go through `_validate_output_path()`
- [ ] markdownlint: zero warnings on changed `.md` files

## License

MIT — contributions licensed under the same.
