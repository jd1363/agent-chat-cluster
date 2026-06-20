# 项目路线图

## 核心理念

**先主控 + 1 个 Agent，禁止一上来全局群聊。**

所有功能从最小可控单元验证，逐步扩展。未经验证的能力默认关闭。

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

## 阶段 1：主控-单 Agent 闭环验证（当前）

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

## 阶段 2：可控扩展至多 Agent

目标：在阶段 1 验证通过的前提下，谨慎扩展至多 Agent 场景。

### 前置安全闸（已实现）

- [x] `scripts/validate_task.py` — 校验台账完整性、ID 格式（Task-三位数字）、status/priority 合法性、assignee 是否存在于 `config/agents.json` 且 `enabled=true`。失败 exit 1，作为所有任务操作的前置安全闸。
- [x] `scripts/dispatch_task.py` assignee 校验 — 在任何任务状态修改、派工文件写入、审计日志写入之前，校验 `--assignee` 参数对应的 Agent 是否存在于 `config/agents.json` 且 `enabled=true`。拒绝未启用或未注册的 assignee，任务保持 pending 状态不变。

### 前置安全闸第二块（已实现，待验收）

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

### 待实现

- [x] 引入任务分配策略（轮询 / 负载 / 专岗）— `scripts/suggest_assignee.py` 已验收（CodeWhale，2026-06-18）
- [x] 评估是否引入轻量级"消息总线"（非群聊，仅主控转发）— ✅ 已完成（2026-06-18）
- [x] 人工审批节点 — `scripts/review_command.py` 已验收（Codex，2026-06-18）
- [x] 性能基线 — `scripts/benchmark_pipeline.py` 已验收（Codex，2026-06-18）

**红线**：
- 未经审批不启用全局广播
- 不自动提升 Agent 权限
- 不自动安装新依赖

---

## 从 MVP 到系统级架构升级（下一关键路线，2026-06-20 新增）

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

---

---

## Milestone A：Event Layer 骨架（进行中，2026-06-20）

目标：新增事件日志能力，为后续 Scheduler / State Store 做基础。先不改造现有业务脚本，只新增事件日志模块。

- [x] 新增 `scripts/event_log.py` — 标准库 only 本地事件日志模块
  - 按天 JSONL 存储：`logs/events/YYYY-MM-DD.jsonl`
  - 死信队列预留：`logs/dead_letter/YYYY-MM-DD.jsonl`
  - 事件结构：eventId / eventType / timestamp / source / correlationId / causationId / payload / policySnapshot / status
  - CLI 子命令：`append` / `list` / `replay --dry-run`
  - 跨进程并发安全：基于 `.state` + `.state.lock` 文件锁
- [ ] 后续：将现有业务脚本逐步接入事件日志
- [ ] 后续：引入 Scheduler 调度器骨架
- [ ] 后续：统一 State Store

---

## Milestone B：State Builder（已完成，2026-06-20）

目标：从现有文件重建统一系统状态，为 Scheduler Tick 提供统一事实源。

- [x] 新增 `scripts/build_state.py` — 标准库 only 统一状态构建模块
  - 读取 tasks/tasks.json、config/agents.json、config/policies.json
  - 读取 logs/messages/*.jsonl、logs/audit/*.jsonl、logs/events/*.jsonl
  - 输出 state/system_state.json（统一状态事实源）
  - 支持 snapshot：state/snapshots/YYYY-MM-DDTHH-mm-ssZ.json
  - CLI：默认 / `--json` / `--output PATH` / `--snapshot` / `--dry-run`
  - 不修改原始业务文件
- [x] 新增 `state/` 与 `state/snapshots/` 目录
- [x] 更新 README.md 与 PROJECT_PLAN.md
- [ ] 后续：稳定后迁移 SQLite / 接入事件流

---

## Milestone C：Scheduler Tick（进行中：第一版 dry-run 已实现，2026-06-20）

目标：引入可控调度循环，但不自动执行真实 Agent。第一版只做 dry-run 调度决策。

- [x] 新增 `scripts/scheduler_tick.py` — 标准库 only 调度器 dry-run
  - 读取 `state/system_state.json` 统一状态
  - 支持 `--dry-run` 必选（不传则 exit 1，拒绝真实派工）
  - 支持 `--json` 输出机器可解析 JSON
  - 支持 `--write-event --dry-run` 写入 `scheduler.tick.evaluated` 事件
  - 调度逻辑：maxConcurrency 检查 / Agent 可用性 / 负载均衡选择
  - 任务选择按 priority（high > medium > low）→ createdAt 排序
  - Agent 选择按负载最低 → id 排序
  - disabled Agent 绝不被选中
- [x] 验证：临时 state 文件测试 4 个场景全部 PASS
  - pending task + enabled agent → `suggest_dispatch`
  - inProgress >= maxConcurrency → `blocked`
  - no enabled agent → `blocked`
  - disabled agent 不被选中
- [x] 更新 README.md 与 PROJECT_PLAN.md
- [ ] 后续：支持 retry limit / backpressure 事件通知
- [ ] 后续：从 dry-run 过渡到真实派工（需审批流程）

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
