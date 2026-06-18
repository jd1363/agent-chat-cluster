# 阶段 2 前置安全闸第二块验收报告

验收时间：2026-06-14
验收人：胖小（项目管理员 / 架构决策 / 验收负责人）
执行工程师：CodeWhale（`codewhale exec --auto`）

## 结论

**阶段 2 前置安全闸第二块：通过。**

已完成：

- 新增 `scripts/list_tasks.py`
- 新增 `scripts/show_audit.py`
- 新增 `docs/OPERATOR_RUNBOOK.md`
- 更新 `README.md`
- 更新 `PROJECT_PLAN.md`
- 最终保持 `tasks/tasks.json` 为空台账

本阶段仍未启动任何 ACP agent，未安装依赖，未执行危险命令。

## 修改文件

```text
scripts/list_tasks.py
scripts/show_audit.py
docs/OPERATOR_RUNBOOK.md
README.md
PROJECT_PLAN.md
ACCEPTANCE_STAGE2_PRECHECK_BLOCK2.md
```

## list_tasks.py 功能

`list_tasks.py` 是只读任务台账查看工具。

支持：

```text
python scripts/list_tasks.py
python scripts/list_tasks.py --status pending
python scripts/list_tasks.py --status done
python scripts/list_tasks.py --assignee agent-exec-01
python scripts/list_tasks.py --assignee none
python scripts/list_tasks.py --json
```

约束：

- 只读取 `tasks/tasks.json`
- 不修改任何文件
- 默认按 `id` 排序
- `--assignee none` 匹配 `assignee` 为 null / 空字符串 / 不存在

## show_audit.py 功能

`show_audit.py` 是只读审计日志查看工具。

支持：

```text
python scripts/show_audit.py
python scripts/show_audit.py --date YYYY-MM-DD
python scripts/show_audit.py --task-id Task-001
python scripts/show_audit.py --event-type task_created
python scripts/show_audit.py --limit 5
python scripts/show_audit.py --json
```

约束：

- 只读取 `logs/audit/*.jsonl`
- 不修改任何文件
- 默认读取 UTC 今天的审计日志
- 默认最多显示 20 条
- 记录按 timestamp 降序显示

## OPERATOR_RUNBOOK.md

新增人工操作手册，覆盖：

- 环境自检
- 创建任务
- 校验任务
- 派发任务
- 查看任务
- 完成任务
- 查看审计
- `--force` 管理员覆盖规则
- 禁止事项
- 进入真实 ACP 执行前的条件

## 验收测试

### 1. 语法检查

已执行：

```text
python -m py_compile scripts\list_tasks.py scripts\show_audit.py
```

结果：通过。

### 2. 空台账查看

已执行：

```text
python scripts\list_tasks.py
```

结果：通过，输出无匹配任务。

### 3. 审计日志 JSON 查看

已执行：

```text
python scripts\show_audit.py --limit 3 --json
```

结果：通过，输出合法 JSON，包含最近 3 条审计记录。

### 4. CodeWhale 自测记录

CodeWhale 用 3 个测试任务验证：

- `list_tasks.py` 默认输出：显示 3 个任务
- `list_tasks.py --status pending`：只显示 pending 任务
- `list_tasks.py --status done`：只显示 done 任务
- `list_tasks.py --assignee agent-exec-01`：只显示已派发任务
- `list_tasks.py --assignee none`：显示未指派任务
- `list_tasks.py --json`：输出合法 JSON
- `show_audit.py --limit 5`：显示最近 5 条审计记录
- `show_audit.py --event-type task_created --limit 5`：按事件类型过滤
- `show_audit.py --json --limit 3`：输出合法 JSON

### 5. 最终任务台账

最终 `tasks/tasks.json` 已重置为空：

```json
{
  "schemaVersion": "1.0",
  "nextId": 1,
  "tasks": []
}
```

## 已知非阻塞问题

Windows 控制台输出中文存在 mojibake（乱码）现象，但文件内容为 UTF-8，JSON 输出可解析，不影响功能正确性。

## 当前项目状态

- 阶段 0：通过
- 阶段 1：通过
- 阶段 2 前置安全闸第一块：通过
- 阶段 2 前置安全闸第二块：通过

## 下一步建议

阶段 2 前置安全闸第三块：

1. 修改 `dispatch_task.py`：派工提示从 `config/policies.json` 读取约束，而不是硬编码。
2. 增加 `scripts/preflight_dispatch.py` 或在 `dispatch_task.py` 内整合完整 preflight：先跑 `validate_task.py`，再校验 agent，再生成派工。
3. 清理/归档测试审计日志策略：测试日志可保留，但正式演示前需要区分 test/prod。
4. 完成后再评估是否进入首次真实 ACP Agent 调用。
