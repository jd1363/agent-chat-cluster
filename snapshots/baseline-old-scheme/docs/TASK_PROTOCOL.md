# 任务协议 (Task Protocol)

本文档定义主控（OpenClaw / 项目经理）与执行 Agent（OpenCode / ACP Agent）之间的任务状态、派工消息格式与回报格式，以及执行 Agent 的行为约束。

**适用范围**：阶段 1（主控-单执行 Agent 闭环验证）。
**重要限制**：本阶段不启动任何 ACP agent，仅生成派工提示文件与审计日志。

---

## 1. 任务状态定义

任务在其生命周期中必须处于以下状态之一：

| 状态 | 说明 |
|------|------|
| `pending` | 任务已创建，等待主控派发。 |
| `in_progress` | 任务已派发给执行 Agent，正在处理中。 |
| `done` | 任务已成功完成，回报已采集。 |
| `failed` | 任务执行失败，需人工复核或重试。 |
| `blocked` | 任务因外部依赖或权限问题被阻塞，需人工介入。 |
| `cancelled` | 任务已被取消，不再执行。 |

状态流转规则：
- `pending` → `in_progress`（主控派发）
- `in_progress` → `done` / `failed` / `blocked`（执行 Agent 回报）
- `pending` / `in_progress` → `cancelled`（主控取消）
- `failed` → `in_progress`（主控决定重试，最多 1 次）

---

## 2. 主控 → 执行 Agent 派工消息格式

当主控决定派发任务时，生成一个派工提示文件（如 `logs/runs/Task-XXX_dispatch.md`），包含以下结构化信息：

```json
{
  "taskId": "Task-001",
  "title": "验证网关状态",
  "priority": "high",
  "constraints": {
    "maxRuntimeMinutes": 30,
    "maxOutputSizeKB": 1024,
    "workingDirectory": "G:\\agent-chat-cluster"
  },
  "allowedPaths": ["scripts/", "tasks/", "logs/", "config/", "docs/"],
  "forbiddenActions": [
    "不得私自外发网络请求",
    "不得启动其他 Agent",
    "不得修改文件或目录权限",
    "不得执行 rm -rf、format、fdisk、regedit 等危险命令",
    "不得访问 G:\\agent chat 原方案目录"
  ],
  "expectedOutput": "命令输出摘要或生成的文件路径",
  "auditRequirements": {
    "logCommands": true,
    "logFilesChanged": true,
    "reportRisks": true
  }
}
```

字段说明：
- `taskId`：任务唯一标识。
- `title`：任务标题，简述任务目标。
- `priority`：优先级 (`low` | `medium` | `high`)。
- `constraints`：执行约束，包括最大运行时间、输出大小、工作目录。
- `allowedPaths`：Agent 允许读写的相对路径列表。
- `forbiddenActions`：明确禁止的行为清单。
- `expectedOutput`：主控期望得到的输出形式。
- `auditRequirements`：Agent 必须在回报中包含的审计信息。

---

## 3. 执行 Agent → 主控 回报格式

任务执行完毕后（无论成功或失败），执行 Agent 必须向主控提供以下回报结构：

```json
{
  "summary": "任务执行的简要总结",
  "filesChanged": ["scripts/check_env.py", "logs/audit/2025-01-01.jsonl"],
  "commandsRun": ["python scripts/check_env.py"],
  "risks": ["未检测到风险"],
  "statusProposal": "done",
  "notes": "补充说明或异常详情"
}
```

字段说明：
- `summary`：对执行过程和结果的 1-3 句话总结。
- `filesChanged`：本次任务创建或修改的文件列表（相对路径）。
- `commandsRun`：执行过程中运行的命令列表。
- `risks`：识别到的风险项，若无可填 `["未检测到风险"]`。
- `statusProposal`：Agent 建议的终态 (`done` | `failed` | `blocked`)。
- `notes`：其他需要主控注意的补充信息。

**注意**：本阶段不通过 ACP 通道实际发送回报，仅通过 `scripts/complete_task.py` 由主控或执行工程师人工录入回报信息。

---

## 4. 执行 Agent 行为约束（安全红线）

以下约束为强制执行，违反即视为严重违规：

1. **不得私自外发**：禁止自动发起外部网络请求（HTTP、TCP、UDP 等），禁止向远程服务回传数据。
2. **不得启动其他 Agent**：禁止在任务执行过程中调用 `sessions_spawn`、`openclaw agent start` 或其他方式启动新的 Agent 进程。
3. **不得修改权限**：禁止执行 `chmod`、`chown`、`icacls`、`setfacl` 或任何改变文件/目录权限的操作。
4. **不得执行危险命令**：禁止执行 `rm -rf /`、`format`、`fdisk`、`regedit`、`mkfs`、`dd` 等可能导致系统损坏或数据丢失的命令。
5. **不得越权访问**：只能访问 `allowedPaths` 中列出的路径，禁止访问 `G:\\agent chat` 原方案目录或其他未授权路径。
6. **审计优先**：任何文件变更、命令执行必须如实记录，不得隐瞒或篡改。

---

## 5. 派工与回报流程（阶段 1）

```
主控
  │
  ├─ 从 tasks/tasks.json 选择 pending 任务
  │
  ├─ 运行 scripts/dispatch_task.py
  │     ├─ 生成派工提示 → logs/runs/Task-XXX_dispatch.md
  │     ├─ 更新任务状态 → in_progress
  │     └─ 写审计日志 → logs/audit/YYYY-MM-DD.jsonl
  │
  ├─ （本阶段不启动 ACP agent，由主控或执行工程师人工读取派工提示并执行）
  │
  ├─ 执行完成后，运行 scripts/complete_task.py
  │     ├─ 默认仅允许 in_progress → done / failed / blocked
  │     ├─ 如需管理员人工覆盖其他状态流转，必须显式使用 --force
  │     ├─ --force 会在审计日志中记录 previousStatus / newStatus / force
  │     ├─ 记录 output / notes / summary
  │     └─ 写审计日志 → logs/audit/YYYY-MM-DD.jsonl
  │
  └─ 任务闭环结束
```

---

*文档版本：Phase1-v1.0*
