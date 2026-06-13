# Parent Project Import Scan

> Phase 0.5 产出。`scripts/` → `sw_2026_skill/` 重命名影响分析。

## Scan Commands Executed

```bash
grep -rn "from scripts\." tools/ --include="*.py"     # → 零命中
grep -rn "import scripts" tools/ --include="*.py"      # → 零命中
grep -rn "scripts/" AGENTS.md CLAUDE.md sw-2026-skill/SKILL.md sw-2026-skill/FEATURES.md
```

## Key Finding: ZERO impact on `tools/`

`tools/` 目录下所有 `.py` 文件通过 `tools/swlib.py`（本地独立 1597 行 SW COM 封装库）访问 SW，**不直接从 `scripts/` import**。

```
tools/build_*.py ──→ from swlib import SW, verify_step, ...
tools/swlib.py    ──→ 独立实现（无 scripts/ 依赖）
```

## Files Requiring Update

| File | Line(s) | Old Reference | New Reference |
|------|---------|---------------|---------------|
| `sw-2026-skill/mcp/server.py` | multiple | `sys.path.insert` + 内联 COM 逻辑 | `from sw_2026_skill import ...` |
| `sw-2026-skill/SKILL.md` | module nav table | `scripts/sw_session.py` etc. | `sw_2026_skill/sw_session.py` |
| `sw-2026-skill/FEATURES.md` | capabilities refs | `scripts/` | `sw_2026_skill/` |
| `AGENTS.md` | project structure | `03_Source_源代码/` (无 scripts/ 引用) | — no change |
| `CLAUDE.md` | modeling rules | references `tools/swlib.py` not `scripts/` | — no change |

## Note on `tools/swlib.py`

`swlib.py` 是 `sw-2026-skill/scripts/` 的**独立副本**（重复 `SW` 类、`verify_step`、`VN`/`VBR` 等）。应规划为 v1.1 任务：用 `from sw_2026_skill import SW, verify_step` 替代 swlib.py。
