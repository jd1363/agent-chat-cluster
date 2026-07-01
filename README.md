# Agent Chat Cluster — MVP

本项目旨在构建一个受控的多智能体协作平台，由 OpenClaw 主会话/项目经理作为主控/管理员负责决策，OpenCode/ACP Agent 作为执行工程师负责执行，逐步验证安全策略、任务调度与命令管控。

> **当前状态：MVP v1 收口完成（2026-07-01）**。Phase 0-3 全部验收通过，执行引擎 + Web Dashboard 已完成。详见 `ACCEPTANCE_STAGE2.md`、`ACCEPTANCE_STAGE3.md` 与 `PROJECT_STATUS.md`。
>
> **阶段 2 已完成 / 已验收**：双 Agent 启用、任务分配策略、命令审批节点、性能基线、轻量消息总线基础全部通过。
>
> **阶段 3 已完成 / 已验收**：真实 subagent 验证、list_tasks/check_env/show_audit 验证、receive_message 修复、ACK/重发、broadcast 策略门禁、消息 ID 锁全部收口。
>
> **执行引擎 + Dashboard 已完成（2026-07-01）**：真实执行引擎已接入（7 Agent → 5 CLI），Web Dashboard 已上线（实时控制面板 + 操作面板 + SSE 推送），CLI 链路测试通过（Codex/CodeWhale/OpenCode/MiMo），17 个 bug 修复。
>
> **系统级架构升级已启动但暂缓继续开发**：Milestone A/B/C（Event Layer / State Builder / Scheduler Tick）保留为 MVP v2 / Control Plane Prototype 预研；先完成旧方案 MVP v1 收口，不继续推进 Milestone D。详见 [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) 与 [`docs/architecture/system_architecture.html`](docs/architecture/system_architecture.html)。

## 交付入口

