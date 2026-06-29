# SW 选择器引用系统

> STEP 导出后自动发现圆柱面 → 分配标签 `#h1`/`#b1` → 写 `part_refs.json`。用于 mate 验证脚本。

## 为什么

SW 装配内选面靠程序化（`find_cyl_face` 等），但验证脚本运行时 SW 不一定开着。STEP 文件是唯一的几何事实来源。本系统从 STEP 中自动发现可引用的几何特征并分配稳定标签。

## 范围

**只做圆柱面（孔/凸台/轴承座）。** 不做平面——STEP 中 `PLANE` 不含边界，面选择不可靠。

## 工作流

```
SW 导出 STEP → discover_refs(step_path) → part_refs.json → "Bracket#h1"
```

## 选择器语法

```text
<零件名>#<类型><序号>
```

| 类型 | 含义 | 示例 |
|------|------|------|
| `h` | 孔 (hole, r < 20mm) | `JointHousing#h1` |
| `b` | 凸台/轴承座 (boss, r ≥ 20mm) | `Base#b1` |

> 20mm 阈值是启发式规则。可通过参数调整。

## 生成 refs JSON

```python
from solidworks_2026_skill.sw_selector_refs import discover_refs, write_refs_json

refs = discover_refs("D:/out/JointHousing.STEP")
# → {
#     "h1": {"radius": 1.25, "origin": (0.0, 46.0, 13.0), "axis": (0.0, 1.0, 0.0)},
#     "h2": {"radius": 1.25, "origin": (0.0, 46.0, -13.0), "axis": (0.0, 1.0, 0.0)},
#     "b1": {"radius": 22.0, "origin": (0.0, 46.0, 0.0), "axis": (0.0, 1.0, 0.0)},
#     ...
#   }

write_refs_json(refs, "D:/out/JointHousing_refs.json")
```

## 在验证脚本中使用

```python
from solidworks_2026_skill.sw_selector_refs import load_refs, format_ref
from solidworks_2026_skill.sw_check_interfaces import Checker

refs_a = load_refs("JointHousing_refs.json")
refs_b = load_refs("CarrierFlange_refs.json")

ck = Checker()
# 对比 PCD36 接口: JointHousing 的 h1-h4 vs CarrierFlange 的 h1-h4
ck.eq(f"{format_ref('JointHousing', 'h', 1)} PCD",
      pcd_and_angle([refs_a['h1']['origin'], ...])[0], 36.0)
```

## 排序规则

圆柱面按 `(radius, axis_idx, coordinate)` 排序分配序号：
1. 按半径分组（同半径 = 同一类特征）
2. 按轴向分组（同轴 = 同一面上的孔）
3. 按坐标排序（统一方向上的编号）

排序确保同一零件多次导出的 STEP 中标签一致（只要几何不变）。

## 限制

- **不做平面。** STEP `PLANE` 不含边界信息，regex 无法可靠区分不同平面面。
- **依赖 `sw_verify._parse_step_entities`。** 该函数是 internal helper，不保证跨版本 API 稳定。如果上游修改了返回格式，本模块需同步更新。
- **面序无保证。** 标签依赖于排序规则，如果几何拓扑变化（如加了一个孔），序号可能会变。
