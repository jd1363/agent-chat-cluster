# 项目路线图

## 核心理念

**先主控 + 1 个 Agent，禁止一上来全局群聊。**

所有功能从最小可控单元验证，逐步扩展。未经验证的能力默认关闭。

---


## 当前总状态（2026-06-20）

- **MVP v1 主线**：Phase 0-3，已完成并进入收口；详见 `ACCEPTANCE_STAGE0.md`、`ACCEPTANCE_STAGE1.md`、`ACCEPTANCE_STAGE2.md`、`ACCEPTANCE_STAGE3.md`。
- **MVP v2 / Control Plane Prototype 预研线**：Milestone A/B/C（Event Layer / State Builder / Scheduler Tick）已启动并有骨架产物，但当前暂缓继续开发，不替代旧方案验收。
- **当前下一步**：先完成 MVP v1 文档、验收与项目状态收口；不要继续开发 Milestone D 或新增系统化功能。

---

## 阶段 0：基础骨架（已验收）

目标：建立最小可运行环境，确保主控与一个示例 Agent 能协同工作。

- [x] 目录结构初始化
- [x] 策略文件：默认禁用高危险功能
- [x] Agent 注册表：仅启用一个示例执行 Agent
- [x] 任务台账：JSON 格式，支持 CRUD 脚本
- [x] 环境自检脚本
- [x] 文档：可用命令与安全备忘

**原则**：阶段 0 不启动任何 ACP agent，不安装依赖，不执行危险命令。

---

## 阶段 1：主控-单 Agent 闭环验证（已验收）

目标：建立协议与审计层，验证主控→Agent 的派工提示生成与任务状态闭环，但**仍不启动 ACP agent**。

- [x] 定义任务状态：pending, in_progress, done, failed, blocked, cancelled
- [x] 定义主控→Agent 派工消息格式与 Agent→主控回报格式
- [x] 实现审计日志模块 `scripts/audit_log.py`（标准库，按天 JSONL）
- [x] 实现任务派发脚本 `scripts/dispatch_task.py`（生成派工提示，不启动 Agent）
- [x] 实现任务完成脚本 `scripts/complete_task.py`（更新台账，无外部动作）
- [x] `create_task.py` / `update_task.py` 增加 UTC ISO 时间戳与审计日志
- [x] 更新 README.md 与 PROJECT_PLAN.md

**限制**：
- 仍只启用 1 个 Agent（概念上）
- 禁止全局广播
- 禁止自动外发
- 禁止自动自愈
- 禁止危险命令
- **明确不启动 ACP agent，仅做派工协议、日志和本地脚本**

---

## 阶段 2：可控扩展至多 Agent（已验收，MVP v1）

目标：在阶段 1 验证通过的前提下，谨慎扩展至多 Agent 场景。

### 前置安全闸（已实现）

- [x] `scripts/validate_task.py` — 校验台账完整性、ID 格式（Task-三位数字）、status/priority 合法性、assignee 是否存在于 `config/agents.json` 且 `enabled=true`。失败 exit 1，作为所有任务操作的前置安全闸。
- [x] `scripts/dispatch_task.py` assignee 校验 — 在任何任务状态修改、派工文件写入、审计日志写入之前，校验 `--assignee` 参数对应的 Agent 是否存在于 `config/agents.json` 且 `enabled=true`。拒绝未启用或未注册的 assignee，任务保持 pending 状态不变。

### 前置安全闸第二块（已验收）

- [x] `scripts/list_tasks.py` — 只读查看任务台账。支持 `--status` `--assignee` `--json`，按 id 排序。不修改任何文件。
- [x] `scripts/show_audit.py` — 只读查看审计日志。支持 `--date` `--task-id` `--event-type` `--limit` `--json`。不修改任何文件。
- [x] `docs/OPERATOR_RUNBOOK.md` — 人工操作手册：环境自检、创建/查看/校验/派发/完成任务、查看审计、force 覆盖规则、禁止事项、进入真实 ACP 执行的条件。
- [x] 更新 `README.md` 与 `PROJECT_PLAN.md` 加入新脚本说明。

