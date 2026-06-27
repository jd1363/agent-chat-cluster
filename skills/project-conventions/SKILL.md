---
name: project-conventions
description: Agent Chat Cluster 项目的编码规范、目录结构、文件锁机制和提交规范。所有 Agent 在执行任务前必须阅读。
---

# 项目编码规范

> 所有 Agent 在执行任务前必须阅读本文件。

## 项目位置

`G:\agent-chat-cluster`

## 目录结构

```
agent-chat-cluster/
├── config/          # agents.json, policies.json — Agent 配置和策略
├── scripts/         # 所有 Python 脚本（任务管理、执行、审计）
├── tasks/           # 任务台账 + dispatch 派工文件
├── tasks/dispatch/  # 生成的 prompt 文件和执行结果
├── logs/            # 审计日志、事件日志、成本记录
│   ├── audit/       # 按日期 YYYY-MM-DD.jsonl
│   ├── events/      # 事件日志
│   └── cost/        # 成本记录
├── web/             # Web Dashboard (server.py + dashboard.html)
├── docs/            # 项目文档
├── memory/          # 项目记忆文件（按日期）
├── skills/          # 共享技能目录（本文件所在位置）
├── state/           # 系统状态快照
├── snapshots/       # 配置快照
└── agents/          # Agent 工作目录
    ├── resident/    # 常驻 Agent
    └── ext/         # 外部 Agent
```

## 编码规范

### Python 脚本
- Python 3.10+，类型注解必须
- 文件编码 UTF-8，`print()` 输出中文时用 `ensure_ascii=False`
- JSON 读写必须指定 `encoding='utf-8'`
- 所有路径用 raw string 或正斜杠（`G:/agent-chat-cluster/...`）
- 函数有 docstring，复杂逻辑有注释

### 文件锁机制
- 并发写 tasks.json 必须用 `file_lock.py` 的 `FileLock`
- 用法：`from file_lock import FileLock; with FileLock('tasks/tasks.json'): ...`
- 锁超时 10s，超时抛 `TimeoutError`

### Git 提交规范
- commit message 格式：`type: 简述`
- type: feat / fix / test / docs / refactor / chore
- 中文描述，简洁明了
- 示例：`feat: Web Dashboard 集成执行按钮`

### 任务状态流转
```
pending → in_progress → done
                     ↘ failed
                     ↘ cancelled
```

### 安全红线
- 禁止执行 `rm -rf /`、`format`、`fdisk`、`regedit` 等危险命令
- 禁止 Agent 自动发起外部网络请求
- 禁止自动自愈
- 最大并发：2 个 Agent
- 单任务最大运行时间：30 分钟
- 单任务输出上限：1024 KB
- Agent 只允许在 `scripts/ tasks/ logs/ config/ docs/` 目录内读写

## API 端点参考（Web Dashboard 后端）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/agents` | GET | 获取所有 Agent 配置 |
| `/api/tasks` | GET | 获取任务列表 + 统计 |
| `/api/tasks/create` | POST | 创建任务 |
| `/api/tasks/execute` | POST | 执行任务（调 dispatch_task） |
| `/api/audit` | GET | 获取审计日志 |
| `/api/cost` | GET | 获取成本记录 |
| `/api/events` | GET | 获取事件日志 |
| `/api/messages` | GET | 获取消息列表 |
| `/api/alerts` | GET | 获取告警 |
| `/api/policies` | GET | 获取策略配置 |
| `/api/state` | GET | 获取系统状态 |
| `/api/stream/events` | SSE | 全局事件流 |
| `/api/stream/tasks/{id}/logs` | SSE | 单任务日志流 |

## Agent 映射

| Agent ID | CLI 工具 | 显示名 | 超时 |
|----------|---------|--------|------|
| agent-exec-01 | codex exec | Codex | 120s |
| agent-ext-01 | codewhale exec --auto --output-format stream-json | CodeWhale | 300s |
| agent-ext-02 | opencode run --dangerously-skip-permissions | OpenCode | 120s |
| agent-ext-03 | ollama run (Qwen2.5-14B) | Ollama | 120s |
| agent-ext-04 | mimo run --dangerously-skip-permissions | MiMo | 120s |
| agent-ext-05 | codex exec | Codex-2 | 300s |
| agent-ext-06 | codewhale exec --auto --output-format stream-json | CodeWhale-2 | 300s |

## executor_bridge 特殊机制

- **完成检测**：CodeWhale 的 stream-json 模式下，检测 `{"type":"done"}` 后主动 kill 进程
- **输出解码**：UTF-8 → GBK → replace 三级回退（解决 Windows 中文编码问题）
- **进程组 kill**：超时后 `taskkill /T /F` 清理整个进程树
