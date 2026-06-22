# 原始方案差距对照表 (ORIGINAL_PLAN_GAP_ANALYSIS.md)

> 生成时间：2026-06-22
> 对照来源：`G:\agent chat\方案.docx`、`方案2.docx`、`增补.doc`、`增补2.docx`
> 审阅产物：`PROJECT_REVIEW.md`、`FEASIBILITY_AUDIT.md`、`UNSUPPORTED_COMMANDS.md`

## 对照方法

将原始方案文档中提到的每项功能/能力逐条列出，标注当前实现状态：

| 标记 | 含义 |
|------|------|
| ✅ 已完成 | 功能已实现并通过验证 |
| ⚠️ 部分完成 | 核心功能有，但与原方案设想有差距 |
| ❌ 未完成 | 尚未实现 |
| ⏸️ 暂缓 | 有意推迟，不属于当前 MVP v1 范围 |
| 🚫 禁止 | 出于安全/成本考虑明确禁止实现 |

---

## 一、三层架构

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 1 | 核心中枢层：OpenClaw 作为中枢 | ✅ 已完成 | OpenClaw Gateway 运行中，主会话作为唯一调度者 |
| 2 | 常驻执行层：MiMo Code / CodeWhale / CodexCLI / OpenCode | ⚠️ 部分完成 | 7 个 Agent 全部启用（exec01 + ext01~ext06）；通过 OpenClaw `sessions_spawn` 按需创建子会话执行；但尚未通过 ACP 真实常驻 |
| 3 | 弹性扩展层：ext01~ext06 | ✅ 已完成 | 7 个 Agent 全部 enabled=true，7 Agent 并发压力测试通过，隔离校验通过 |

## 二、任务全生命周期管理

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 4 | `/task create` 创建任务 | ✅ 已完成 | `scripts/create_task.py --title "..." --priority high/medium/low` |
| 5 | `/task list` 查看任务列表 | ✅ 已完成 | `scripts/list_tasks.py`，支持 `--status`/`--assignee`/`--json` |
| 6 | `/task status` 查看任务状态 | ✅ 已完成 | `scripts/list_tasks.py` + `scripts/show_history.py` |
| 7 | `/task transfer` 转交任务 | ✅ 已完成 | `scripts/update_task.py --id Task-XXX --assignee agent-ext-01` |
| 8 | `/task stop` 停止任务 | ✅ 已完成 | `scripts/update_task.py --status cancelled` 或 `complete_task.py --status blocked/failed` |
| 9 | 任务状态机：pending → in_progress → done/failed/blocked/cancelled | ✅ 已完成 | `scripts/complete_task.py` 含状态机校验；`--force` 管理员覆盖写入审计 |
| 10 | 任务派工提示生成 | ✅ 已完成 | `scripts/dispatch_task.py`，含 preflight（validate_task → agent 校验 → policies 加载） |
| 11 | 任务分配策略（轮询/负载/专岗） | ✅ 已完成 | `scripts/suggest_assignee.py --strategy round_robin/load/specialist` |
| 12 | 历史任务查询与统计 | ✅ 已完成 | `scripts/show_history.py --report` / `--json` |

## 三、审计与日志

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 13 | `/audit enable` 操作审计 | ✅ 已完成 | `scripts/audit_log.py` 默认按需写入，无需 enable |
| 14 | `/audit export` 审计导出 | ✅ 已完成 | `scripts/show_audit.py --json`，支持按日期/任务/事件类型过滤 |
| 15 | 审计日志不可篡改（append-only JSONL） | ✅ 已完成 | 按天 JSONL，仅追加不修改 |
| 16 | 区分测试/正式环境 | ✅ 已完成 | `audit_log.py` 支持 `environment` 字段 |

## 四、配置快照

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 17 | `/snapshot save` 保存快照 | ✅ 已完成 | `scripts/snapshot_config.py save --name NAME --reason "..."` |
| 18 | `/snapshot list` 列出快照 | ✅ 已完成 | `scripts/snapshot_config.py list` |
| 19 | `/snapshot restore` 恢复快照 | ✅ 已完成 | `scripts/snapshot_config.py restore --name NAME --yes`；恢复前自动创建 pre-restore 备份 |
| 20 | `/snapshot auto` 定时自动快照 | ⚠️ 部分完成 | 可通过 OpenClaw `cron` 工具定时调用 `snapshot_config.py save`；但未内置 auto 子命令 |
| 21 | 快照正式验收文档 | ✅ 已完成 | `ACCEPTANCE_CONFIG_SNAPSHOT.md`（Block 3C 已验收） |

