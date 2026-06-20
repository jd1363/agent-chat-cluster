# 项目状态总表

更新时间：2026-06-20
当前主线：**MVP v1 收口中（旧方案 Phase 0-3）**

## 一页结论

Agent Chat 当前应先完成旧方案 MVP v1 收口。Phase 0-3 是已落地并已验收的 MVP v1 主线；Milestone A/B/C 是系统化升级 / Control Plane Prototype 预研，已经启动但暂不替代旧方案验收，也不应继续压过 MVP v1 收口。

## 主线状态

| 模块 | 定位 | 当前状态 | 验收文件 / 说明 |
|---|---|---:|---|
| Phase 0 | MVP v1：基础骨架 | ✅ 已验收 | `ACCEPTANCE_STAGE0.md` |
| Phase 1 | MVP v1：主控-单 Agent 闭环 | ✅ 已验收 | `ACCEPTANCE_STAGE1.md` |
| Phase 2 | MVP v1：可控扩展至多 Agent | ✅ 已验收 | `ACCEPTANCE_STAGE2.md` |
| Phase 3 | MVP v1：真实 subagent 验证与消息总线收口 | ✅ 已验收 | `ACCEPTANCE_STAGE3.md` |
| 旧方案管理模块 | MVP v1 补齐项：快照、成本台账、命令映射等 | 🟡 收口中 | 已完成配置快照、成本估算台账、旧命令映射器；告警雏形仍可后续补。 |

## 系统化升级线状态

| 模块 | 定位 | 当前状态 | 是否替代 MVP v1 验收 |
|---|---|---:|---:|
| Milestone A：Event Layer | MVP v2 / Control Plane Prototype 预研 | 🟡 骨架已实现 | 否 |
| Milestone B：State Builder | MVP v2 / Control Plane Prototype 预研 | 🟡 已实现并验收 | 否 |
| Milestone C：Scheduler Tick | MVP v2 / Control Plane Prototype 预研 | 🟡 dry-run 已实现 | 否 |
| Milestone D 及之后 | 系统化升级后续路线 | ⏸ 暂缓 | 否 |

## 当前边界

- 不继续开发 Milestone D；
- 不新增系统化 Event/Scheduler/State 功能；
- 不把 dry-run Scheduler 视为旧方案派工验收的替代；
- 不开启自由群聊、自动自愈、自动外发、自动提权；
- 当前优先级是文档与验收口径收口，而不是新增业务脚本。

## 推荐下一步

1. 由主会话 review 本次文档收口变更。
2. 确认 `ACCEPTANCE_STAGE2.md`、`ACCEPTANCE_STAGE3.md` 与 `PROJECT_PLAN.md` 口径一致。
3. 若验证通过，提交一次文档收口 commit。
4. 然后再决定是否补旧方案「多维度告警雏形」；系统化升级线继续暂缓。
