# Agent Chat Cluster 系统级架构设计

> 状态：MVP → 系统级架构升级草案  
> 日期：2026-06-20  
> 目标：把当前 script-driven MVP 升级为 event-driven、scheduler-controlled、state-centered 的受控多 Agent 系统。

---

## 1. 核心定位

Agent Chat Cluster 当前已经具备：

- 任务台账：`tasks/tasks.json`
- Agent 注册表：`config/agents.json`
- 策略配置：`config/policies.json`
- 审计日志：`logs/audit/*.jsonl`
- 轻量消息总线：`logs/messages/*.jsonl`
- 命令审批：`scripts/review_command.py`
- 任务分配策略：`scripts/suggest_assignee.py`
- 环境隔离校验：`scripts/test_isolation.py`

这些能力说明它已经不是纯文档方案，而是一个**可运行、可审计、可验证的多 Agent 协作 MVP**。

但当前架构仍以脚本为中心：

```text
human/operator → command/script → file update → audit log
```

下一阶段应升级为系统级控制流：

```text
request/event → event bus → scheduler/handler → state store → agent worker → result event → audit/replay
```

核心变化：

- 从“脚本驱动”升级为“事件驱动”；
- 从“人工派工”升级为“调度器控制”；
- 从“多个文件各管各的”升级为“统一状态事实源”；
- 从“失败后人工修补”升级为“可审计的容错恢复模型”。

---

## 2. 总体架构分层

### 2.1 Control Plane：主控/控制平面

职责：

- 接收用户任务请求；
- 创建任务事件；
- 调用策略检查；
- 触发调度器；
- 维护全局系统状态；
- 向用户汇报执行进度。

当前对应组件：

- OpenClaw 主会话 / 胖小；
- `scripts/create_task.py`
- `scripts/update_task.py`
- `scripts/dispatch_task.py`
- `scripts/complete_task.py`

未来演进：

- 引入统一 `controller.py` 或 `control_plane/` 模块；
- 所有外部命令先变成 event，再由 handler 消费；
- 主控不直接改任务文件，而是写入事件并等待状态更新。

---

### 2.2 Event Layer：事件层

职责：

- 接收所有系统动作；
- 统一记录事件；
- 支持异步处理；
- 支持事件回放；
- 支持失败重试与死信队列。

建议事件类型：

| Event Type | 说明 |
|---|---|
| `task.created` | 任务创建 |
| `task.validated` | 任务通过安全校验 |
| `task.assignee_suggested` | 调度器给出候选 Agent |
| `task.dispatched` | 任务派发给 Agent |
| `task.completed` | 任务完成 |
| `task.failed` | 任务失败 |
| `message.sent` | 主控向 Agent 发送消息 |
| `message.received` | Agent 接收消息 |
| `message.acked` | Agent ACK 消息 |
| `command.review_requested` | 命令进入审批 |
| `command.approved` | 命令审批通过 |
| `command.rejected` | 命令被拒绝 |
| `cost.updated` | 成本/资源统计更新 |
| `agent.heartbeat` | Agent 心跳 |
| `agent.disabled` | Agent 被禁用 |
| `audit.appended` | 审计日志追加完成 |

初期实现建议：

```text
logs/events/YYYY-MM-DD.jsonl
logs/dead_letter/YYYY-MM-DD.jsonl
```

每条事件最小结构：

```json
{
  "eventId": "EVT-20260620-000001",
  "eventType": "task.created",
  "timestamp": "2026-06-20T06:10:00Z",
  "source": "control-plane",
  "correlationId": "Task-001",
  "causationId": null,
  "payload": {},
  "policySnapshot": {},
  "status": "pending"
}
```

---

### 2.3 Scheduler：调度器

职责：

- 从事件层读取待调度任务；
- 根据任务优先级、Agent 能力、负载、风险级别、策略约束选择 Agent；
- 控制并发；
- 处理 backpressure；
- 控制 retry；
- 产生 `task.dispatched` 或 `task.blocked` 事件。

调度输入：

- 任务状态：priority/status/assignee/history；
- Agent 状态：enabled/riskLevel/cwd/currentLoad/capabilities；
- 策略：maxConcurrency/maxRetries/maxRuntimeMinutes/allowedPaths；
- 审计/历史：失败次数、超时次数、Agent 成功率；
- 消息状态：是否有未 ACK 的派工消息。

调度输出：

- selectedAgent；
- dispatchReason；
- constraints；
- retryPolicy；
- deadline；
- expectedOutputContract。

MVP 可复用：

- `scripts/suggest_assignee.py`
- `scripts/validate_task.py`
- `scripts/test_isolation.py`
- `scripts/review_command.py`

未来脚本：

```text
scripts/scheduler_tick.py
scripts/scheduler_state.py
scripts/retry_failed.py
```

---

### 2.4 Unified State Store：统一状态事实源

职责：

- 统一管理 task / agent / message / cost / scheduler 状态；
- 避免多个 JSON/JSONL 文件各自为政；
- 给控制平面、调度器、审计层提供一致视图。

初期仍可用标准库文件实现：

```text
state/system_state.json
state/locks/*.lock
state/snapshots/YYYY-MM-DDTHH-mm-ss.json
```

建议状态域：

```json
{
  "tasks": {},
  "agents": {},
  "messages": {},
  "scheduler": {},
  "cost": {},
  "policy": {},
  "audit": {}
}
```

演进路线：