### 前置安全闸第三块（已验收，2026-06-17）

- [x] `scripts/dispatch_task.py` preflight — 完整派工前校验（validate_task → agent 校验 → policies 加载）
- [x] `config/policies.json` 新增约束字段（maxRuntimeMinutes / maxOutputKB / allowedPaths）
- [x] `scripts/audit_log.py` environment 字段支持 — 区分测试/正式环境
- [x] 4 处 code review 修复（main 顺序、中文编码、硬编码序号、sys.path 清理）

### 前置安全闸第四块（已验收，2026-06-18）

- [x] `scripts/show_history.py` — 历史任务查询与统计报表。支持按状态/assignee/日期/优先级过滤，支持 `--report` 报表模式与 `--json` 输出。仅标准库，只读不写。由 CodeWhale 实现，胖小 code review 通过。

### 前置安全闸第五块（已验收，2026-06-18）

- [x] `scripts/test_isolation.py` — Agent 环境隔离校验。检查 cwd 目录存在性、cwd 在项目根目录内、cwd 之间互不重叠、allowedPaths 越界风险、模拟路径边界检查（内部/跨 Agent/逃逸）。由 CodeWhale 实现，胖小验收。修复 `agents/resident/exec01` 缺失目录。

### 启用第二个 Agent（已验收，2026-06-18）

- [x] `agent-ext-01` 启用：`config/agents.json` enabled=true。由 CodeWhale 执行，`test_isolation.py` 验证两台 Agent 隔离全部通过。

### 扩展能力（已验收）

- [x] 引入任务分配策略（轮询 / 负载 / 专岗）— `scripts/suggest_assignee.py` 已验收（CodeWhale，2026-06-18）
- [x] 评估是否引入轻量级"消息总线"（非群聊，仅主控转发）— ✅ 已完成（2026-06-18）
- [x] 人工审批节点 — `scripts/review_command.py` 已验收（Codex，2026-06-18）
- [x] 性能基线 — `scripts/benchmark_pipeline.py` 已验收（Codex，2026-06-18）

**红线**：
- 未经审批不启用全局广播
- 不自动提升 Agent 权限
- 不自动安装新依赖

---

## 旧方案管理模块落地（MVP v1 收口项，2026-06-20 切回）

目标：优先补齐原始方案中的管理能力，但全部替换为当前项目真实可运行的 Python 脚本 / 文件台账 / OpenClaw 工具能力，不直接照搬未验证 slash 命令。

### 已完成 / 进行中

- [x] 管理员操作审计：`scripts/audit_log.py` + `scripts/show_audit.py`
- [x] 任务全生命周期管理：`create_task.py` / `dispatch_task.py` / `complete_task.py` / `update_task.py` / `list_tasks.py` / `show_history.py`
- [x] 主控点对点消息与受控多播：`send_message.py` / `receive_message.py` / `list_messages.py` / `broadcast.py` / `resend_unacked.py`
- [x] 配置快照 / 备份恢复：`scripts/snapshot_config.py`，支持 `save` / `list` / `show` / `restore --yes`，恢复前自动创建 pre-restore 备份并写入审计

### 下一步优先级

1. [x] 本地成本/Token 估算台账：`scripts/record_cost.py` + `scripts/show_cost.py`，替代旧方案不可确认的 `/usage` 命令第一版，先做手动/估算记录、汇总、预算阈值提示，不承诺精确美元级自动暂停。
2. [x] 旧方案命令映射器：`scripts/command_map.py`，把 `/task`、`/audit`、`/snapshot`、`/usage`、`/acp spawn` 等伪命令映射到当前真实脚本或标记为 forbidden/pending。
3. [ ] 多维度告警雏形：先做本地状态/日志告警，不做自动自愈，不做无限重启。

### 暂缓项

