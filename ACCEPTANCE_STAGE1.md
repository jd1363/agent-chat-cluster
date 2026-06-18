# 阶段 1 验收报告

验收时间：2026-06-14
验收人：胖小（项目管理员 / 架构决策 / 验收负责人）
执行工程师：OpenCode
管理员紧急补丁：胖小（因 OpenCode 连续两次 SIGKILL，用户授权后仅修复状态机 hotfix）

## 结论

**阶段 1：通过。**

阶段 1 已完成“主控-单执行 Agent 闭环”的协议与审计层：

- 可创建任务
- 可派发 pending 任务
- 可生成派工提示
- 可写审计日志
- 可结束 in_progress 任务
- 可通过 `--force` 做管理员人工覆盖，并写入审计

本阶段仍然没有启动任何 ACP agent，没有安装依赖，没有执行危险命令。

## 新增/修改文件

```text
docs/TASK_PROTOCOL.md
scripts/audit_log.py
scripts/dispatch_task.py
scripts/complete_task.py
scripts/create_task.py
scripts/update_task.py
README.md
PROJECT_PLAN.md
ACCEPTANCE_STAGE1.md
```

## 阶段 1 核心流程

```text
create_task.py
  ↓
tasks/tasks.json 新增 pending 任务
  ↓
dispatch_task.py
  ↓
任务状态改为 in_progress
生成 logs/runs/Task-XXX_dispatch.md
写 logs/audit/YYYY-MM-DD.jsonl: task_dispatched
  ↓
complete_task.py
  ↓
任务状态改为 done / failed / blocked
写 logs/audit/YYYY-MM-DD.jsonl: task_completed / task_failed / task_blocked
```

## 已验证测试

### 1. 语法检查

已执行：

```text
python -m py_compile scripts\complete_task.py scripts\create_task.py scripts\dispatch_task.py scripts\audit_log.py scripts\update_task.py scripts\check_env.py
```

结果：通过。

### 2. 状态机防绕过测试

创建 pending 任务后，直接执行：

```text
python scripts\complete_task.py --id Task-001 --status done --summary "should fail"
```

结果：失败，符合预期。

关键输出：

```text
[FAIL] 任务 Task-001 当前状态不是 in_progress（当前: pending），如需管理员覆盖请加 --force
```

### 3. 正常闭环测试

执行：

```text
python scripts\dispatch_task.py --id Task-001 --assignee agent-exec-01
python scripts\complete_task.py --id Task-001 --status done --summary "hotfix normal flow passed"
```

结果：通过。

审计日志包含：

```json
{
  "eventType": "task_completed",
  "taskId": "Task-001",
  "data": {
    "previousStatus": "in_progress",
    "newStatus": "done",
    "summary": "hotfix normal flow passed",
    "output": null,
    "force": false
  }
}
```

### 4. 管理员 force 覆盖测试

创建 pending 任务后执行：

```text
python scripts\complete_task.py --id Task-002 --status blocked --summary "force override test" --force
```

结果：通过，且输出 WARN。

审计日志包含：

```json
{
  "eventType": "task_blocked",
  "taskId": "Task-002",
  "data": {
    "previousStatus": "pending",
    "newStatus": "blocked",
    "summary": "force override test",
    "output": null,
    "force": true
  }
}
```

### 5. 最终任务台账

最终已清空测试任务：

```json
{
  "schemaVersion": "1.0",
  "nextId": 1,
  "tasks": []
}
```

## Hotfix 说明

OpenCode 在修复 `complete_task.py` 状态机漏洞时连续两次被系统 SIGKILL：

- `mellow-lobster`：读文件后被杀
- `briny-otter`：刚启动就被杀

用户授权后，验收人执行管理员紧急补丁，仅修改：

- `scripts/complete_task.py`
- `docs/TASK_PROTOCOL.md`
- `README.md`

未扩大范围。

## 当前红线

阶段 2 前仍保持：

- 不自动启动 ACP agent
- 不开启全局广播
- 不自动外发消息
- 不自动自愈
- 不执行危险命令
- 不安装新依赖
- 不扩容 ext01~ext06

## 下一阶段建议

进入阶段 2 前，建议先做“真实执行前安全闸”：

1. `scripts/validate_task.py`：校验任务字段、状态、路径、assignee 是否合法
2. `scripts/list_tasks.py`：只读查看任务台账
3. `scripts/show_audit.py`：查看审计日志摘要
4. `docs/OPERATOR_RUNBOOK.md`：人工操作手册
5. 给 `dispatch_task.py` 加 assignee 必须存在于 `config/agents.json` 且 enabled=true 的检查

这些完成后，再考虑让 OpenCode/ACP Agent 真实执行第一个受控任务。
