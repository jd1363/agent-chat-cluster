# 命令参考 (COMMAND_REFERENCE.md)

> 本文档列出 Agent Chat Cluster 项目所有可用的真实命令，替代旧方案文档中的伪 slash 命令。

## 任务管理

| 功能 | 命令 |
|------|------|
| 创建任务 | `python scripts/create_task.py --title "标题" --priority high/medium/low` |
| 更新任务 | `python scripts/update_task.py --id Task-XXX --status pending/in_progress/done/failed/blocked/cancelled` |
| 查看任务列表 | `python scripts/list_tasks.py [--status STATUS] [--assignee AGENT_ID] [--json]` |
| 派发任务 | `python scripts/dispatch_task.py [--id Task-XXX] [--assignee AGENT_ID]` |
| 完成任务 | `python scripts/complete_task.py --id Task-XXX --status done/failed/blocked --summary "..."` |
| 校验台账 | `python scripts/validate_task.py` |
| 历史查询 | `python scripts/show_history.py [--status STATUS] [--assignee AGENT_ID] [--report] [--json]` |
| 分配建议 | `python scripts/suggest_assignee.py --title "标题" --strategy round_robin/load/specialist` |
| 命令审批 | `python scripts/review_command.py --agent-id AGENT_ID --command "CMD"` |
| 性能基线 | `python scripts/benchmark_pipeline.py [--mode lifecycle/agent] [--json]` |

## 消息总线

| 功能 | 命令 |
|------|------|
| 发送消息 | `python scripts/send_message.py --to AGENT_ID --message "..."` |
| 受控多播 | `python scripts/broadcast.py --message "..." --manual-approval` |
| 接收消息 | `python scripts/receive_message.py --agent-id AGENT_ID [--mark-read]` |
| 消息历史 | `python scripts/list_messages.py [--to AGENT_ID] [--status STATUS] [--json]` |
| 重发未 ACK | `python scripts/resend_unacked.py --dry-run/--resend/--mark-failed` |

## 审计与告警

| 功能 | 命令 |
|------|------|
| 查看审计 | `python scripts/show_audit.py [--date YYYY-MM-DD] [--task-id Task-XXX] [--event-type TYPE] [--json]` |
| 告警检查 | `python scripts/check_alerts.py [--json] [--severity info/warning/critical] [--quiet]` |

## 配置管理

| 功能 | 命令 |
|------|------|
| 环境自检 | `python scripts/check_env.py [--skip-external]` |
| 配置快照 | `python scripts/snapshot_config.py save/list/show/restore` |
| 环境隔离 | `python scripts/test_isolation.py [--json]` |

## 成本管理

| 功能 | 命令 |
|------|------|
| 记录成本 | `python scripts/record_cost.py --agent-id AGENT_ID --input-tokens N --output-tokens N [--estimated-cost N] [--task-id Task-XXX]` |
| 查看成本 | `python scripts/show_cost.py [--by-agent/--by-task] [--budget N] [--json]` |

## 命令映射

| 功能 | 命令 |
|------|------|
| 查询旧命令 | `python scripts/command_map.py --old "/task list"` |
| 列出全部 | `python scripts/command_map.py --list` |

## 系统级预研（MVP v2，暂缓）

| 功能 | 命令 |
|------|------|
| 事件日志 | `python scripts/event_log.py append/list/replay` |
| 状态构建 | `python scripts/build_state.py [--json] [--snapshot]` |
| 调度器 | `python scripts/scheduler_tick.py --dry-run [--json]` |

## 禁止使用的命令

以下命令在当前 MVP v1 阶段**明确禁止**，不要尝试执行：

| 禁止命令 | 原因 |
|---------|------|
| `openclaw --web --port 8080` | 非真实命令，使用 `openclaw gateway status/start/restart` |
| `/acp spawn --name ... --cmd ...` | 参数格式不匹配，需通过 `sessions_spawn` 创建 |
| `/self-heal restart-on-down` | `policies.json` 禁止自动自愈 |
| `/usage set-protection auto-pause` | 不实现自动暂停，改用硬限制 |
| `/acp broadcast full on` | 全局广播默认禁止，仅受控多播 |

## 标签管理

当前版本未实现独立标签管理脚本。Agent 标签可通过 `config/agents.json` 的 `notes` 字段手动维护。

后续如需标签查询能力，可在 `agents.json` 增加 `tags` 数组字段，并编写轻量查询脚本。

## 命令别名

当前版本未实现命令别名系统。建议使用方式：

- 在 `docs/COMMAND_REFERENCE.md` 查找真实命令
- 使用 `python scripts/command_map.py --old "/旧命令"` 查询映射
- 如需快捷别名，可通过 shell 函数或 PowerShell profile 设置

## 定时任务

定时任务通过 OpenClaw `cron` 工具实现，不在项目脚本内独立调度。

### 已配置的定时任务

| 任务 | 说明 |
|------|------|
| 自动快照提交 | 每 10 分钟检查 git 状态，有变更自动 commit（通过 OpenClaw cron job） |

### 可扩展的定时任务示例

- **定时配置快照**：通过 cron 定时调用 `python scripts/snapshot_config.py save --name auto-$(date)` 
- **定时告警检查**：通过 cron 定时调用 `python scripts/check_alerts.py --quiet`
- **定时成本报表**：通过 cron 定时调用 `python scripts/show_cost.py --by-agent`

> 注意：所有定时任务需先人工确认策略与输出目标，不自动启动高风险操作。
