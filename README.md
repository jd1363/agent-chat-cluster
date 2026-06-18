# Agent Chat Cluster — MVP

本项目旨在构建一个受控的多智能体协作平台，由 OpenClaw 主会话/项目经理作为主控/管理员负责决策，OpenCode/ACP Agent 作为执行工程师负责执行，逐步验证安全策略、任务调度与命令管控。

## MVP 范围（当前阶段）

- **主控节点**：负责任务下发、状态跟踪、策略校验。
- **单执行 Agent**：仅启用一个示例执行 Agent，验证主控→Agent 的单向命令通道。
- **本地文件级任务台账**：`tasks/tasks.json` 记录任务生命周期。
- **环境自检脚本**：`scripts/check_env.py` 快速验证目录、配置与基础命令可用性。
- **任务协议与审计**：`docs/TASK_PROTOCOL.md` 定义派工与回报格式；`scripts/audit_log.py` 记录不可篡改审计日志。
- **明确禁止的功能（阶段 0）**：
  - 全局群聊 / 广播
  - 自动外发网络请求
  - 自动自愈（self-heal）
  - 高危险命令自动执行
  - 多 Agent 并发

## 快速开始

脚本支持从项目根目录运行，也可以从其他目录运行（脚本会自动定位项目根路径）。

```bash
# 环境自检
python scripts/check_env.py

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
```

## 项目结构

```
├── config/           # 策略与 Agent 注册表
├── docs/             # 可用命令说明、安全备忘、任务协议
├── scripts/          # 运维与任务管理脚本
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

## 注意事项

- 所有脚本仅依赖 Python 标准库，无需安装额外包。
- 配置变更后建议重新运行 `check_env.py` 验证 JSON 合法性。
- `dispatch_task.py` 在阶段 1 仅生成 `logs/runs/Task-XXX_dispatch.md` 派工提示文件，**不会**自动启动 ACP agent 或执行任何命令。
