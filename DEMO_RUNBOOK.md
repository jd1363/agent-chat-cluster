# Agent Chat Cluster — MVP v1 演示手册

适用版本：MVP v1（旧方案 Phase 0-3）
演示目标：用 5-10 分钟证明项目可运行、可管控、可审计、可安全演示。

> 所有命令均在 `G:\agent-chat-cluster` 项目根目录执行。
> 演示默认不启动真实 ACP 常驻 Agent，不外发网络请求，不执行危险命令。

---

## 0. 演示前准备

```powershell
cd G:\agent-chat-cluster
git status -s
```

预期：工作区干净，或仅有你明确知道的演示改动。

如需确认 Python 脚本语法：

```powershell
python -c "import pathlib, py_compile; [py_compile.compile(str(p), doraise=True) for p in pathlib.Path('scripts').glob('*.py')]"
```

---

## 1. 5 分钟快速演示路径

### Step 1：环境自检

```powershell
python scripts\check_env.py --skip-external
```

讲解点：

- 项目目录、配置文件、任务台账可解析；
- 演示跳过外部 OpenClaw 探测，避免现场环境波动。

---

### Step 2：查看任务台账

```powershell
python scripts\list_tasks.py
```

可选 JSON：

```powershell
python scripts\list_tasks.py --json
```

讲解点：

- 所有任务有 ID、状态、优先级、assignee；
- 当前 10 个任务中 8 个 done、2 个 failed；
- failed 任务不是烂尾，而是有替代完成关系。

---

### Step 3：查看历史统计报告

```powershell
python scripts\show_history.py --report
```

讲解点：

- 展示任务总数、状态分布、优先级分布、assignee 分布、审计统计；
- 证明项目不是散脚本，而是有台账和统计口径。

---

### Step 4：校验任务与 Agent 注册表

```powershell
python scripts\validate_task.py
```

讲解点：

- 校验任务 ID、状态、优先级；
- 校验 assignee 必须存在且 enabled=true；
- 这是派工前安全闸。

---

### Step 5：演示任务分配建议

```powershell
python scripts\suggest_assignee.py --title "演示任务：检查消息总线" --strategy load
```

可选 JSON：

```powershell
python scripts\suggest_assignee.py --title "演示任务：检查消息总线" --strategy load --json
```

讲解点：

- 系统能给出 Agent 分配建议；
- 但建议不等于自动派工，仍由主控决定；
- 这体现“受控多 Agent”，不是自动乱跑。

---

### Step 6：演示命令审批

安全命令：

```powershell
python scripts\review_command.py --agent-id agent-ext-01 --command "python scripts/list_tasks.py"
```

高风险命令示例：

```powershell
python scripts\review_command.py --agent-id agent-ext-01 --command "rm -rf /"
```

讲解点：

- 安全命令可被 APPROVED；
- 高风险命令会被 REJECTED；
- Agent 执行前有人工审批辅助。

---

### Step 7：演示消息总线点对点发送

```powershell
python scripts\send_message.py --to agent-ext-01 --message "demo: check message bus" --json
```

然后接收：

```powershell
python scripts\receive_message.py --agent-id agent-ext-01 --json
```

讲解点：

- 主控可以向指定 Agent 发送消息；
- Agent 可以读取消息；
- 消息写入本地 JSONL，便于审计。

如果不想产生新消息，可改用只读查询：

```powershell
python scripts\list_messages.py --to agent-ext-01 --limit 5
```

---

### Step 8：演示 ACK/重发 dry-run

```powershell
python scripts\resend_unacked.py --timeout-minutes 5 --dry-run --json
```

讲解点：

- 未 ACK 消息可以被扫描；
- dry-run 默认不写入，适合安全演示；
- 真正重发前先预览，避免误操作。

---

### Step 9：展示验收与交付文档

```powershell
Get-Content PROJECT_STATUS.md -TotalCount 80
Get-Content MVP_DELIVERY_REPORT.md -TotalCount 80
```

讲解点：

- Phase 0-3 是 MVP v1 主线；
- Milestone A/B/C 是 MVP v2 预研，不替代本次交付；
- 项目有明确边界和后续路线。

---

## 2. 推荐演示话术

