# 需求
为 solidworks-2026-skill 设计并运行分层测试。

工作目录: C:\Users\FKKXT\.claude\skills\solidworks-2026-skill

## 测试分层

### L1 — 安装与导入 (纯 Python, 无需 SW)
1. 所有公开符号可 import: SW, verify_step, Checker, VN, VBR 等
2. _com_helpers 14 符号全量可导入
3. _com_signatures 参数 tuple 长度正确 (FC3=26, FE3=23)
4. mcp.server 可导入 (without starting)

### L2 — 纯 Python 功能 (无需 SW)
5. verify_step() 对已知 STEP fixture 返回正确结果
6. _parse_step_entities 正确解析 STEP 文本
7. discover_refs 正确分类 hole/boss
8. Checker 类实例化

### L3 — 错误处理与边界 (无需 SW)
9. verify_step 对不存在的文件给出合理错误
10. verify_step 对空文件/非 STEP 文件不崩溃
11. _com_helpers 函数边界测试 (mm(0), deg(0), untuple(None))
12. feature_cut3_params 参数组合 (through_all/正常/dir_flag 变体)

### L4 — SW 连通性 (需 SW 运行 — 标记为 MANUAL)
13. SW 连接成功 (GetActiveObject)
14. 模板查找成功
15. 简单草图+拉伸+保存

# 验收标准
- [ ] L1: 5 项全部 PASS
- [ ] L2: 6 项全部 PASS
- [ ] L3: 11 项全部 PASS
- [ ] 现有 4 项测试无退化
- [ ] L4: 检测 SW 运行状态，输出 MANUAL 提示
