---
name: script-reference
description: Agent Chat Cluster 所有 Python 脚本的用法参考。子 Agent 执行任务时需要调用这些脚本。
---

# 脚本参考手册

> 所有脚本在 `G:\agent-chat-cluster\scripts\` 目录下，用 `python scripts/xxx.py` 执行。
> 执行前 `cd G:\agent-chat-cluster`。

## 任务管理

### create_task.py — 创建任务
```bash
python scripts/create_task.py --title "任务标题" --priority low|medium|high [--assignee agent-id]
```
- 输出：`[OK] 已创建 Task-XXX: 标题 (priority=xxx)`
- 参数：`--title`（必填）、`--priority`（默认 low）、`--assignee`（可选）

### dispatch_task.py — 派工 + 生成 prompt
```bash
python scripts/dispatch_task.py --id Task-XXX --assignee agent-id --execute
```
- `--execute`：同时调用 openclaw_executor 生成 prompt 文件
- `--dry-run`：只打印不实际执行
- 生成文件：`tasks/dispatch/Task-XXX-prompt.txt`

### complete_task.py — 完成任务
```bash
python scripts/complete_task.py --id Task-XXX --output "执行结果"
```

### update_task.py — 更新任务
```bash
python scripts/update_task.py --id Task-XXX --status pending|in_progress|done|failed|cancelled [--output "结果"]
```

### validate_task.py — 验证任务
```bash
python scripts/validate_task.py --id Task-XXX
```

### list_tasks.py — 列出任务
```bash
python scripts/list_tasks.py [--status pending|in_progress|done|failed] [--limit 10]
```

## 执行引擎

### executor_bridge.py — CLI 执行桥接
```bash
python scripts/executor_bridge.py --task-id Task-XXX --assignee agent-id [--timeout 300] [--dry-run] [--project G:\path]
```
- 读取 `tasks/dispatch/Task-XXX-prompt.txt` 作为输入
- 根据 agents.json 选择 CLI 工具执行
- 结果写入 `tasks/dispatch/Task-XXX-result.txt`
- 自动更新任务状态为 done/failed
- 自动写审计日志和成本记录
- `--dry-run`：只打印命令不执行

### openclaw_executor.py — Prompt 生成器
```bash
python scripts/openclaw_executor.py --task-id Task-XXX
```
- 读取任务信息，生成标准 prompt 文件
- 输出：`tasks/dispatch/Task-XXX-prompt.txt`

## 审计与日志

### audit_log.py — 审计日志
```bash
python scripts/audit_log.py --event "事件类型" --task-id Task-XXX [--detail "详情"]
```
- 日志位置：`logs/audit/YYYY-MM-DD.jsonl`

### event_log.py — 事件日志
```bash
python scripts/event_log.py --event "事件类型" --source "来源" [--data '{"key":"value"}']
```

### show_audit.py — 查看审计
```bash
python scripts/show_audit.py [--date YYYY-MM-DD] [--limit 20]
```

### show_history.py — 查看历史
```bash
python scripts/show_history.py --id Task-XXX
```

## 成本管理

### record_cost.py — 记录成本
```bash
python scripts/record_cost.py --task-id Task-XXX --agent-id agent-xxx --tokens-in 1000 --tokens-out 500 --cost-usd 0.01
```

### show_cost.py — 查看成本
```bash
python scripts/show_cost.py [--by-agent] [--date YYYY-MM-DD]
```

## 通信

### send_message.py — 发送消息
```bash
python scripts/send_message.py --from agent-xxx --to agent-yyy --content "消息内容"
```

### list_messages.py — 查看消息
```bash
python scripts/list_messages.py [--limit 30]
```

### broadcast.py — 广播（默认禁止）
```bash
python scripts/broadcast.py --from agent-xxx --content "消息"
```
⚠️ 需要手动审批，policies.json 中 `globalBroadcast.allowed = false`

## 其他

### check_env.py — 环境检查
```bash
python scripts/check_env.py
```

### check_alerts.py — 告警检查
```bash
python scripts/check_alerts.py
```

### snapshot_config.py — 配置快照
```bash
python scripts/snapshot_config.py
```

### suggest_assignee.py — 推荐 Agent
```bash
python scripts/suggest_assignee.py --task-id Task-XXX
```

### file_lock.py — 文件锁（模块）
```python
from file_lock import FileLock
with FileLock('tasks/tasks.json'):
    # 并发安全操作
    pass
```

### command_map.py — 命令映射（模块）
```python
from command_map import map_command
result = map_command("dispatch", task_id="Task-001", assignee="agent-ext-01")
```

### build_state.py — 状态构建器
```bash
python scripts/build_state.py
```
- 生成 `state/current.json`，包含系统全局状态

### scheduler_tick.py — 调度器心跳
```bash
python scripts/scheduler_tick.py
```

### benchmark_pipeline.py — 基准测试
```bash
python scripts/benchmark_pipeline.py
```

## 常见用法示例

### 完整任务执行流程
```bash
# 1. 创建任务
python scripts/create_task.py --title "实现用户登录" --priority medium

# 2. 派工 + 生成 prompt
python scripts/dispatch_task.py --id Task-001 --assignee agent-ext-02 --execute

# 3. 执行（CLI 桥接）
python scripts/executor_bridge.py --task-id Task-001 --assignee agent-ext-02

# 4. 验证
python scripts/validate_task.py --id Task-001

# 5. 查看审计
python scripts/show_audit.py --limit 5
```