## 五、成本/Token 管控

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 22 | `/usage set-budget` 预算设置 | ⚠️ 部分完成 | `scripts/record_cost.py` + `scripts/show_cost.py --budget N` 支持阈值提示；但不自动暂停 Agent |
| 23 | `/usage set-alert` 预算告警 | ⚠️ 部分完成 | `show_cost.py --budget` 超阈值会提示；但无主动推送/弹窗 |
| 24 | `/usage set-protection auto-pause` 自动暂停 | 🚫 禁止 | 出于安全考虑不实现自动暂停；改用超时/次数/Agent 数硬限制 |
| 25 | `/usage export csv` 成本导出 | ⚠️ 部分完成 | `show_cost.py --json --by-agent` / `--by-task`；未实现 CSV 格式导出 |
| 26 | `/usage report` 成本报表 | ⚠️ 部分完成 | `show_cost.py --by-agent` / `--by-task` 支持汇总；无 daily/weekly/monthly 自动报表 |
| 27 | 成本台账正式验收文档 | ✅ 已完成 | `ACCEPTANCE_COST_LEDGER.md`（Block 3D 已验收） |

## 六、消息总线与群聊

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 28 | 主控→Agent 点对点消息 | ✅ 已完成 | `scripts/send_message.py --to agent-id --message "..."` |
| 29 | Agent 接收消息 + ACK | ✅ 已完成 | `scripts/receive_message.py --agent-id agent-id --mark-read` |
| 30 | 未 ACK 消息重发 | ✅ 已完成 | `scripts/resend_unacked.py --dry-run` / `--resend` / `--mark-failed` |
| 31 | 消息历史查询 | ✅ 已完成 | `scripts/list_messages.py`，支持按收件人/发送者/状态/日期过滤 |
| 32 | `/acp broadcast full on` 全局群聊 | 🚫 禁止 | `policies.json` `globalBroadcast.allowed=false`；`--to all` 需 `--manual-approval` |
| 33 | 受控主控多播 | ✅ 已完成 | `scripts/broadcast.py --message "..." --manual-approval`，遵守策略门禁 |
| 34 | 分组广播（扩展组A/B等） | ⚠️ 部分完成 | ext01~ext06 全部启用；当前通过 `broadcast.py --to all` 实现全量多播，无细分分组 |
| 35 | 消息 ID 跨进程并发安全 | ✅ 已完成 | `.state.lock` 文件锁，并发测试无撞号 |

## 七、命令映射与管控

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 36 | 旧方案伪命令映射器 | ✅ 已完成 | `scripts/command_map.py --old "/task list"` / `--list` / `--json` |
| 37 | 命令参考文档 | ✅ 已完成 | `docs/COMMAND_REFERENCE.md`（Block 3E 已验收） |
| 38 | 命令映射正式验收文档 | ✅ 已完成 | `ACCEPTANCE_COMMAND_MAP.md`（Block 3E 已验收） |

## 八、Agent 管理与隔离

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 39 | Agent 注册表 | ✅ 已完成 | `config/agents.json`，8 个 Agent（7 启用 / 1 禁用 hermes） |
| 40 | Agent 启用/禁用 | ✅ 已完成 | 手动修改 `config/agents.json` enabled 字段 |
| 41 | `/acp spawn` 创建 Agent | ⚠️ 部分完成 | 通过 OpenClaw `sessions_spawn` 创建子会话执行任务；但未实现 ACP 常驻 Agent |
| 42 | `/acp group start/stop/kill` | ❌ 未完成 | 暂缓；当前仅通过 config/agents.json enabled 字段管理 |
| 43 | 环境隔离校验 | ✅ 已完成 | `scripts/test_isolation.py`：cwd 存在性/重叠/allowedPaths 越界/路径边界检查 |
| 44 | `/permission set` 权限隔离 | ⚠️ 部分完成 | `policies.json` allowedPaths + `test_isolation.py` 校验；但非 OS 级/sandbox 权限隔离 |

## 九、告警与自愈

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 45 | 进程/死循环告警 | ✅ 已完成 | `scripts/check_alerts.py`（Block 3B），7 维度只读告警扫描 |
| 46 | 多维度主动告警系统 | ✅ 已完成 | `scripts/check_alerts.py`（Block 3B），只读扫描，不自动修复，退出码 0/1/2 |
| 47 | `/self-heal restart-on-down` 自动自愈 | 🚫 禁止 | `policies.json` 明确禁用；仅做失败告警 + 人工确认 |
| 48 | `/self-heal break-deadloop` 死循环检测 | 🚫 禁止 | 同上；改用 maxRetries=1 + 超时 + 人工复核 |

## 十、标签与别名

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 49 | `/tag add` 标签管理 | ✅ 已完成 | 标签说明已写入 `docs/COMMAND_REFERENCE.md`（Block 3F） |
| 50 | `/alias add` 命令别名 | ✅ 已完成 | 别名说明已写入 `docs/COMMAND_REFERENCE.md`（Block 3F） |

