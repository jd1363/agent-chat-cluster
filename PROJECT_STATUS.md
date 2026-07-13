# 项目状态总表

更新时间：2026-07-13
当前主线：**MVP v1 Phase 0-5 全部完成，真实执行流程已打通；#6 真实项目任务端到端验证通过**

## 一页结论

Agent Chat MVP v1 已完结。Phase 0-4 全部验收通过，Phase 5 真实执行引擎接入完成。
- 2026-06-30：完成 executor_bridge 进程组 kill 优化 + dispatch_task 一步执行（`--execute-real` 自动生成 prompt + 执行 CLI）+ Dashboard 执行按钮状态反馈。端到端测试通过（OpenCode 11.9s）。
- 2026-07-13：完成 #8 多任务队列调度器 `scripts/queue_dispatch.py`（支持 --dry-run / --execute-real / --max / --assignee），修复 `config/agents.json` notes 乱码。
- 2026-07-13：完成 #6 真实项目任务端到端验证——新建真实开发任务 Task-084（slugify 工具函数），派 OpenCode(agent-ext-02) 真实执行 56.7s，产出 `scripts/text_utils.py`（6 个自测全 PASS，py_compile 通过），验证 `--write-output` 能正确解析 Agent 输出的 file 代码块并落盘。

## 主线状态

| 模块 | 定位 | 当前状态 | 验收文件 / 说明 |
|---|---|---:|---|
| Phase 0 | MVP v1：基础骨架 | ✅ 已验收 | `ACCEPTANCE_STAGE0.md` |
| Phase 1 | MVP v1：主控 + 单 Agent 闭环 | ✅ 已验收 | `ACCEPTANCE_STAGE1.md` |
| Phase 2 | MVP v1：可控扩展至多 Agent | ✅ 已验收 | `ACCEPTANCE_STAGE2.md` |
| Phase 3 | MVP v1：真实 subagent 验证与消息总线收口 | ✅ 已验收 | `ACCEPTANCE_STAGE3.md` |
| Phase 4 | MVP v1：7 Agent 扩容 + 并发安全 + Web Dashboard | ✅ 已验收 | `ACCEPTANCE_STAGE4.md` |
| Phase 5 | 真实执行引擎接入 | ✅ 已完成 | executor_bridge.py + agents.json executor 映射 + 端到端验证 |
| 旧方案治理模块 | 快照、成本台账、命令映射、告警等 | ✅ 已完成 | Block 3A-3F 全部完成 |

## 系统化升级线状态

| 模块 | 定位 | 当前状态 | 是否替代 MVP v1 验收 |
|---|---|---:|---:|
| Milestone A：Event Layer | MVP v2 / Control Plane Prototype 预研 | 🟨 骨架已实现 | 否 |
| Milestone B：State Builder | MVP v2 / Control Plane Prototype 预研 | 🟨 已实现并验收 | 否 |
| Milestone C：Scheduler Tick | MVP v2 / Control Plane Prototype 预研 | 🟨 dry-run 已实现 | 否 |
| Milestone D 及之后 | 系统化升级后续路线 | ⏸ 暂缓 | 否 |

## 当前边界

- MVP v1 已完结，不再新增 MVP v1 范围内功能；
- 不继续开发 Milestone D；
- 不开启自由群聊、自动自愈、自动外发、自动提权；
- 系统化升级线继续暂缓，待主人决定是否启动；
- Codex CLI 启动较慢（约 3 分钟），建议超时 300s+；
- Ollama 本地 14B 模型指令遵循能力有限，链路正常但输出质量取决于模型。

## 推荐下一步

1. ~~executor_bridge 进程组 kill 优化~~ ✅ 已完成（2026-06-30）
2. ~~测试 CodeWhale / OpenCode / MiMo 链路~~ ✅ 已完成
3. ~~dispatch_task.py 集成 --execute-real~~ ✅ 已完成（一步到位）
4. ~~Web Dashboard 操作面板集成"执行"按钮~~ ✅ 已完成
5. ~~混合读写任务并发测试~~ ✅ 已完成
6. ~~真实项目任务端到端~~ ✅ 已完成（2026-07-13，Task-084 / OpenCode）
7. ~~**Dashboard 浏览器实测**~~ ✅ 已完成（2026-07-13，Playwright chromium 真实点击执行按钮，SSE 反馈闭环验证通过；顺带修复 blocked 终态未纳入 SSE 终止集 + SSE/API 数据源不一致两个 bug）
8. ~~多任务队列调度~~ ✅ 已完成（2026-07-13，queue_dispatch.py）

## 真正剩余待办

- ~~**#7 Dashboard 浏览器实测**~~ ✅ 已完成（2026-07-13）：Playwright headless chromium 真实点击「执行」按钮，SSE log/status 闭环走通，`ok=true`。修复：(1) server.py `terminal_statuses` 补 `blocked`，(2) dashboard.html 前端 blocked 状态关闭 SSE，(3) `find_task_by_id` 改读 SQLite 与 API 对齐数据源。
- 系统化升级线（Milestone D+）：暂缓，等主人拍板。