1. 当前 JSON 文件保持不变；
2. 增加 `state_builder.py`，从 tasks/config/logs/messages 重建系统状态；
3. 增加 `state_snapshot.py`，定期生成快照；
4. 稳定后迁移 SQLite；
5. 若进入分布式，再评估 Redis/etcd。

---

### 2.5 Agent Worker Layer：Agent 执行层

职责：

- 接收主控派工；
- 在授权 cwd 内执行；
- 通过消息总线/任务协议回报；
- 不得绕过策略直接外发；
- 不得自我扩权；
- 不得启动未审批的子进程或危险命令。

当前 Agent：

| Agent | 状态 | 风险 | 角色 |
|---|---:|---:|---|
| `agent-exec-01` | enabled | low | resident executor |
| `agent-ext-01` | enabled | medium | extension worker |
| `agent-ext-02` ~ `agent-ext-06` | disabled | medium | reserved |

后续自治能力必须分级引入：

1. Worker：只执行明确任务；
2. Planner：可拆解子任务，但不能执行危险命令；
3. Tool-using Agent：可选工具，但每个工具需策略门禁；
4. Semi-autonomous Agent：可建议行动，但关键动作仍需审批；
5. Autonomous Cluster：必须有完整审计、回放、限流、熔断和人工接管。

当前建议停在 1→2 之间，别一口吃成胖子——系统会噎死。

---

### 2.6 Policy & Audit Plane：策略与审计平面

职责：

- 策略读取；
- 命令审批；
- 安全门禁；
- 审计日志；
- 环境隔离；
- 人工 override 记录。

当前已有：

- `config/policies.json`
- `scripts/review_command.py`
- `scripts/audit_log.py`
- `scripts/show_audit.py`
- `scripts/test_isolation.py`
- `docs/SECURITY_NOTES.md`

下一步增强：

- 每次事件处理附带 `policySnapshot`；
- 审计日志与事件日志通过 `eventId` 关联；
- 人工审批必须记录 reviewer、reason、scope、expireAt；
- 对危险命令统一进入 `command.review_requested`。

---

## 3. 端到端执行流程

### 3.1 当前 MVP 流程

```text
1. 用户提出任务
2. 主控创建 task
3. validate_task 校验台账
4. suggest_assignee 推荐 Agent
5. dispatch_task 生成派工提示
6. send_message 发给 Agent
7. Agent 执行并回报
8. complete_task 更新状态
9. audit_log 记录审计
```

### 3.2 系统级目标流程

```text
1. 用户提出任务
2. Control Plane 写入 task.created event
3. Event Handler 校验任务，写入 task.validated event
4. Scheduler 读取待调度任务
5. Policy Plane 检查策略、并发、路径、风险
6. Scheduler 选择 Agent，写入 task.dispatched event
7. Message Handler 发送派工消息
8. Agent Worker 执行任务
9. Agent 回报 result event
10. State Store 更新 task/agent/message/cost 状态
11. Audit Plane 追加审计
12. Control Plane 汇报结果
```

---

## 4. 最小可实施路线

### Milestone A：Event Layer 骨架

目标：先不改现有脚本，只增加事件记录能力。

交付物：

- `scripts/event_log.py`
- `logs/events/*.jsonl`
- `logs/dead_letter/*.jsonl`
- 事件 ID 生成与文件锁；
- event append / list / replay dry-run。

验收：

- 能追加 `task.created` / `message.sent` / `audit.appended`；
- 并发写入不撞 ID；
- JSONL 无 BOM；
- 事件可按 correlationId 查询。

---

### Milestone B：State Builder

目标：从现有文件重建统一状态。

交付物：

- `scripts/build_state.py`
- `state/system_state.json`
- `state/snapshots/*.json`

验收：

- 能读取 tasks/config/messages/audit/events；
- 能输出统一状态；
- 不修改原始业务文件；
- 校验失败时输出清晰错误。

---

### Milestone C：Scheduler Tick

目标：引入可控调度循环，但不自动执行真实 Agent。

交付物：

- `scripts/scheduler_tick.py`
- 支持 dry-run；
- 支持 maxConcurrency；
- 支持 retry limit；
- 支持 backpressure 判断；
- 输出调度决策事件。

验收：

- pending task 能被推荐 Agent；
- disabled Agent 不会被选中；
- 超过 maxConcurrency 时拒绝派发；
- 每次决策都有审计与事件。

---

## 5. 风险边界

继续坚持当前红线：

- 不自动启动真实 ACP Agent；
- 不自动外发网络请求；
- 不开放未审批全局广播；
- 不自动安装依赖；
- 不自动自愈；
- 不绕过 `config/policies.json`；
- 不让 Agent 访问未授权路径。

系统级升级不是“让 Agent 放飞自我”，而是给它们上笼头、仪表盘、刹车和黑匣子。否则多 Agent 不是智能集群，是一窝电子蟑螂。

---

## 6. 架构图

配套图文件：

```text
docs/architecture/system_architecture.html
```

图中包含：

- Human / Operator
- Control Plane
- Event Bus / Event Store
- Scheduler
- Unified State Store
- Agent Workers
- Policy & Audit Plane
- Dead Letter / Recovery

---

## 7. 下一步建议

推荐下一步先做 **Milestone A：Event Layer 骨架**。

理由：

1. 对现有 MVP 侵入最小；
2. 可以保留所有现有脚本；
3. 为 Scheduler 和 State Store 打基础；
4. 能立刻提高论文/项目叙事的系统性；
5. 风险低，收益高。

一句话：先把“发生了什么”记录成标准事件，再谈“谁来调度”和“状态归谁管”。
