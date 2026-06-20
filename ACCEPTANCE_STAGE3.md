# 阶段 3 总验收报告（MVP v1）

验收时间：2026-06-20
验收范围：旧方案 Phase 3「真实 subagent 验证与消息总线收口」
验收结论：**通过**

## 1. 验收定位

阶段 3 的目标是验证旧方案 MVP v1 在真实 subagent / Agent 执行语境下是否可控，而不是继续开发系统化升级线。

本阶段重点验证：

- 真实 subagent 能按任务执行只读脚本并回报；
- 失败任务可以解释、审计并用替代任务完成；
- 消息接收、ACK、重发、受控多播和消息 ID 并发安全完成收口；
- 不开启自由群聊，不引入新的 Scheduler / Event Layer 功能。

## 2. 真实 subagent 任务验证

| 任务 | 验收项 | 状态 | 说明 |
|---|---|---:|---|
| Task-003 | `list_tasks.py --json` | ✅ 完成 | 真实 subagent 成功执行只读任务列表查询，证明台账读取链路可用。 |
| Task-004 | `check_env.py` | ✅ 完成 | 真实 subagent 执行环境自检通过，证明基础目录/配置/Gateway 检查链路可用。 |
| Task-005 | `show_audit.py` | ⚠️ failed | `agent-exec-01` 子 Agent 被 SIGKILL，任务失败原因是执行会话异常，不是脚本能力失败。 |
| Task-006 | `show_audit.py` 重试 | ✅ 完成 | 改由 `agent-ext-01` 重试，成功返回 5 条审计记录，替代完成 Task-005 的验收目标。 |
| Task-007 | `resend_unacked.py` code review | ⚠️ failed | 子任务对 subagent 过大且涉及 G 盘读写，沙箱无 G 盘写入权限，被 SIGKILL/中断。 |
| Task-008 | `resend_unacked.py` code review 重试 | ✅ 完成 | 降低任务粒度后完成审查；确认 dry-run 设计良好，无明显安全问题。 |
| Task-009 | `receive_message.py` review 修复 | ✅ 完成 | 修复 mark_read、日志大小上限、OSError 脱敏、Python 3.8/3.9 类型兼容。 |
| Task-010 | 消息总线策略门禁与 ID 锁 | ✅ 完成 | 完成 broadcast 策略门禁、manualApproval 审计、消息 ID 跨进程锁。 |

## 3. Task-005 / Task-007 失败原因与替代完成关系

### Task-005

- 原目标：验证真实 subagent 能查看审计日志 `show_audit.py`。
- 失败原因：`agent-exec-01` 子 Agent 被强制终止（SIGKILL）。
- 风险判断：属于执行会话稳定性问题，不构成 `show_audit.py` 功能失败。
- 替代完成：Task-006 使用 `agent-ext-01` 重试并成功返回审计记录，因此该验收目标已完成。

### Task-007

- 原目标：对 `scripts/resend_unacked.py` 做 code review。
- 失败原因：任务粒度过大，涉及读取/写入 `G:\` 项目路径，实测沙箱无 G 盘写入权限，子 Agent 被 SIGKILL/中断。
- 风险判断：属于任务拆分与沙箱权限边界问题，不构成消息 ACK/重发能力失败。
- 替代完成：Task-008 缩小任务后完成 code review，确认 `resend_unacked.py` dry-run 与重发设计可接受。

## 4. 消息总线收口验收

| 验收项 | 产物 / 脚本 | 状态 | 说明 |
|---|---|---:|---|
| 点对点发送 | `scripts/send_message.py` | ✅ 通过 | 主控向已启用 Agent 发送消息，写入 `logs/messages/*.jsonl`。 |
| 消息接收 | `scripts/receive_message.py` | ✅ 通过 | 支持读取最新未读消息、标记已读、JSON 输出。 |
| receive_message 修复 | `scripts/receive_message.py` | ✅ 通过 | `mark_read()` 不再覆盖原始 `timestamp`，改写 `readAt`；增加 5MB 日志大小上限；OSError 脱敏；兼容 Python 3.8/3.9。 |
| ACK / 重发 | `scripts/resend_unacked.py` | ✅ 通过 | 支持 dry-run、重发、标记失败；经 Task-008 review 通过。 |
| 消息历史 | `scripts/list_messages.py` | ✅ 通过 | 支持收件人/发送者/状态/日期过滤，只读查询。 |
| broadcast 策略门禁 | `scripts/send_message.py --to all` / `scripts/broadcast.py` | ✅ 通过 | 读取 `config/policies.json`；当 `globalBroadcast.allowed=false` 时，必须显式 `--manual-approval`。 |
| 多播审计 | `logs/audit/*.jsonl` | ✅ 通过 | `broadcast_sent` 审计事件增加 `manualApproval` 字段。 |
| 消息 ID 锁 | `logs/messages/.state.lock` | ✅ 通过 | 为消息 ID 分配增加跨进程锁；并发回归得到不同 ID，无撞号。 |

## 5. 安全边界确认

阶段 3 收口后仍保持：

- 受控主控多播 ≠ Agent 自由群聊；
- globalBroadcast 默认关闭；
- `--manual-approval` 只是显式人工确认标记，不代表长期放开广播；
- ACK / 重发能力不允许无限重试，失败必须可审计；
- 消息 ID 使用锁保护，避免并发撞号导致审计/追踪混乱；
- 不在阶段 3 引入新的 Scheduler Tick 或 Event Layer 依赖。

## 6. 验收结论

阶段 3 已满足旧方案 MVP v1 的「真实 subagent 验证与消息总线收口」要求：

- 真实 subagent 执行链路已验证；
- 失败案例已解释并由替代任务完成；
- receive_message、ACK/重发、broadcast 策略门禁、消息 ID 锁均已完成；
- 阶段 3 可标记为 **已完成 / 已验收**。
