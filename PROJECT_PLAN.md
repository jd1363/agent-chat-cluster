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

- [ ] 引入任务分配策略（轮询 / 负载 / 专岗）
- [ ] 评估是否引入轻量级"消息总线"（非群聊，仅主控转发）
- [ ] 人工审批节点：高危险命令需主控确认
- [ ] 性能基线：在最大并发 1 的条件下评估瓶颈

**红线**：
- 未经审批不启用全局广播
- 不自动提升 Agent 权限
- 不自动安装新依赖

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
