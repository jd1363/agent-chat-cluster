# -*- coding: utf-8 -*-
"""Update README.md and PROJECT_PLAN.md for 2026-07-01 milestone."""

import pathlib
import re

BASE = pathlib.Path(r"G:\agent-chat-cluster")

# ============================================================
# 1. Update README.md
# ============================================================
readme_path = BASE / "README.md"
readme = readme_path.read_text(encoding="utf-8")

# --- 1a. Update the blockquote status section ---
old_blockquote = """> **当前状态：MVP v1 收口中**。旧方案 Phase 0-3 是当前主线，阶段 2 已完成并验收，阶段 3 已完成并验收；详见 `ACCEPTANCE_STAGE2.md`、`ACCEPTANCE_STAGE3.md` 与 `PROJECT_STATUS.md`。
>
> **阶段 2 已完成 / 已验收**：双 Agent 启用、任务分配策略、命令审批节点、性能基线、轻量消息总线基础全部通过。
>
> **阶段 3 已完成 / 已验收**：真实 subagent 验证、list_tasks/check_env/show_audit 验证、receive_message 修复、ACK/重发、broadcast 策略门禁、消息 ID 锁全部收口。
>
> **系统级架构升级已启动但暂缓继续开发**：Milestone A/B/C（Event Layer / State Builder / Scheduler Tick）保留为 MVP v2 / Control Plane Prototype 预研；先完成旧方案 MVP v1 收口，不继续推进 Milestone D。详见 [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) 与 [`docs/architecture/system_architecture.html`](docs/architecture/system_architecture.html)。"""

new_blockquote = """> **当前状态：MVP v1 收口完成（2026-07-01）**。Phase 0-3 全部验收通过，执行引擎 + Web Dashboard 已完成。详见 `ACCEPTANCE_STAGE2.md`、`ACCEPTANCE_STAGE3.md` 与 `PROJECT_STATUS.md`。
>
> **阶段 2 已完成 / 已验收**：双 Agent 启用、任务分配策略、命令审批节点、性能基线、轻量消息总线基础全部通过。
>
> **阶段 3 已完成 / 已验收**：真实 subagent 验证、list_tasks/check_env/show_audit 验证、receive_message 修复、ACK/重发、broadcast 策略门禁、消息 ID 锁全部收口。
>
> **执行引擎 + Dashboard 已完成（2026-07-01）**：真实执行引擎已接入（7 Agent → 5 CLI），Web Dashboard 已上线（实时控制面板 + 操作面板 + SSE 推送），CLI 链路测试通过（Codex/CodeWhale/OpenCode/MiMo），17 个 bug 修复。
>
> **系统级架构升级已启动但暂缓继续开发**：Milestone A/B/C（Event Layer / State Builder / Scheduler Tick）保留为 MVP v2 / Control Plane Prototype 预研；先完成旧方案 MVP v1 收口，不继续推进 Milestone D。详见 [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) 与 [`docs/architecture/system_architecture.html`](docs/architecture/system_architecture.html)。"""

assert old_blockquote in readme, "Could not find old blockquote in README.md"
readme = readme.replace(old_blockquote, new_blockquote)

# --- 1b. Add Dashboard startup to 快速开始 section ---
# Find the 快速开始 section and add dashboard commands after the existing bash block
old_quick_start = """```powershell
# Windows PowerShell: 编译检查全部脚本
python -c "import pathlib, py_compile; [py_compile.compile(str(p), doraise=True) for p in pathlib.Path('scripts').glob('*.py')]"
```"""

new_quick_start = """```powershell
# Windows PowerShell: 编译检查全部脚本
python -c "import pathlib, py_compile; [py_compile.compile(str(p), doraise=True) for p in pathlib.Path('scripts').glob('*.py')]"
```

```bash
# 启动 Web Dashboard
python web/server.py --port 8765
# 浏览器打开 http://127.0.0.1:8765
```"""

assert old_quick_start in readme, "Could not find quick start section in README.md"
readme = readme.replace(old_quick_start, new_quick_start)

# --- 1c. Add 真实执行引擎 and Web Dashboard to MVP 范畴 section ---
old_mvp_scope = """- **明确禁止的功能（MVP v1 / Phase 0-3）**："""