- 真实全局自由群聊：继续默认禁止，只允许主控受控多播。
- 自动自愈：继续禁用，避免无限重试/无限烧钱。
- 真实 ACP 常驻四 Agent：必须先确认 OpenClaw 当前真实 ACP/session 创建方式，再小步接入。

---

## 从 MVP 到系统级架构升级（MVP v2 / Control Plane Prototype 预研，暂缓继续开发）

### 核心判断

当前项目已经不是“写着玩的 Agent 框架”，而是一个**可运行的受控多智能体系统原型**。

但它目前仍处在：

```text
工程化 MVP 完成 → 系统化架构缺失
```

也就是说：

- 已经能跑；
- 已经有任务、审计、安全闸和消息机制；
- 但距离“真正自治的 AI Agent Cluster”还差一层系统级架构：**事件驱动 + 调度器 + 全局状态一致性**。

### 当前缺口

#### 1. 缺少真正的 Scheduler

当前仍偏向 script-driven execution 和人工指挥流水线。

后续需要补：

- 优先级调度算法；
- 资源分配策略；
- 并发控制模型；
- backpressure 机制；
- 自动选 agent、自动分配 task、自动重试、自动负载均衡。

#### 2. 缺少 Event Bus / Event Layer

当前链路主要是：

```text
command → script → result
```

真正系统应升级为：

```text
event → queue → handler → state update
```

后续需要抽象：

- event store；
- event replay；
- async dispatch；
- task update / message send / audit write / cost update 的统一事件模型。

#### 3. Agent 仍然非自治

当前 Agent 更像 worker：

- 不自主决策；
- 不自主规划；
- 不自选工具；
- 主要执行主控派发的任务。

后续若进入自治 Agent Cluster，需要逐步引入受控的规划、工具选择和自我汇报机制。

#### 4. 缺少统一 State Store

当前已有：

- `tasks.json`
- `logs/audit/*.jsonl`
- `logs/messages/*.jsonl`
- message bus state

但还没有统一的 control plane state / source of truth。

后续需要统一：

- task state；
- agent state；
- cost state；
- message state；
- scheduler state。

可先实现本地 stdlib 版本，再评估是否迁移到 SQLite / Redis / etcd 等状态后端。

#### 5. 缺少系统级容错模型

当前容错主要是：

- retry；
- manual fix；
- kill + reassign。

后续需要补：

- distributed retry policy；
- idempotency guarantee；
- recovery orchestration；
- dead letter queue；
- 失败恢复与审计回放机制。

### 下一阶段优先级

如果从 MVP 继续升级为真正 Agent 系统，优先做三件事：

1. **抽象 Event Layer**：把 task update、message send、audit write、cost update 全部变成 event-driven model。
2. **引入 Scheduler**：替代手动 dispatch，支持自动选 Agent、自动分配任务、自动重试策略和负载均衡。
3. **统一 State Store**：统一 task / agent / cost / message / scheduler 状态，形成唯一事实源。

### 架构图任务

已将现有系统重构为可论文、可工程实现的系统级架构说明与架构图，核心包含：

```text
Event Bus + Scheduler + Unified State Store + Agent Workers + Audit/Policy Plane
```

交付物：

- [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) — 系统级架构设计说明
- [`docs/architecture/system_architecture.html`](docs/architecture/system_architecture.html) — 可打开查看的系统架构图

这是项目从“MVP”跨到“系统级设计”的关键一步。

> 当前口径：上述内容保留为 MVP v2 / Control Plane Prototype 的预研路线。旧方案 MVP v1 的验收仍以 Phase 0-3 为准；在 MVP v1 收口前，不继续推进 Milestone D，不新增系统化功能。

---

## Milestone A：Event Layer 骨架（MVP v2 预研；骨架已完成，暂缓继续扩展）

目标：新增事件日志能力，为后续 Scheduler / State Store 做基础。先不改造现有业务脚本，只新增事件日志模块。当前定位为系统化升级预研产物，不替代 MVP v1 Phase 0-3 验收。

