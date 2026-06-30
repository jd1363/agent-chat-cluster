# 人工操作手册 (Operator Runbook)

> **适用角色**：项目经理 / 主控管理员 / 执行工程师
> **当前版本**：阶段 3 消息总线收口
> **上次更新**：2026-06-20

本文档描述 Agent Chat Cluster 日常运维的完整人工操作流程。所有操作通过 Python 脚本完成，**不依赖 ACP agent 运行**。

---

## 目录

1. [环境自检](#1-环境自检)
2. [创建任务](#2-创建任务)
3. [查看任务](#3-查看任务)
4. [校验任务](#4-校验任务)
5. [派发任务](#5-派发任务)
6. [~~命令审批~~（已删除）](#6-命令审批review_commandpy-已删除)
7. [完成任务](#7-完成任务)
8. [查看审计日志](#8-查看审计日志)
9. [~~性能基线~~（已删除）](#9-性能基线benchmark_pipelinepy-已删除)
10. [force 覆盖规则](#10-force-覆盖规则)
11. [禁止事项](#11-禁止事项)
12. [消息总线操作](#12-消息总线操作)
13. [何时可以进入真实 ACP 执行](#13-何时可以进入真实-acp-执行)
14. [执行引擎](#14-执行引擎)
15. [Agent 执行任务拆分原则](#15-agent-执行任务拆分原则)

---

## 1. 环境自检

在开始任何操作前，先运行环境自检确认目录和配置文件正常：

```bash
python scripts/check_env.py
```

检查项：
- 关键目录是否存在（`config/`, `docs/`, `scripts/`, `tasks/`, `logs/`）
- 配置 JSON 是否可解析（`config/agents.json`, `config/policies.json`, `tasks/tasks.json`）
- OpenClaw 网关命令是否可探测

**预期**：全部通过。如有失败项，先修复再继续。

---

## 2. 创建任务

```bash
# 创建一个中等优先级任务
python scripts/create_task.py --title "验证网关状态" --priority medium

# 创建高优先级任务
python scripts/create_task.py --title "修复配置错误" --priority high

# 创建低优先级任务
python scripts/create_task.py --title "更新文档" --priority low
```

参数：
- `--title`：任务标题（必填）。
- `--priority`：优先级，可选 `low` / `medium` / `high`（默认 `medium`）。

创建后：
- 任务被写入 `tasks/tasks.json`，状态 `pending`，assignee 为 `null`。
- 审计日志自动记录（`task_created` 事件）。
- 任务 ID 自动生成，格式 `Task-NNN`。

---

## 3. 查看任务

```bash
# 查看所有任务（按 ID 排序）
python scripts/list_tasks.py

# 只看 pending 状态
python scripts/list_tasks.py --status pending

# 只看 in_progress 状态
python scripts/list_tasks.py --status in_progress

# 按 assignee 过滤（已派发给 agent-exec-01 的任务）
python scripts/list_tasks.py --assignee agent-exec-01

# 查看未指派的任务
python scripts/list_tasks.py --assignee none

# JSON 输出（供其他脚本消费）
python scripts/list_tasks.py --json
```

说明：
- 只读操作，不修改任何文件。
- 两个过滤条件可组合使用：`--status pending --assignee none`。

---

## 4. 校验任务

```bash
python scripts/validate_task.py
```

校验内容：
- `tasks/tasks.json` 的 `schemaVersion` 存在。
- `tasks` 是 list。
- 每个任务必须有 `id`、`title`、`status`、`priority`。
- `id` 格式必须是 `Task-三位数字`（如 `Task-001`）。
- `status` 只能是 `pending` / `in_progress` / `done` / `failed` / `blocked` / `cancelled`。
- `priority` 只能是 `low` / `medium` / `high`。
- 如果任务有 `assignee`，该 assignee 必须存在于 `config/agents.json` 且 `enabled=true`。

**退出码**：全部通过 = 0，有错误 = 1。建议在派发/完成等写操作前先运行此校验作为安全闸。

---

## 5. 派发任务

```bash
# 派发第一个 pending 任务
python scripts/dispatch_task.py

# 派发指定任务
python scripts/dispatch_task.py --id Task-001

# 指定 assignee
python scripts/dispatch_task.py --id Task-001 --assignee agent-exec-01
```

派发流程：
1. 校验 `--assignee` 参数对应的 Agent 是否在 `config/agents.json` 中且 `enabled=true`。
2. 拒绝未启用或未注册的 assignee — 任务保持 `pending` 不变，不写任何文件。
3. 校验通过后：更新任务状态为 `in_progress`、生成派工提示文件到 `logs/runs/Task-XXX_dispatch.md`、写入审计日志。

**重要约束**：
- **不启动 ACP agent**。仅生成派工提示文件，由人工读取并手动执行。
- 只能派发 `pending` 状态的任务。
- 只能指派给已启用的 Agent。

---

## 6. ~~命令审批~~（`review_command.py` 已删除）

> **此脚本已删除。** 命令风险审批功能不再可用。如需审批，请人工判断。


## 7. 完成任务

```bash
# 正常完成（任务必须是 in_progress 状态）
python scripts/complete_task.py --id Task-001 --status done --summary "任务已完成"

# 标记失败
python scripts/complete_task.py --id Task-001 --status failed --summary "执行出错"

# 标记阻塞
python scripts/complete_task.py --id Task-001 --status blocked --summary "依赖未就绪"

# 管理员 force 覆盖（见第 8 节）
python scripts/complete_task.py --id Task-001 --status done --summary "管理员手动标记" --force
```

参数：
- `--id`：任务 ID（必填）。
- `--status`：终态，可选 `done` / `failed` / `blocked`（必填）。
- `--summary`：执行摘要（必填）。
- `--output`：可选，输出文件路径。
- `--force`：管理员覆盖状态机限制（见第 8 节）。

**注意**：默认只允许 `in_progress` → 终态。其他状态流转需 `--force`。

---

## 8. 查看审计日志

```bash
# 查看今天的审计记录（最近 20 条）
python scripts/show_audit.py

# 指定日期
python scripts/show_audit.py --date 2026-06-13

# 限制条数
python scripts/show_audit.py --limit 5

# 按任务过滤
python scripts/show_audit.py --task-id Task-001

# 按事件类型过滤
python scripts/show_audit.py --event-type task_created

# 组合过滤
python scripts/show_audit.py --date 2026-06-14 --event-type task_completed --limit 10

# JSON 输出
python scripts/show_audit.py --json
```

常见事件类型：
- `task_created` — 任务创建
- `task_dispatched` — 任务派发
- `task_completed` — 任务完成
- `task_failed` — 任务失败
- `task_blocked` — 任务阻塞
- `task_updated` — 任务更新

说明：
- 只读操作，不修改任何文件。
- 审计日志按天切分，路径为 `logs/audit/YYYY-MM-DD.jsonl`。
- 默认读取今天 UTC 日期的日志。

---

## 9. ~~性能基线~~（`benchmark_pipeline.py` 已删除）

> **此脚本已删除。** 性能基线报告功能不再可用。如需性能分析，请手动使用 `list_tasks.py` 查看任务状态分布。

## 10. force 覆盖规则

`--force` 是管理员人工覆盖状态机限制的机制，仅用于以下场景：

**允许 force 的场景**：
- 任务被错误标记为 `done`，需回退到 `in_progress`。
- 紧急情况下需将非 `in_progress` 任务直接标记为终态。
- 人工审计后确认需要绕过状态流转规则。

**force 的约束**：
- force 操作会在审计日志中记录 `previousStatus`、`newStatus` 和 `force: true`。
- force 不会自动校验业务逻辑，由操作者自行判断。
- force 只能用于 `complete_task.py`，不能用于 `dispatch_task.py`。

**不建议 force 的场景**：
- 正常状态流转 → 用不带 `--force` 的标准流程。
- 不确定状态 → 先运行 `validate_task.py` 和 `list_tasks.py` 确认当前状态。
- 可复现问题 → 先理解根因，不应当用 force 掩盖。

---

## 11. 禁止事项

以下行为**在任何阶段均禁止**：

### 绝对禁止

| 行为 | 说明 |
|------|------|
| `rm -rf /` 或递归删除 | 可能导致系统损坏 |
| `format` / `fdisk` / `mkfs` | 磁盘格式化/分区 |
| `regedit` 修改注册表 | 系统级配置修改 |
| `dd` 直接磁盘写入 | 数据破坏风险 |
| 自动外发网络请求 | 数据泄漏风险 |
| 自动启动 ACP agent | 未经人工审批 |
| 未审批全局广播/群聊 | 信息交叉污染；受控主控多播必须显式 `--manual-approval` 并记录审计 |
| 自动自愈 (self-heal) | 未经验证的自动修复 |
| 修改文件/目录权限 | 安全策略绕过 |
| 安装额外依赖 | 环境不可控 |

### 当前阶段（阶段 2）限制

- 不启动 ACP agent。
- 不安装第三方 Python 包（仅标准库）。
- 不删除 `G:\agent chat` 原方案目录。
- 不启用未审批的 ext Agent。

---

## 12. 消息总线操作

消息总线是主控向 Agent 发送指令的轻量通道。默认模式是点对点；`--to all` 只代表“主控受控多播到所有已启用 Agent”，不是 Agent 群聊。消息存储于 `logs/messages/YYYY-MM-DD.jsonl`，每条消息以 `MSG-XXXX` 格式自动编号，审计日志记录 `message_sent` / `broadcast_sent` 等事件。

策略门禁：`config/policies.json` 中 `communication.globalBroadcast.allowed=false` 时，任何多播必须显式传入 `--manual-approval`，否则脚本拒绝执行。

### 发送消息

```bash
# 主控向 Agent 发送消息
python scripts/send_message.py --to agent-ext-01 --message "check config"

# JSON 输出（供脚本消费）
python scripts/send_message.py --to agent-ext-01 --message "task dispatched" --json

# 受控主控多播：必须有人工确认
python scripts/send_message.py --to all --message "maintenance notice" --manual-approval
python scripts/broadcast.py --message "maintenance notice" --manual-approval --json
```

**约束**：
- 单播收件人必须在 `config/agents.json` 中存在且 `enabled=true`。
- 多播只发送给所有 `enabled=true` 的 Agent；当策略 `globalBroadcast.allowed=false` 时，必须显式 `--manual-approval`。
- 消息写入当日 JSONL 文件，自动递增消息编号。
- 审计日志自动记录（单播 `message_sent`，多播 `broadcast_sent`，并记录 `manualApproval` 字段）。

### 接收消息

```bash
# Agent 获取最新未读消息
python scripts/receive_message.py --agent-id agent-ext-01

# 接收并标记为已读
python scripts/receive_message.py --agent-id agent-ext-01 --mark-read

# 接收并发送 ACK 给 master
python scripts/receive_message.py --agent-id agent-ext-01 --ack

# JSON 输出
python scripts/receive_message.py --agent-id agent-ext-01 --json
```

说明：
- 扫描所有历史消息文件，返回该 Agent 最新一条 `status!=read` 的消息。
- `--mark-read` 会在日志末尾追加一条 `status=read` 的记录，不会修改原始发送记录；读取时间写入 `readAt`，保留原始 `timestamp`。
- `--ack` 会追加一条系统 ACK 消息，字段 `ackFor` 指向原消息 ID。
- 单个消息日志文件超过 5MB 时，`receive_message.py` 拒绝读取，防止日志膨胀拖垮脚本。
- 无未读消息时输出 `[INFO] No new messages`，不报错。

### 查看消息历史

```bash
# 查看最近 20 条消息
python scripts/list_messages.py

# 按收件人过滤
python scripts/list_messages.py --to agent-ext-01

# 按发送者过滤
python scripts/list_messages.py --from master

# 按状态过滤
python scripts/list_messages.py --status sent

# 按日期下限过滤
python scripts/list_messages.py --since 2026-06-18

# 组合过滤 + JSON 输出
python scripts/list_messages.py --to agent-ext-01 --status sent --json
```

说明：
- 只读操作，扫描所有历史 JSONL 文件，按时间倒序返回。
- 默认最多返回 20 条，使用 `--limit N` 可调整。
- 过滤条件可任意组合。

### ~~未 ACK 消息重发 / 失败处理~~（`resend_unacked.py` 已删除）

> **此脚本已删除。** 未 ACK 消息重发功能不再可用。如需检查未 ACK 消息，请使用 `list_messages.py --status sent` 手动查看。

## 13. 何时可以进入真实 ACP 执行

在以下条件**全部满足**后，可考虑进入真实 ACP agent 执行：

### 前置条件

1. **阶段 2 前置安全闸全部通过**：
   - `validate_task.py` 校验无误。
   - `dispatch_task.py` assignee 校验生效。
   - `list_tasks.py` / `show_audit.py` 可用。

2. **所有脚本经真实测试验证**：
   - 创建 → 校验 → 派发 → 完成 全流程至少跑通 3 次。
   - 异常路径（force、非法 assignee、非 pending 派发）均已覆盖。

3. **环境隔离确认**：
   - Agent 的 `cwd` 严格限制在项目内。
   - 禁止路径已配置（如原方案目录）。
   - 网络策略已启用。

4. **人工审批**：
   - 项目经理确认以上条件满足。
   - 审批记录写入审计日志。

### 首批可执行的任务类型

- 只读探查任务（如 `check_env.py`）
- 文档生成任务
- 数据校验任务

### 暂不执行的任务类型

- 需要网络请求的任务
- 需要修改系统配置的任务
- 需要高权限的任务
- 涉及多 Agent 并发的任务

---

*文档版本：Phase3-v1.2（消息总线策略门禁 + ACK/重发说明）*

---

## 执行引擎

### run.py — 一站式入口
创建任务 → 生成 prompt → 调用 executor_bridge 执行 CLI → 输出结果
用法: `python scripts/run.py --description "任务描述" --assignee agent-ext-02 --project "G:\目标项目"`

### executor_bridge.py — 真实 CLI 执行
接收 prompt 文件，调用对应 Agent 的 CLI 工具（Codex/CodeWhale/OpenCode/MiMo/Ollama）执行，
支持 `--project` 模式（CLI 工作目录设为目标项目）、`--write-output`（解析输出写入文件）、`--timeout`。

---

## 15. Agent 执行任务拆分原则

> **背景**：OpenClaw exec 工具有超时限制，单次命令超过阈值会收到 SIGKILL 信号（Windows 下为 TerminateProcess）。大任务如果不拆碎，会被强制中断，已完成的工作可能丢失。

### 核心原则

**每个子任务控制在 10 分钟以内。**

> 大任务 → 拆成 10 分钟以内的子任务 → 分别派工 → 各自 commit → 接续完成

### 何时必须拆分

| 任务类型 | 预估耗时 | 处理方式 |
|:---|:---|:---|
| 单一脚本修改 | <10 分钟 | 单次派工 |
| 多文件修改（>3个） | >10 分钟 | 按文件/模块拆成多个子任务 |
| 新脚本 + 修改已有文件 | >10 分钟 | 分两次：先写新脚本，再改旧文件 |
| 文档批量更新 | >10 分钟 | 按章节/文件拆 |
| 需要 read→analyze→write 循环 | >10 分钟 | 每轮循环单独派工 |

### 拆分示例

❌ 一次派工（易 SIGKILL）：
> "修改 scripts/send_message.py、增加 scripts/broadcast.py，然后 git add + commit"

✅ 分三次派工（各 <10 分钟）：
> 1. "修改 scripts/send_message.py，支持 --to all 多播参数，不要 git commit"
> 2. "新增 scripts/broadcast.py，调用 send_message.py 的 send_broadcast()，不要 git commit"
> 3. "新增 scripts/broadcast.py 完整实现，然后 git add + commit"

### SIGKILL 后如何接续

1. 检查 git status，看看哪些文件被改动了
2. 用 `git diff` 查看改动是否完整
3. 完整则手动 git add + commit；不完整则基于已有改动继续补完
4. 记录 SIGKILL 发生点，下一次派工时将任务拆得更细

### 任务描述规范

每个派工任务描述必须包含：
- **做什么**：明确文件/函数/功能
- **做到什么程度**：可验收的标准
- **不做什么**：明确排除范围（如"不要 git commit"）
- **完成后报告**：列出改动的文件和关键逻辑

### 与 cron job 的区分

- **需要人工交互/判断的任务** → 用 sessions_spawn 派给 Agent
- **纯后台定时任务（如 auto-snapshot）** → 用 cron job，不占用 exec 时间预算

---

## 注意事项

- 所有脚本使用 `fix_encoding.setup_utf8_stdout()` 统一 UTF-8 输出，新增脚本必须调用。