### 30 秒项目介绍

> Agent Chat Cluster 是一个受控多 Agent 协作原型。它不是直接让 Agent 自由群聊，而是先把任务台账、派工、审批、审计、消息收发和安全边界做扎实。MVP v1 的目标是可运行、可管控、可追踪、可演示。

### 讲任务系统

> 每个任务都有 ID、状态、优先级和 assignee。所有派工前都会做安全校验，非法 Agent 或非法状态不会被写入。

### 讲安全

> 项目默认禁止自动外发、自动自愈、危险命令和未审批广播。多 Agent 能力是受控扩展，不是把权限放飞。

### 讲失败处理

> Task-005 和 Task-007 是真实执行中的失败案例。我们没有隐藏失败，而是记录原因，并通过 Task-006 和 Task-008 替代完成验收目标。这体现工程审计意识。

### 讲后续路线

> MVP v1 完成后，系统化升级路线才会考虑 Event Layer、State Store、Scheduler 和容错模型。目前 A/B/C 是预研骨架，Milestone D 暂缓。

---

## 3. 安全演示清单

演示时优先使用这些命令：

```powershell
python scripts\check_env.py --skip-external
python scripts\validate_task.py
python scripts\list_tasks.py
python scripts\show_history.py --report
python scripts\show_audit.py --limit 5
python scripts\suggest_assignee.py --title "demo task" --strategy load
python scripts\review_command.py --agent-id agent-ext-01 --command "python scripts/list_tasks.py"
python scripts\list_messages.py --limit 5
python scripts\resend_unacked.py --timeout-minutes 5 --dry-run --json
```

这些命令以只读或 dry-run 为主，适合现场展示。

---

## 4. 谨慎演示命令

以下命令会写入本地日志或台账，演示前要确认：

```powershell
python scripts\send_message.py --to agent-ext-01 --message "demo" --json
python scripts\receive_message.py --agent-id agent-ext-01 --mark-read --json
python scripts\create_task.py --title "demo task" --priority low
python scripts\dispatch_task.py --id Task-XXX --assignee agent-ext-01
python scripts\complete_task.py --id Task-XXX --status done --summary "demo done"
```

说明：

- 可以演示，但会产生真实记录；
- 演示后应根据需要 commit 或清理测试数据；
- 不建议在正式汇报中随手创建大量垃圾任务。

---

## 5. 禁止现场演示

不要现场运行：

```powershell
rm -rf /
del /f /s
format
shutdown
curl ... | bash
pip install ...
npm install ...
```

也不要现场开启：

- 未审批全局广播；
- 自动自愈；
- 自动外发；
- 未验证的 ACP 常驻 Agent；
- Milestone D 或更后续的系统化自动调度。

---

## 6. 如果演示失败怎么办

### 环境自检失败

先检查：

```powershell
git status -s
python scripts\check_env.py --skip-external
```

如果是外部 OpenClaw 探测问题，演示可使用 `--skip-external`，因为 MVP v1 本地脚本仍可展示。

### 消息演示失败

先用只读命令替代：

```powershell
python scripts\list_messages.py --limit 5
```

再解释消息写入是本地 JSONL，避免现场产生新垃圾消息。

### 任务状态不符合预期

先运行：

```powershell
python scripts\validate_task.py
python scripts\show_history.py --report
```

不要直接 force；force 只用于管理员审计后覆盖。

---

## 7. 演示结束后

```powershell
git status -s
python scripts\show_history.py --report
```

如果产生了演示记录，选择：

- 保留并 commit；或
- 如果只是临时垃圾，按项目规则审慎清理，避免破坏审计链。

---

## 8. 最短演示版本

如果只有 3 分钟，只跑这 5 条：

```powershell
python scripts\check_env.py --skip-external
python scripts\validate_task.py
python scripts\show_history.py --report
python scripts\suggest_assignee.py --title "demo task" --strategy load
python scripts\review_command.py --agent-id agent-ext-01 --command "rm -rf /"
```

讲解结论：

> 项目能自检、能校验台账、能统计历史、能做 Agent 分配建议、能拒绝危险命令。这就是 MVP v1 的核心价值：受控、可审计、可演示。