new_mvp_scope = """- **真实执行引擎**：`dispatch_task --execute-real` → `executor_bridge` → 真实 CLI 工具（codex/codewhale/opencode/mimo/ollama），支持 `--project` 模式注入项目上下文、git diff 附加、file: 代码块解析写入文件，输出质量检测（失败信号正则匹配 + 输出过短检测）。
- **Web Dashboard**：实时控制面板（任务表格、Agent 状态、审计日志、成本图表），操作面板（行内执行/取消/重跑按钮，批量操作工具栏），PID 跟踪 + kill API，SSE 实时推送（任务状态变更、审计日志、Agent 状态）。
- **明确禁止的功能（MVP v1 / Phase 0-3）**："""

assert old_mvp_scope in readme, "Could not find MVP scope section in README.md"
readme = readme.replace(old_mvp_scope, new_mvp_scope)

readme_path.write_text(readme, encoding="utf-8")
print("README.md updated successfully")

# ============================================================
# 2. Update PROJECT_PLAN.md
# ============================================================
plan_path = BASE / "PROJECT_PLAN.md"
plan = plan_path.read_text(encoding="utf-8")

# Insert the 2026-07-01 update section after the 当前总状态 section
# Find the end of the 当前总状态 section (marked by the first --- after it)
old_status_section = """## 当前总状态（2026-06-20）

- **MVP v1 主线**：Phase 0-3，已完成并进入收口；详见 `ACCEPTANCE_STAGE0.md`、`ACCEPTANCE_STAGE1.md`、`ACCEPTANCE_STAGE2.md`、`ACCEPTANCE_STAGE3.md`。
- **MVP v2 / Control Plane Prototype 预研线**：Milestone A/B/C（Event Layer / State Builder / Scheduler Tick）已启动并有骨架产物，但当前暂缓继续开发，不替代旧方案验收。
- **当前下一步**：先完成 MVP v1 文档、验收与项目状态收口；不要继续开发 Milestone D 或新增系统化功能。

---"""

new_status_section = """## 当前总状态（2026-07-01）

- **MVP v1 主线**：Phase 0-3 全部验收通过，执行引擎 + Web Dashboard 已完成。详见 `ACCEPTANCE_STAGE0.md`、`ACCEPTANCE_STAGE1.md`、`ACCEPTANCE_STAGE2.md`、`ACCEPTANCE_STAGE3.md`。
- **MVP v2 / Control Plane Prototype 预研线**：Milestone A/B/C（Event Layer / State Builder / Scheduler Tick）已启动并有骨架产物，但当前暂缓继续开发，不替代旧方案验收。
- **当前下一步**：MVP v1 已收口；后续按需迭代。

---

## 2026-07-01 更新

### 执行引擎
- executor_bridge.py：把派工 prompt 转发给真实 CLI（codex/codewhale/opencode/mimo/ollama）
- run.py：一键 create+dispatch+execute+result
- 支持 --project 模式：自动注入项目上下文、附加 git diff、解析 file: 代码块写入文件
- 输出质量检测：失败信号正则匹配（中英文），输出过短检测

### Web Dashboard
- 实时控制面板：任务表格、Agent 状态、审计日志、成本图表
- 操作面板：行内执行/取消/重跑按钮，批量操作工具栏
- PID 跟踪 + kill API
- SSE 实时推送：任务状态变更、审计日志、Agent 状态

### CLI 链路测试结果
| Agent | CLI | 状态 | 备注 |
|-------|-----|------|------|
| Codex | codex exec | ✅ | 端到端验证通过 |
| CodeWhale | codewhale exec --auto | ✅ | stream-json 模式，26.6s |
| OpenCode | opencode run | ✅ | 26.2s，输出最清晰 |
| MiMo | mimo run | ✅ | 82.6s，有编码问题 |
| Ollama | ollama run | ⏸ | disabled，服务未运行 |

### Bug 修复（2026-06-30）
- 17 个问题修复（3 Critical + 6 High + 8 Medium）
- 12 个死脚本清理
- tasks.json 数据修正（cancelled/failed 任务补 notes）

---"""

assert old_status_section in plan, "Could not find old status section in PROJECT_PLAN.md"
plan = plan.replace(old_status_section, new_status_section)

plan_path.write_text(plan, encoding="utf-8")
print("PROJECT_PLAN.md updated successfully")
