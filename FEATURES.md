# FEATURES — sw-2026-skill 能力清单

> 给人类看的。Agent 入口请读 [SKILL.md](SKILL.md)。

## 这个 Skill 是什么

UR-SEU-2026 五自由度机械臂项目（东南大学）全程用 Python COM 脚本操控 SolidWorks 2026 完成
**13 种打印零件建模 + 32 实例装配体 + 43 个配合**，期间踩完 27 条坑并全部破解沉淀。
本 Skill = 自建公共库（swlib）+ 自建 mate 自动化 + 自建验收体系 + 121-tool MCP server
+ 开源 solidworks-automation-skill（修复其坑后）的大一统封装。

## 能做什么

| 能力 | 入口 | 验证强度 |
|------|------|----------|
| 零件建模（草图/拉伸/切除/圆角/阵列） | `scripts/sw_session.py` (毫米) / `scripts/sw_part.py` (米) | 35+ 零件实战，全部 STEP 几何级 PASS |
| 切除（最大坑区） | `SW.cut()` / `extrude_cut()` — FeatureCut3 验证签名 + Dir 自动重试 | makepy 签名 + 方向矩阵穷举实测 |
| 装配体位姿级插入（含旋转） | `sw_assembly.add_component_posed()` | 32/32 位姿 ±0.1mm 验收 |
| 配合自动化（同心/贴合/距离/齿轮/LOCK/固定） | `scripts/sw_mate.py` 程序化面选择 | 43 配合全成功 + 复验零漂移 |
| 可拖动演示装配体 | LOCK 刚性组 + 关节同心 + 轴向贴合 | 实测拖不散、关节可转 |
| 零件验收 | `sw_verify.verify_step()` STEP 圆柱面半径分布 | 防假成功 L3 |
| 装配验收 | `sw_verify.verify_assembly_poses()` 位姿矩阵 | 防假成功 |
| 7D3S 量化评分 | `sw_verify.score_s1/score_s2/verdict_7d3s` | S1/S2 全自动 |
| 跨零件接口校验 | `scripts/sw_check_interfaces.py` | 33 项配对实战 |
| 导出 STEP/STL/IGES/PDF/DXF | `scripts/sw_export.py` | Extension.SaveAs 实测 |
| 环境自检 | `scripts/sw_preflight.py` | 依赖+SW 安装+COM 注册 |
| VBA 宏防护 | `scripts/sw_macro_guard.py` | 模型分流+模板兜底+校验 |
| AI 客户端交互操控 | `mcp/server.py` — 121 tools (stdio MCP) | 项目全程主力 |

## 不能做什么（明确边界）

- **CreateSpline**：Python COM 不可用 → 多段线近似（≤20 齿）或 VBA
- **FeatureCut4 / FeatureCircularPattern4**：静默失败，已从全部代码中移除
- **SaveAs4 导 STEP**：4KB 空壳 → 一律 Extension.SaveAs
- **GetMassProperties / SetDisplayMode**：不可用，包围盒估算 / 手动
- **异型孔向导**：未封装（普通孔+沉孔两步切除替代）
- **装配体内坐标选面**：视线射线拾取不可靠 → 只用程序化面选择
- 工程图/运动算例/审查/外观：上游脚本已收录（`sw_drawing/motion/review/appearance.py` + `references/upstream/`）但**未经本项目实测**，用前验签名
- 钣金/焊件/仿真：仅 upstream 参考文档（`references/upstream/advanced.md`）

## 测试覆盖（全部来自真实项目交付）

| 验证项 | 规模 | 结果 |
|--------|------|------|
| 零件 STEP 几何级验收 | 13 种零件 ×（孔径分布+外径） | 全 PASS |
| 装配位姿级验收 | 32 实例 ×（origin ±0.1mm + 轴向 ±0.01） | 32/32 |
| 配合 | 5 同心 + 5 轴向贴合 + 24 LOCK + 2 指轴 + 2 距离 + 1 齿轮 + 1 固定 | 43/43 + 复验零漂移 |
| 接口交叉校验 | 33 项 PCD/孔径/方距/角度配对 | 33/33 |
| MCP tools | 121 个 | 项目全程在用 |

## 27 条踩坑去哪了

- 6 条致命坑 → SKILL.md 十条铁律
- 全部 27 条 → `references/troubleshooting.md`（按症状查）
- API 级结论 → `references/com-api-table.md`（实测状态表）
- 调用模式 → `references/com-patterns.md`（VARIANT/gen_py/PUTREF/makepy 四件套）

## 版本

- 2026-06-12 v1.0 — 初版大一统（UR-SEU-2026 V9 交付后封装）
- 适配 SolidWorks 2026（类型库版本 0,34）；2024+ 大部分模式通用，FeatureCut3 签名建议按 com-patterns 模式 4 重读确认