- [x] 新增 `scripts/event_log.py` — 标准库 only 本地事件日志模块
  - 按天 JSONL 存储：`logs/events/YYYY-MM-DD.jsonl`
  - 死信队列预留：`logs/dead_letter/YYYY-MM-DD.jsonl`
  - 事件结构：eventId / eventType / timestamp / source / correlationId / causationId / payload / policySnapshot / status
  - CLI 子命令：`append` / `list` / `replay --dry-run`
  - 跨进程并发安全：基于 `.state` + `.state.lock` 文件锁
- [ ] 后续暂缓：将现有业务脚本逐步接入事件日志
- [ ] 后续暂缓：引入 Scheduler 调度器骨架
- [ ] 后续暂缓：统一 State Store

---

## Milestone B：State Builder（MVP v2 预研；已完成，暂缓继续扩展）

目标：从现有文件重建统一系统状态，为 Scheduler Tick 提供统一事实源。当前定位为系统化升级预研产物，不替代 MVP v1 Phase 0-3 验收。

- [x] 新增 `scripts/build_state.py` — 标准库 only 统一状态构建模块
  - 读取 tasks/tasks.json、config/agents.json、config/policies.json
  - 读取 logs/messages/*.jsonl、logs/audit/*.jsonl、logs/events/*.jsonl
  - 输出 state/system_state.json（统一状态事实源）
  - 支持 snapshot：state/snapshots/YYYY-MM-DDTHH-mm-ssZ.json
  - CLI：默认 / `--json` / `--output PATH` / `--snapshot` / `--dry-run`
  - 不修改原始业务文件
- [x] 新增 `state/` 与 `state/snapshots/` 目录
- [x] 更新 README.md 与 PROJECT_PLAN.md
- [ ] 后续暂缓：稳定后迁移 SQLite / 接入事件流

---

## Milestone C：Scheduler Tick（MVP v2 预研；dry-run 已实现，暂缓继续扩展）

目标：引入可控调度循环，但不自动执行真实 Agent。第一版只做 dry-run 调度决策。当前定位为系统化升级预研产物，不替代旧方案派工/验收链路。

- [x] 新增 `scripts/scheduler_tick.py` — 标准库 only 调度器 dry-run
  - 读取 `state/system_state.json` 统一状态
  - 支持 `--dry-run` 必选（不传则 exit 1，拒绝真实派工）
  - 支持 `--json` 输出机器可解析 JSON
  - 支持 `--write-event --dry-run` 写入 `scheduler.tick.evaluated` 事件
  - 调度逻辑：maxConcurrency 检查 / Agent 可用性 / 负载均衡选择
  - 调度逻辑增强：maxRetries 检查 / backpressure 警告 / dead-letter 候选识别
  - 任务选择按 priority（high > medium > low）→ createdAt 排序
  - Agent 选择按 in_progress 负载最低 → id 排序
  - disabled Agent 绝不被选中
- [x] 验证：临时 state 文件测试 4 个场景全部 PASS
  - pending task + enabled agent → `suggest_dispatch`
  - inProgress >= maxConcurrency → `blocked`
  - no enabled agent → `blocked`
  - disabled agent 不被选中
- [x] 更新 README.md 与 PROJECT_PLAN.md
- [x] 支持 retry limit / backpressure / dead-letter 候选 dry-run 判断
- [ ] 后续暂缓：backpressure 事件通知与 recovery orchestration
- [ ] 后续暂缓：从 dry-run 过渡到真实派工（需审批流程）

---

## 长期愿景（暂不实施）

- 动态 Agent 注册与发现
- 全局群聊（仅在安全沙箱内评估）
- 自动自愈（需完整审计与回滚机制先行）
- 高危险命令白名单/审批工作流
- 与外部 ACP 生态的深度集成

---

## 决策原则

1. **默认拒绝**：新功能默认关闭，需人工启用。
2. **单步验证**：每增加一个 Agent 或一项能力，必须独立验证。
3. **日志优先**：任何自动化动作必须留下不可篡改的审计记录。
4. **最小权限**：Agent 只能访问其 `cwd` 与明确授权的路径。