- **最终交付报告**：[`MVP_DELIVERY_REPORT.md`](MVP_DELIVERY_REPORT.md)
- **演示手册**：[`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md)
- **项目状态总表**：[`PROJECT_STATUS.md`](PROJECT_STATUS.md)
- **阶段 2 总验收**：[`ACCEPTANCE_STAGE2.md`](ACCEPTANCE_STAGE2.md)
- **阶段 3 总验收**：[`ACCEPTANCE_STAGE3.md`](ACCEPTANCE_STAGE3.md)

### 5 分钟演示路径

```powershell
python scripts\check_env.py --skip-external
python scripts\validate_task.py
python scripts\list_tasks.py --json
python scripts\dispatch_task.py --dry-run
```

详细流程见 [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md)。

## MVP 范围（当前阶段）

- **主控节点**：负责任务下发、状态跟踪、策略校验、命令审批。
- **双 Agent 架构**：`agent-exec-01`（resident/low）+ `agent-ext-01`（ext/medium）。
- **本地文件级任务台账**：`tasks/tasks.json` 记录任务生命周期。
- **环境自检脚本**：`scripts/check_env.py` 快速验证目录、配置与基础命令可用性。
- **任务协议与审计**：`docs/TASK_PROTOCOL.md` 定义派工与回报格式；`scripts/audit_log.py` 记录不可篡改审计日志。
- **真实执行引擎**：`dispatch_task --execute-real` → `executor_bridge` → 真实 CLI 工具（codex/codewhale/opencode/mimo/ollama），支持 `--project` 模式注入项目上下文、git diff 附加、file: 代码块解析写入文件，输出质量检测（失败信号正则匹配 + 输出过短检测）。
- **Web Dashboard**：实时控制面板（任务表格、Agent 状态、审计日志、成本图表），操作面板（行内执行/取消/重跑按钮，批量操作工具栏），PID 跟踪 + kill API，SSE 实时推送（任务状态变更、审计日志、Agent 状态）。
- **明确禁止的功能（MVP v1 / Phase 0-3）**：
  - 未审批的全局群聊 / 广播（受控主控多播必须显式人工确认）
  - 自动外发网络请求
  - 自动自愈（self-heal）
  - 高危险命令自动执行
  - 多 Agent 并发（当前最大并发 2）

## 快速开始

脚本支持从项目根目录运行，也可以从其他目录运行（脚本会自动定位项目根路径）。

```bash
# 环境自检
python scripts/check_env.py

# 仅检查目录与配置 JSON，跳过 openclaw 外部命令探测
python scripts/check_env.py --skip-external
```

```powershell
# Windows PowerShell: 编译检查全部脚本
python -c "import pathlib, py_compile; [py_compile.compile(str(p), doraise=True) for p in pathlib.Path('scripts').glob('*.py')]"
```

```bash
# 启动 Web Dashboard
python web/server.py --port 8765
# 浏览器打开 http://127.0.0.1:8765
```

```bash
# 查看当前策略
cat config/policies.json

# 添加任务
python scripts/create_task.py --title "验证网关状态" --priority high

# 更新任务
python scripts/update_task.py --id Task-001 --status done

# 派发任务（阶段 1）
# 注意：仅生成派工提示文件，不启动 Agent
# dispatch_task.py 会校验 assignee 是否在 config/agents.json 中且 enabled=true
python scripts/dispatch_task.py [--id Task-001] [--assignee agent-exec-01]

# 完成任务（阶段 1）
python scripts/complete_task.py --id Task-001 --status done --summary "任务已完成"

# 校验台账与 Agent 注册表（阶段 2 前置安全闸）
python scripts/validate_task.py

# 查看任务列表（支持按状态/assignee 过滤）
python scripts/list_tasks.py
python scripts/list_tasks.py --status pending
python scripts/list_tasks.py --assignee agent-exec-01
python scripts/list_tasks.py --json

# 查看审计日志（支持按日期/任务/事件类型过滤）
python scripts/show_audit.py
python scripts/show_audit.py --limit 5
python scripts/show_audit.py --event-type task_created
python scripts/show_audit.py --json

# 任务分配（基于 dispatch_task.py 自动选择 assignee）
python scripts/dispatch_task.py --id Task-001 --assignee agent-exec-01

# 成本/Token 估算台账（旧方案 /usage 的安全替代第一版）
python scripts/record_cost.py --agent-id agent-ext-01 --task-id Task-010 --input-tokens 1200 --output-tokens 800 --estimated-cost 0.03 --notes "manual estimate"
python scripts/record_cost.py --agent-id agent-ext-01 --input-tokens 1000 --output-tokens 500 --rate-input-per-1k 0.002 --rate-output-per-1k 0.006 --dry-run
python scripts/show_cost.py --by-agent
python scripts/show_cost.py --agent-id agent-ext-01 --budget 5
python scripts/show_cost.py --json --by-task

# 多维度只读告警检查（不自动修复）
python scripts/check_alerts.py
python scripts/check_alerts.py --json
python scripts/check_alerts.py --quiet   # 只显示 warning+critical

# 消息总线（阶段 2，轻量级主控→Agent 消息传递）
python scripts/send_message.py --to agent-ext-01 --message "check config"
python scripts/send_message.py --to agent-ext-01 --message "task dispatched" --json

# 受控主控多播（globalBroadcast 默认关闭；必须显式人工确认）
python scripts/send_message.py --to all --message "maintenance notice" --manual-approval
python scripts/broadcast.py --message "maintenance notice" --manual-approval --json

# 接收消息（获取最新未读消息）
python scripts/receive_message.py --agent-id agent-ext-01
python scripts/receive_message.py --agent-id agent-ext-01 --mark-read --json

# 查看消息历史（支持按收件人/发送者/状态/日期过滤）
python scripts/list_messages.py
python scripts/list_messages.py --to agent-ext-01
python scripts/list_messages.py --status sent --since 2026-06-18
python scripts/list_messages.py --json

# 事件日志（Milestone A：Event Layer 骨架）
python scripts/event_log.py append --event-type task.created --source test --correlation-id Task-001 --payload '{"title":"demo"}'
python scripts/event_log.py append --event-type task.created --json
python scripts/event_log.py list
python scripts/event_log.py list --date 2026-06-20 --event-type task.created --limit 10
python scripts/event_log.py list --correlation-id Task-001 --json
python scripts/event_log.py replay --dry-run
python scripts/event_log.py replay --date 2026-06-20 --dry-run --json

> ~~`build_state.py`（Milestone B）和 `scheduler_tick.py`（Milestone C）已删除，暂不维护。~~
```

## 项目结构

```
├── config/           # 策略与 Agent 注册表
├── docs/             # 可用命令说明、安全备忘、任务协议、系统架构设计
├── scripts/          # 运维与任务管理脚本
├── snapshots/        # 配置快照（按需生成）
├── tasks/            # 任务台账
└── README.md         # 本文件
```

## 阶段 1/2 脚本说明

| 脚本 | 用途 | 重要约束 |
|------|------|----------|
| `scripts/audit_log.py` | 审计日志记录，支持模块调用与 CLI | 仅标准库，按天切分 JSONL |
| `scripts/dispatch_task.py` | 从 tasks.json 选择 pending 任务，生成派工提示 | **不启动 ACP，不调用 opencode**；**拒绝未启用 assignee** |
| `scripts/complete_task.py` | 标记任务为 done/failed/blocked，更新台账 | 默认只允许 `in_progress` 任务结束；`--force` 管理员覆盖会进入审计 |
| `scripts/validate_task.py` | 校验台账完整性、ID 格式、status/priority 合法性、assignee 是否已启用 | 阶段 2 前置安全闸，失败 exit 1 |
| `scripts/list_tasks.py` | 只读查看任务列表，支持按 status/assignee 过滤，支持 JSON 输出 | 阶段 2 前置安全闸，只读不写 |
| `scripts/show_audit.py` | 只读查看审计日志，支持按日期/任务/事件类型过滤，支持 JSON 输出 | 阶段 2 前置安全闸，只读不写 |
| ~~`scripts/show_history.py`~~ | ~~已删除~~ | — |
| ~~`scripts/test_isolation.py`~~ | ~~已删除~~ | — |
| ~~`scripts/suggest_assignee.py`~~ | ~~已删除~~ | — |
| ~~`scripts/review_command.py`~~ | ~~已删除~~ | — |
| ~~`scripts/benchmark_pipeline.py`~~ | ~~已删除~~ | — |
| ~~`scripts/snapshot_config.py`~~ | ~~已删除~~ | — |
| `scripts/record_cost.py` | 写入本地成本/Token 估算台账 | 旧方案 `/usage` 替代第一版；只记录/估算，不自动暂停 Agent |
| `scripts/show_cost.py` | 查询成本/Token 台账，支持明细、按 Agent/任务汇总、预算阈值提示 | 预算只提示，不承诺精确账单 |
| ~~`scripts/command_map.py`~~ | ~~已删除~~ | — |
| `scripts/check_alerts.py` | 多维度只读告警检查：failed 任务/超时/Agent 状态/审计异常/未 ACK 消息/成本/日志体积 | 只读不写，不自动修复；退出码 0/1/2 表示 info/warning/critical |
| `scripts/send_message.py` | 主控向已启用 Agent 发送消息；`--to all` 需 `--manual-approval` | 阶段 2 消息总线，只写 |
| `scripts/broadcast.py` | 受控主控多播包装脚本；遵守 `globalBroadcast` 策略门禁 | 阶段 2 消息总线，只写 |
| `scripts/receive_message.py` | Agent 获取最新未读消息，支持标记为已读 / ACK | 阶段 2 消息总线，读+追加状态 |
| `scripts/list_messages.py` | 查询消息历史，支持按收件人/发送者/状态/日期过滤 | 阶段 2 消息总线，只读 |
| ~~`scripts/resend_unacked.py`~~ | ~~已删除~~ | — |
| `scripts/event_log.py` | 事件日志骨架：append/list/replay，按天 JSONL，跨进程并发安全 | Milestone A，读写，仅标准库 |
| ~~`scripts/build_state.py`~~ | ~~已删除~~ | — |
| ~~`scripts/scheduler_tick.py`~~ | ~~已删除~~ | — |

## 注意事项

- 所有脚本仅依赖 Python 标准库，无需安装额外包。
- 配置变更后建议重新运行 `check_env.py` 验证 JSON 合法性。
- `dispatch_task.py` 在阶段 1 仅生成 `logs/runs/Task-XXX_dispatch.md` 派工提示文件，**不会**自动启动 ACP agent 或执行任何命令。
