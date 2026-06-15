# 装配设计账本

> 写 `add_mates.py` 之前必填。每条 silent frame mistake 背后都是一个没填的账本条目。
> 与 `assembly.md` 分工：后者 = API 怎么调，本文档 = 调之前怎么规划。

## 五账本

装配设计的所有空间决策、推断值、未验证假设收敛到五个结构化表。填完之前不动代码。

### 1. Robot Metadata

```text
名称: <装配体名>
目标消费者: SW 拖动验证 / STEP 导出 / Gazebo URDF / 3D 打印装配
单位约定: API 原生米, 人类接口毫米 (mm() 转换)
Frame 约定: REP-103 body convention (X前 Y左 Z上) 或 GB Y-up
坐标系: Y-up (GB 模板默认 TOP=法向Y FRONT=法向Z)
尺寸来源: CAD 草图 / 实测 / 供应商文档 / 假设
```

**UR-SEU-2026 实例：**

```text
名称: UR_SEU_2026_Arm
目标消费者: SW 拖动验证 + STEP 验收 + 3D 打印装配
单位约定: 米 (API 原生), mm() 转毫米
Frame 约定: GB Y-up, p_world = p_local·R + t
坐标系: Y-up (TOP=顶面), 行约定 R_rows_3x3
尺寸来源: CAD 零件 STEP 导出 + 齿轮参数矩阵 (AGENTS.md)
```

### 2. Link Ledger

每个要插入的组件一行。`local frame` 是零件自身坐标系（建模时的原点+朝向），`R` 是零件→世界的旋转，`t_mm` 是世界平移。

| Label | 文件 | Local Frame | R 矩阵 | t (mm) | 角色 |
|-------|------|------------|--------|--------|------|
| `<标签>` | `<SLDPRT路径>` | `<原点+朝向>` | `<3×3>` | `<x,y,z>` | `<功能>` |

**UR-SEU-2026 实例（摘录前 5 个）：**

| Label | 文件 | Local Frame | R | t (mm) | 角色 |
|-------|------|------------|---|--------|------|
| Base | Base.SLDPRT | 底板中心, Y-up | IDENT | (0, 0, 0) | 固定根 |
| J1H | JointHousing.SLDPRT | 筒底中心, Y-up | IDENT | (0, 46, 0) | J1 壳体 |
| J1M | MotorX35.SLDPRT | 电机轴心, Y-up | IDENT | (0, 18, 0) | J1 电机 |
| J1G | GearSet.SLDPRT | 行星组中心, Y-up | IDENT | (0, 51, 0) | J1 减速组 |
| J1K | HousingCap.SLDPRT | 端盖中心, Y-up | IDENT | (0, 67, 0) | J1 端盖 |

旋转矩阵速查（完整定义见 `build_assembly.py`）：

```python
IDENT   = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]    # 恒等
FLIP    = [[1, 0, 0], [0,-1, 0], [0, 0,-1]]    # 翻转180° (柱朝下)
AXIS_Z  = [[1, 0, 0], [0, 0, 1], [0,-1, 0]]    # local Y → world +Z (水平轴)
AXIS_NZ = [[1, 0, 0], [0, 0,-1], [0, 1, 0]]    # local Y → world -Z (翻转水平轴)
ARM_UP  = [[0, 1, 0], [0, 0, 1], [1, 0, 0]]    # local X → world +Y (臂竖直)
```

### 3. Joint Ledger

每个运动副一行。`parent` = 固定端组件，`child` = 运动端组件。`type` 决定 mate 组合。

| Joint | Type | Parent | Child | Axis (world) | 范围 |
|-------|------|--------|-------|-------------|------|
| `<关节名>` | revolute/prismatic/rigid | `<Label>` | `<Label>` | `<dx,dy,dz>` | `<角度/行程>` |

**UR-SEU-2026 实例：**

| Joint | Type | Parent | Child | Axis (world) | 范围 |
|-------|------|--------|-------|-------------|------|
| J1 | revolute | Base | J1C | (0, 1, 0) (Y轴) | ±180° |
| J2 | revolute | TT | J2C | (0, 0, 1) (Z轴) | ±135° |
| J3 | revolute | UA | J3C | (0, 0, -1) (-Z轴) | ±135° |
| J4 | revolute | FA | J4C | (0, 0, 1) (Z轴) | ±135° |
| J5 | revolute | WL | EF | 世界Y | ±90° |

