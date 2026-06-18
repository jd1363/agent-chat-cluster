# 阶段 2 前置安全闸 — 第三块验收报告

## 验收项

1. ✅ dispatch_task 派工提示从 config/policies.json 读取约束（不再是硬编码）
2. ✅ 增加完整 preflight（validate_task → agent 校验 → policies 加载）
3. ✅ 审计日志增加 environment 字段（支持 test/production 区分）

## 改动文件

| 文件 | 变更 |
|------|------|
| `config/policies.json` | 新增 `execution.maxRuntimeMinutes`、`maxOutputKB`、`allowedPaths` |
| `scripts/dispatch_task.py` | 新增 `load_policies()`、`preflight()`；`generate_dispatch_prompt()` 改为从 policies 读取约束；`main()` 增加三步 preflight |
| `scripts/audit_log.py` | `append_audit()` 增加 `environment` 参数；CLI 增加 `--environment`；默认从 `AGENT_CHAT_ENV` 环境变量读取 |

## 测试验证

```
$ python scripts/validate_task.py
[OK] 所有校验通过

$ python scripts/dispatch_task.py --id Task-001 --assignee agent-exec-01
[PREFLIGHT] 步骤 1/3: 校验任务台账与 Agent 注册表...
[PREFLIGHT OK] 台账与注册表校验通过
[PREFLIGHT] 步骤 2/3: 校验指派 Agent...
[PREFLIGHT OK] assignee 'agent-exec-01' 存在且已启用
[PREFLIGHT] 步骤 3/3: 加载执行策略...
[PREFLIGHT OK] 策略加载成功
[OK] Task-001 已派发至 agent-exec-01
```

生成的 `logs/runs/Task-001_dispatch.md` 中：
- 最大运行时间、输出大小、允许路径、最大并发、重试次数均来自 `policies.json`
- 禁止行为根据 `communication.autoOutbound` 和 `execution.dangerousCommands` 动态生成
- 审计要求包含日志保留天数（来自 `audit.logRetentionDays`）

## Code Review 结果

审查者：胖小（子 agent spawn 失败，改为人工审查）

| 严重度 | 问题 | 状态 |
|--------|------|------|
| 🔴 Critical | `main()` 中 `preflight()` 在定位任务之前运行，可能白跑 | ✅ 已修复：先定位任务 → 确认 pending → 再 preflight |
| 🟡 High | subprocess 输出中文乱码（Windows GBK） | ✅ 已修复：子进程注入 `PYTHONIOENCODING=utf-8` |
| 🟡 High | `prohibitions` 列表硬编码序号，策略变化时跳号 | ✅ 已修复：改用 `enumerate` 动态生成序号 |
| 🟢 Medium | `sys.path` 导入后未恢复，可能污染 | ✅ 已修复：导入后立即 `remove` + `del` |
| 🟢 Medium | `load_policies()` 未校验字段类型 | 暂留：不影响功能，后续增强 |

## 待办

- [x] Code review（胖小人工完成）
- [ ] 主人确认后，更新 `OPERATOR_RUNBOOK.md` 和 `docs/SECURITY_NOTES.md`
- [ ] 进入阶段 2 正式验收（若本块通过）
