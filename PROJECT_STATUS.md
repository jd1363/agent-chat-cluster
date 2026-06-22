# 项目状态总表

更新时间：2026-06-22
当前主线：**MVP v1 Phase 0-4 全部完成并验收通过**

## 一页结论

Agent Chat MVP v1 已完结。Phase 0-4 全部验收通过，包含基础骨架、主控-单 Agent 闭环、多 Agent 扩展、真实 subagent 验证与消息总线收口、7 Agent 扩容与并发安全。Milestone A/B/C 是系统化升级预研，不替代 MVP v1 验收。当前等待下一阶段需求。

## 主线状态

| 模块 | 定位 | 当前状态 | 验收文件 / 说明 |
|---|---|---:|---|
| Phase 0 | MVP v1：基础骨架 | ✅ 已验收 | `ACCEPTANCE_STAGE0.md` |
| Phase 1 | MVP v1：主控-单 Agent 闭环 | ✅ 已验收 | `ACCEPTANCE_STAGE1.md` |
| Phase 2 | MVP v1：可控扩展至多 Agent | ✅ 已验收 | `ACCEPTANCE_STAGE2.md` |
| Phase 3 | MVP v1：真实 subagent 验证与消息总线收口 | ✅ 已验收 | `ACCEPTANCE_STAGE3.md` |
| Phase 4 | MVP v1：7 Agent 扩容 + 并发安全 + Web Dashboard | ✅ 已验收 | `ACCEPTANCE_STAGE4.md` |
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
- 系统化升级线继续暂缓，待主人决定是否启动。

## 推荐下一步

1. MVP v1 阶段性完结，可用于课堂演示、项目汇报、比赛材料；
2. 若需要继续，可选方向：
   - openclaw_executor 优化（prompt 生成更精确）
   - Milestone D（Event Layer 接入业务脚本）
   - Scheduler 从 dry-run 过渡到真实派工
   - 混合读写任务并发测试
