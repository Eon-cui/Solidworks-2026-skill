# step.parts 外购件集成

> 建模前先查 step.parts API。能找到真实 STEP → 导入 → 验比例 → 省去手工建模。找不到 → 降级占位，不影响工作流。

## 独立性

step-parts 是独立 skill（`earthtojake/text-to-cad@step-parts`），与 text-to-cad 的 cad skill 无关。SW skill 不依赖 text-to-cad。

## 工作流

```
建模需要标准件 (螺丝/轴承/舵机/联轴器)
  → is_step_parts_installed()
    ├─ 已装 → search_standard_part("M3 SHCS 12", category="fastener")
    │         ├─ 命中 → download_and_import() → verify_step() 验比例 ✅
    │         └─ 无命中/超时 → create_placeholder_and_record_miss()
    └─ 未装 → create_placeholder_and_record_miss()
```

## 动态发现

不硬编码路径。查找顺序：

```python
def _find_step_parts_script():
    for base in [Path.home() / ".claude" / "skills",
                 Path(__file__).parent.parent.parent / "step-parts"]:
        sp = base / "step-parts" / "scripts" / "download_step_part.py"
        if sp.exists():
            return sp
    return None
```

## API 调用

```python
import subprocess, sys, json

result = subprocess.run(
    [sys.executable, str(script_path), "M3 socket head 12",
     "--limit", "5", "--timeout", "15"],
    capture_output=True, text=True, timeout=20
)
if result.returncode == 0:
    data = json.loads(result.stdout)
    items = data.get("items", [])
```

## 下载 + 导入 + 验证

```python
# 1. 下载
subprocess.run([sys.executable, str(script_path), part_id,
                "--download", "--out-dir", out_dir, "--overwrite"],
               capture_output=True, timeout=30)

# 2. SHA-256 校验 (download_step_part.py 内部已做)

# 3. 导入 SW
sw.OpenDoc6(step_path, 3, 0, "", VBR(), VBR())  # 3 = swDocPART
model = sw.ActiveDoc
model.SaveAs3(sldprt_path, 0, 0)  # 存为 SLDPRT

# 4. verify_step 验比例 (导入 STEP 可能是米制/英制)
ok, report = verify_step(step_path, expected_holes=[], bbox=expected_bbox)
if not ok:
    # 比例不对 → scale + re-save
    pass
```

## 中国网络降级

- **默认 timeout=15s。** api.step.parts 在中国可能不可达。
- **不可达 = 正常情况。** 不报错，不阻塞，静默降级到占位。
- `URLError` / `TimeoutExpired` → `return None` → 自动走 placeholder。
- 占位件记录在零件手册中标注 `(占位 — step.parts 不可达)`。

## 降级占位

```python
def create_placeholder_and_record_miss(sw, name, envelope):
    """
    envelope: {"type": "cylinder", "od": 5.5, "length": 12}
    或 {"type": "box", "w": 23, "d": 12, "h": 26}  (舵机 SMJ5)
    """
    with SW(name) as s:
        s.sketch_on_plane()
        s.circle(0, 0, envelope["od"])
        s.exit_sketch()
        s.extrude(envelope["length"])
        s.check_faces(f"{name} 占位")
        s.save(out_dir, name)
    return os.path.join(out_dir, f"{name}.SLDPRT")
```

## 依赖

- step-parts skill（独立安装：`npx skills add earthtojake/text-to-cad --skill step-parts -g -y`）
- 中国用户：step.parts API 可能不可达，降级策略已内置
