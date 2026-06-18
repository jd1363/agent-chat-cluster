# 阶段 2 前置安全闸验收报告

验收时间：2026-06-14
验收人：胖小（项目管理员 / 架构决策 / 验收负责人）
执行工程师：CodeWhale

## 结论

**阶段 2 前置安全闸第一块：通过。**

已完成：

- 新增 `scripts/validate_task.py`
- 修改 `scripts/dispatch_task.py`，派发前校验 assignee 必须存在且 enabled=true
- 更新 `README.md`
- 更新 `PROJECT_PLAN.md`
- 最终保持 `tasks/tasks.json` 为空台账

本阶段仍未启动任何 ACP agent，未安装依赖，未执行危险命令。

## 重要工具经验

CodeWhale 必须使用工具执行模式：

```text
codewhale exec --auto "任务"
```

不要使用普通：

```text
codewhale exec "任务"
```

普通 `exec` 是 one-shot model response，容易只输出方案、不真实写文件。

## 修改文件

```text
scripts/validate_task.py
scripts/dispatch_task.py
README.md
PROJECT_PLAN.md
ACCEPTANCE_STAGE2_PRECHECK.md
```

## validate_task.py 校验规则

`validate_task.py` 校验：

- `tasks/tasks.json` 存在且 JSON 可解析
- `config/agents.json` 存在且 JSON 可解析
- `schemaVersion` 存在
- `tasks` 是 list
- 每个任务必须有：`id` / `title` / `status` / `priority`
- `status` 只能是：`pending` / `in_progress` / `done` / `failed` / `blocked` / `cancelled`
- `priority` 只能是：`low` / `medium` / `high`
- `id` 必须符合 `Task-三位数字`，如 `Task-001`
- 若 `assignee` 非空，必须存在于 `config/agents.json` 且 `enabled=true`
- 成功 exit 0，失败 exit 1

## dispatch_task.py 新安全闸

派发前会先读取：

```text
config/agents.json
```

并校验：

```text
--assignee 必须存在，且 enabled=true
```

非法时：

- exit 1
- 不修改任务状态
- 不生成派工文件
- 不写 `task_dispatched` 审计日志

## 验收测试

### 1. 语法检查

已执行：

```text
python -m py_compile scripts\validate_task.py scripts\dispatch_task.py
```

结果：通过。

### 2. 空台账校验

已执行：

```text
python scripts\validate_task.py
```

结果：通过。

### 3. 合法 assignee 派发

已执行：

```text
python scripts\create_task.py --title "manager validation legal dispatch" --priority high
python scripts\dispatch_task.py --id Task-001 --assignee agent-exec-01
```

结果：通过，任务进入 `in_progress`。

### 4. 非法 assignee 派发

已执行：

```text
python scripts\create_task.py --title "manager validation bad assignee" --priority medium
python scripts\dispatch_task.py --id Task-001 --assignee bad-agent
```

结果：失败，符合预期。

确认任务仍保持：

```text
status = pending
assignee = null
```

### 5. disabled assignee 派发

已执行：

```text
python scripts\dispatch_task.py --id Task-001 --assignee agent-ext-01
```

结果：失败，符合预期，因为 `agent-ext-01` 在注册表中但 `enabled=false`。

### 6. 最终任务台账

最终已重置为空：

```json
{
  "schemaVersion": "1.0",
  "nextId": 1,
  "tasks": []
}
```

## 当前项目状态

- 阶段 0：通过
- 阶段 1：通过
- 阶段 2 前置安全闸第一块：通过

## 下一步建议

继续阶段 2 前置安全闸第二块：

1. `scripts/list_tasks.py`：只读查看任务台账，支持按 status/assignee 过滤
2. `scripts/show_audit.py`：查看审计日志摘要，支持按 taskId/eventType 过滤
3. `docs/OPERATOR_RUNBOOK.md`：人工操作手册
4. `dispatch_task.py` 派工提示从 `config/policies.json` 读取约束，而不是硬编码路径/限制

完成这些后，再考虑第一次真实调用 ACP/执行 Agent。
