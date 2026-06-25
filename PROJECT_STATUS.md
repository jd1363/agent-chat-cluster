# 项目状态总表

更新时间：2026-06-25
当前主线：**MVP v1 Phase 0-5 全部完成，真实执行引擎已接入**

## 一页结论

Agent Chat MVP v1 已完结。Phase 0-4 全部验收通过，包含基础骨架、主控-单 Agent 闭环、多 Agent 扩展、真实 subagent 验证与消息总线收口、7 Agent 扩容与并发安全。Phase 5 真实执行引擎接入已完成。Milestone A/B/C 是系统化升级预研，不替代 MVP v1 验收。当前等待下一阶段需求。

## 主线状态

| 模块 | 定位 | 当前状态 | 验收文件 / 说明 |
|---|---|---:|---|
| Phase 0 | MVP v1：基础骨架 | ✅ 已验收 | `ACCEPTANCE_STAGE0.md` |
| Phase 1 | MVP v1：主控-单 Agent 闭环 | ✅ 已验收 | `ACCEPTANCE_STAGE1.md` |
| Phase 2 | MVP v1：可控扩展至多 Agent | ✅ 已验收 | `ACCEPTANCE_STAGE2.md` |
| Phase 3 | MVP v1：真实 subagent 验证与消息总线收口 | ✅ 已验收 | `ACCEPTANCE_STAGE3.md` |
| Phase 4 | MVP v1：7 Agent 扩容 + 并发安全 + Web Dashboard | ✅ 已验收 | `ACCEPTANCE_STAGE4.md` |
| Phase 5 | 真实执行引擎接入 | ✅ 已完成 | executor_bridge.py + agents.json executor 映射 + 端到端验证 |
| 旧方案管理模块 | 快照、成本台账、命令映射、告警等 | ✅ 已完成 | Block 3A-3F 全部完成 |

## 系统化升级线状态

| 模块 | 定位 | 当前状态 | 是否替代 MVP v1 验收 |
|---|---|---:|---:|
| Milestone A：Event Layer | MVP v2 / Control Plane Prototype 预研 | 🟡 骨架已实现 | 否 |
| Milestone B：State Builder | MVP v2 / Control Plane Prototype 预研 | 🟡 已实现并验收 | 否 |
| Milestone C：Scheduler Tick | MVP v2 / Control Plane Prototype 预研 | 🟡 dry-run 已实现 | 否 |
| Milestone D 及之后 | 系统化升级后续路线 | ⏸ 暂缓 | 否 |

## 当前边界

- MVP v1 已完结，不再新增 MVP v1 范围内功能；
- 不继续开发 Milestone D；
- 不开启自由群聊、自动自愈、自动外发、自动提权；
- 系统化升级线继续暂缓，待主人决定是否启动；
- Codex CLI 启动较慢（~3 分钟），建议超时 300s+；
- Ollama 本地 14B 模型指令遵循能力有限，链路正常但输出质量取决于模型。

## 推荐下一步

1. executor_bridge 进程组 kill 优化（防止子进程残留）；
2. 测试 CodeWhale / OpenCode / MiMo 链路；
3. dispatch_task.py 集成 --execute-real 参数直接调用 executor_bridge；
4. Web Dashboard 操作面板集成"执行"按钮；
5. 混合读写任务并发测试。