关节 mate 组合（SW 实现）：
- **转动副 = 同心(Concentric) + 平面贴合(Coincident)** — 同心只锁径向，轴向自由
- **刚性组 = LOCK mate** — 螺栓连接的多零件组，拖动不散架
- **接地 = Fix** — 根零件

### 4. Mating Datum Ledger

每个 mate 对的面选择策略。**坐标选面不可靠 → 必须程序化。**

| Mate 对 | Moving 面 (怎么选) | Target 面 (怎么选) | Type | 轴向约束 |
|---------|-------------------|-------------------|------|---------|
| `<moving> → <target>` | `find_cyl_face(r=?)` / `find_plane_face(axis=?, pos=?)` | 同上 | Concentric/Coincident/Distance | 有/无 |

**UR-SEU-2026 实例（摘录 J1）：**

| Mate 对 | Moving 面 | Target 面 | Type | 轴向约束 |
|---------|----------|----------|------|---------|
| J1C→J1G 输出 | `find_cyl_face(r=5.0)` | `find_cyl_face(r=5.0)` | Concentric | — |
| J1C→J1G 端面 | `find_plane_face(axis=1, pos=0)` | `find_plane_face(axis=1, pos=6)` | Coincident | Y |
| J1H→J1G 外圈 | `find_cyl_face(r=16.0)` | `find_cyl_face(r=16.0)` | Concentric | — |
| Base→J1H 安装 | `find_cyl_face_at(r=1.25, axis=1, pos=0)` | `find_cyl_face_at(r=1.25, axis=1, pos=46)` | Concentric | — |
| Base→J1H 端面 | `find_plane_face(axis=1, pos=46)` | `find_plane_face(axis=1, pos=0)` | Coincident | Y |

同半径多孔用 `find_cyl_face_at(comp, r_mm, axis_idx, pos_mm)` 按局部坐标区分。参数是**零件局部系**坐标，非世界系。

### 5. Assumption Ledger

所有推断值、未验证假设显式记录。`confidence`：exact / estimated / placeholder / unknown。

| 假设 | 值 | 置信度 | 如果错会导致 |
|------|---|:--:|------|
| `<描述>` | `<采用的>` | estimated | `<影响>` |

**UR-SEU-2026 实例：**

| 假设 | 值 | 置信度 | 如果错会导致 |
|------|---|:--:|------|
| J5 舵机 SG90 力矩 0.176 N·m 够用 | 不验证 | placeholder | 末端抓不住 |
| FDM 孔公差 +0.2mm | 孔 φ3.4→φ3.2 建模 | estimated | 螺栓装不进 |
| 行星轮轴 φ3×14 压入 6mm | 6mm 压入深度 | estimated | 轴脱落 |
| J2 拉簧 0.5×6×40 平衡 | 40mm 自由长 | estimated | J2 力矩不足 |
| 滑动轴承 PLA+锂基脂 间隙 0.3mm | 柱 φ21.9 / 孔 φ22.2 | estimated | 卡死或松动 |

## 使用规则

1. **写 `add_mates.py` 前填满五个账本。** 每个 mate 对必须在 Mating Datum Ledger 中有对应的面选择策略。
2. **LAYOUT 列表直接复制 Link Ledger 的 R+t 数据。** 账本是 LAYOUT 的单事实来源。
3. **假设列不能空。** 不确定的值标 confidence=unknown，不能默默填个数。
4. **改设计时先改账本**，再改 LAYOUT + mate 脚本，最后重跑 `verify_assembly_poses`。
5. **新队员接手** → 先读账本理解空间布局，再读代码。

## 就绪判据

账本就绪当且仅当：
- 五个表全部有内容（不能有空表）
- Link Ledger 每行的 R 矩阵可以写出 3×3 数字
- Joint Ledger 每行的 axis 是具体向量（非 "Z轴" 模糊描述）
- Mating Datum Ledger 每行有具体的 `find_*` 调用策略
- Assumption Ledger 每行有 confidence 标注