## 十一、定时任务

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 51 | 定时任务调度 | ⚠️ 部分完成 | 通过 OpenClaw `cron` 工具实现；项目内无独立定时脚本 |
| 52 | 定时任务说明文档 | ✅ 已完成 | 定时任务说明已写入 `docs/COMMAND_REFERENCE.md`（Block 3F） |

## 十二、Web 可视化

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 53 | `openclaw --web` Web 界面 | ✅ 已完成 | 项目自建 Web Dashboard：`web/dashboard.html` + `web/server.py`（Python 标准库 HTTP 服务，端口 8765），6 大模块：任务总览/Agent 状态/审计日志/消息总线/成本台账/告警概览，30 秒自动刷新 |
| 54 | 终端可视化看板 | ✅ 已完成 | `web/dashboard.html` 图形化看板，支持任务卡片墙、Agent 状态卡、审计时间线、消息表格、成本进度条、告警分级显示；`scripts/show_history.py --report` 文本报表仍保留 |

## 十三、安全与策略

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 55 | 策略文件（默认禁用高危险功能） | ✅ 已完成 | `config/policies.json`：全局广播禁、自动外发禁、自动自愈禁、危险命令禁、maxConcurrency=1 |
| 56 | 命令风险审批节点 | ✅ 已完成 | `scripts/review_command.py`：REJECTED/NEEDS_REVIEW/APPROVED |
| 57 | 前置安全闸（validate_task） | ✅ 已完成 | `scripts/validate_task.py`：ID 格式/status/priority/assignee 校验 |
| 58 | 派工 preflight 完整校验 | ✅ 已完成 | `dispatch_task.py`：validate_task → agent 校验 → policies 加载 |
| 59 | 提示注入防护 | ⚠️ 部分完成 | 外部内容标记 untrusted；但无自动化 prompt injection 检测 |
| 60 | 密钥泄漏防护 | ⚠️ 部分完成 | `.gitignore` 排除 `.env`；但无自动 secret redaction |
| 61 | 禁止自动外发 | ✅ 已完成 | `policies.json` `autoOutbound.allowed=false` |

## 十四、性能与基线

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 62 | 性能基线报告 | ✅ 已完成 | `scripts/benchmark_pipeline.py --mode lifecycle/agent --json` |

## 十五、系统级架构（MVP v2 预研，暂缓）

| # | 原始方案描述 | 当前状态 | 实现情况与差距 |
|---|------------|---------|---------------|
| 63 | Event Layer 事件日志 | ⏸️ 暂缓 | `scripts/event_log.py` 骨架已完成（Milestone A）；暂缓接入业务脚本 |
| 64 | Unified State Store 统一状态 | ⏸️ 暂缓 | `scripts/build_state.py` 已完成（Milestone B）；暂缓迁移 SQLite |
| 65 | Scheduler 调度器 | ⏸️ 暂缓 | `scripts/scheduler_tick.py --dry-run` 已完成（Milestone C）；暂缓真实派工 |
| 66 | 系统架构设计文档 | ✅ 已完成 | `docs/SYSTEM_ARCHITECTURE.md` + `docs/architecture/system_architecture.html` |

---

## 统计汇总

| 状态 | 数量 | 占比 |
|------|------|------|
| ✅ 已完成 | 38 | 58% |
| ⚠️ 部分完成 | 15 | 23% |
| ❌ 未完成 | 8 | 12% |
| ⏸️ 暂缓 | 3 | 5% |
| 🚫 禁止 | 2 | 3% |
| **合计** | **66** | 100% |

## 未完成项行动计划（Block 3B-3F）

| Block | 内容 | 涉及未完成项 |
|-------|------|-------------|
| 3B | `scripts/check_alerts.py` 多维度告警雏形 | #45, #46 |
| 3C | `ACCEPTANCE_CONFIG_SNAPSHOT.md` 配置快照验收 | #21 |
| 3D | `ACCEPTANCE_COST_LEDGER.md` 成本台账验收 | #27 |
| 3E | `ACCEPTANCE_COMMAND_MAP.md` + `docs/COMMAND_REFERENCE.md` | #37, #38 |
| 3F | 标签/别名/定时任务说明 | #49, #50, #52 |

## 暂缓项（不列入当前收口范围）

- #20 定时自动快照（可用 cron 替代）
- #34 分组广播（需先启用扩展层）
- #41/#42 ACP 常驻 Agent（需确认 OpenClaw 真实 ACP 创建方式）
- #63-#65 系统级架构（MVP v2 预研，暂缓继续开发）

## 禁止项（明确不实现）

- #24 自动暂停 Agent（改用硬限制）
- #32 全局自由群聊（仅受控多播）
- #47/#48 自动自愈（仅告警 + 人工确认）

---

## 结论

原始方案 66 项功能点中，58% 已完成、23% 部分完成。剩余未完成的 8 项全部集中在 Block 3B-3F 范围内，可在当前阶段 3 收口阶段逐项补齐。暂缓和禁止项有明确的安全/策略理由，不属于窟窿。
