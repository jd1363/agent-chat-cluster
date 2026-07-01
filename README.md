<div align="center">

# 🤖 Agent Chat Cluster

### 受控的多 Agent 协作执行平台

由 OpenClaw 主会话担任主控/管理员，多种 CLI Agent（Codex、CodeWhale、OpenCode、MiMo）作为执行工程师，完成任务调度、真实执行、状态追踪与审计。

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()
[![Status](https://img.shields.io/badge/Status-MVP%20v1%20Complete-success)]()

</div>

---

## ✨ 核心特性

| 特性 | 描述 |
|------|------|
| 🎯 **主控 + 多执行 Agent** | 主控负责任务下发/状态追踪/策略校验，Agent 负责真实执行 |
| ⚡ **真实 CLI 执行引擎** | dispatch → executor_bridge → 真实 CLI 工具，端到端自动化 |
| 🖥️ **Web Dashboard** | 实时控制面板：任务/Agent/审计/成本，支持执行/取消/重跑/批量操作 |
| 📋 **任务台账** | JSON 任务生命周期管理（pending → in_progress → done/failed/blocked） |
| 🔒 **安全策略** | 文件锁、命令审批、preflight 校验、风险等级控制 |
| 📊 **审计日志** | 不可篡改的 JSONL 审计轨迹，每次操作都有记录 |
| 💰 **成本追踪** | 按 Agent 统计 token 消耗和费用 |
| 📨 **消息总线** | 主控 ↔ Agent 轻量级消息通道，ACK 机制 |

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    Web Dashboard                         │
│  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Task Table │ │ Agent List│ │ Audit Log│ │ Cost Chart│ │
│  └─────┬─────┘ └───────────┘ └──────────┘ └──────────┘ │
│        │ Execute / Kill / Rerun / Batch                  │
└────────┼────────────────────────────────────────────────┘
         │ POST /api/tasks/*
         ▼
┌─────────────────────────────────────────────────────────┐
│                    server.py (REST + SSE)                │
│  GET: /api/tasks /api/agents /api/audit /api/cost ...   │
│  POST: /api/tasks/execute /kill /rerun /batch /create   │
│  SSE: /api/stream/events /api/stream/tasks/{id}/logs    │
└────────┬────────────────────────────────────────────────┘
         │ subprocess
         ▼
┌─────────────────────────────────────────────────────────┐
│              dispatch_task.py --execute-real             │
│  1. preflight (validate_task → agent check → policies)  │
│  2. 生成 prompt (openclaw_executor)                      │
│  3. 调用 executor_bridge                                 │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                  executor_bridge.py                      │
│  · 读取 Agent executor 配置                              │
│  · 构建 CLI 命令（{prompt} 替换）                        │
│  · subprocess 执行 + 流式读取 + 完成检测                 │
│  · 输出质量检测（失败信号 / 过短 / 空输出）              │
│  · 写结果文件 + 更新任务状态 + 审计日志                  │
│  · 项目模式：注入上下文 + 附加 git diff + 解析 file: 块  │
└────────┬────────────────────────────────────────────────┘
         │
    ┌────┴────┬────────┬────────┬────────┐
    ▼         ▼        ▼        ▼        ▼
┌────────┐┌────────┐┌──────┐┌──────┐┌──────┐
│ Codex  ││CodeWhale││OpenCode││ MiMo ││Ollama│
│        ││        ││       ││      ││(off) │
└────────┘└────────┘└──────┘└──────┘└──────┘
```

---

## 🚀 快速开始

### 环境要求

- **Python 3.10+**
- **Windows / Linux / macOS**（Windows 为主测试环境）
- 至少一个 CLI 执行工具（Codex / CodeWhale / OpenCode / MiMo / Ollama）

### 1. 克隆仓库

```bash
git clone https://github.com/yourname/agent-chat-cluster.git
cd agent-chat-cluster
```

### 2. 检查环境

```bash
python scripts/check_env.py --skip-external
```

### 3. 启动 Web Dashboard

**Windows 一键启动：**
```bash
start_dashboard.bat
```

**手动启动：**
```bash
python web/server.py --port 8765
```

浏览器打开 http://127.0.0.1:8765 即可看到控制面板。

### 4. 命令行方式

```bash
# 创建任务
python scripts/create_task.py --title "My first task" --description "Do something cool"

# 派发 + 执行（一步到位）
python scripts/dispatch_task.py --id Task-001 --assignee agent-exec-01 --execute-real

# 查看所有任务
python scripts/list_tasks.py

# 校验台账完整性
python scripts/validate_task.py
```

---

## 🖥️ Web Dashboard 功能

| 功能 | 描述 |
|------|------|
| 📊 **KPI 仪表盘** | 总任务/进行中/已完成/失败/Agent 数一目了然 |
| 📋 **任务表格** | 按状态过滤，行内操作按钮（▶执行 / ⏹取消 / 🔄重跑） |
| 🔧 **批量操作** | 一键执行所有 Pending、一键取消所有 Running |
| 📝 **任务详情** | 点击展开，含 timeout/dry-run/project 参数输入 |
| 🤖 **Agent 状态** | 实时显示 Agent 在线状态、CLI 命令、超时配置 |
| 📜 **审计日志** | 实时滚动，按类型着色（create/dispatch/done/fail） |
| 💰 **成本图表** | 按 Agent 统计 USD 和 Token 消耗 |
| 📡 **SSE 实时推送** | 任务状态变更、审计日志、Agent 状态自动刷新 |
| 📺 **执行日志流** | 实时查看 CLI 输出日志 |

---

## ⚡ CLI 执行引擎

### 支持的 CLI 工具

| Agent | CLI 命令 | 状态 | 测试结果 |
|-------|---------|------|----------|
| **Codex** | `codex exec "{prompt}"` | ✅ 启用 | 端到端验证通过 |
| **CodeWhale** | `codewhale exec --auto --output-format stream-json "{prompt}"` | ✅ 启用 | 26.6s，stream-json 模式 |
| **OpenCode** | `opencode run --dangerously-skip-permissions "{prompt}"` | ✅ 启用 | 26.2s，输出最清晰 |
| **MiMo** | `mimo run --dangerously-skip-permissions "{prompt}"` | ✅ 启用 | 82.6s，支持中文 |
| **Ollama** | `ollama run maayan/Qwen2.5-14B-Instruct-GGUF:latest "{prompt}"` | ⏸ 禁用 | 服务未运行 |

### 执行流程

```bash
# 一键执行（推荐）
python scripts/dispatch_task.py --id Task-001 --assignee agent-exec-01 --execute-real

# 项目模式：注入项目上下文 + 附加 git diff + 解析 file: 代码块写入文件
python scripts/dispatch_task.py --id Task-001 --assignee agent-ext-02 --execute-real --project G:/weather/weather-ai-project --write-output

# dry-run 模式
python scripts/dispatch_task.py --id Task-001 --assignee agent-exec-01 --execute-real --dry-run

# 自定义超时
python scripts/dispatch_task.py --id Task-001 --assignee agent-ext-01 --execute-real --timeout 300
```

### 输出质量检测

executor_bridge 自动检测 CLI 输出质量：
- **失败信号检测**：中英文正则匹配（"I cannot" / "无法理解" / "请提供更多" 等）
- **输出过短检测**：< 20 字符标记为 needs_review
- **空输出检测**：无输出标记为 needs_review
- 质量可疑的任务自动标记为 `blocked`，等待人工审查

---

## 📁 项目结构

```
agent-chat-cluster/
├── web/                    # Web Dashboard
│   ├── server.py          # REST API + SSE 服务器
│   └── dashboard.html     # 前端控制面板
├── scripts/                # 核心脚本
│   ├── create_task.py     # 创建任务
│   ├── dispatch_task.py   # 派发任务（支持 --execute-real）
│   ├── executor_bridge.py # CLI 执行桥接器
│   ├── run.py             # 一站式入口（create+dispatch+execute）
│   ├── complete_task.py   # 完成任务
│   ├── update_task.py     # 更新任务
│   ├── validate_task.py   # 台账校验
│   ├── list_tasks.py      # 查看任务列表
│   ├── check_env.py       # 环境自检
│   ├── audit_log.py       # 审计日志模块
│   ├── show_audit.py      # 查看审计日志
│   ├── show_cost.py       # 查看成本
│   ├── record_cost.py     # 记录成本
│   ├── check_alerts.py    # 告警检查
│   ├── send_message.py    # 发送消息
│   ├── receive_message.py # 接收消息
│   ├── broadcast.py       # 广播（受策略控制）
│   ├── event_log.py       # 事件日志
│   ├── file_lock.py       # 文件锁（排他写入）
│   ├── openclaw_executor.py # prompt 生成与结果收集
│   └── fix_encoding.py    # UTF-8 编码修复
├── config/                # 配置
│   ├── agents.json        # Agent 注册表
│   └── policies.json      # 执行策略
├── tasks/                 # 任务数据
│   ├── tasks.json         # 任务台账
│   └── dispatch/          # 派工 prompt 与结果文件
├── logs/                  # 运行日志
│   ├── audit/             # 审计日志 (JSONL)
│   ├── events/            # 事件日志 (JSONL)
│   ├── messages/          # 消息日志 (JSONL)
│   ├── cost/              # 成本日志 (JSONL)
│   └── runs/              # 派工记录
├── docs/                  # 文档
│   ├── OPERATOR_RUNBOOK.md # 操作手册
│   ├── DEMO_WALKTHROUGH.md # 演示流程
│   ├── TASK_PROTOCOL.md    # 任务协议
│   ├── SECURITY_NOTES.md   # 安全说明
│   └── SYSTEM_ARCHITECTURE.md # 系统架构
├── start_dashboard.bat    # 一键启动 Dashboard
├── stop_dashboard.bat     # 一键停止 Dashboard
├── README.md              # 本文件
└── PROJECT_PLAN.md        # 项目路线图
```

---

## 🔒 安全策略

| 策略 | 说明 |
|------|------|
| **文件锁** | tasks.json 读写使用排他锁，防止并发写入损坏 |
| **Preflight 校验** | 派工前依次校验：台账完整性 → Agent 存在且启用 → 策略加载 |
| **风险等级** | 每个 Agent 有 riskLevel（low/medium/high），策略可按等级限制 |
| **命令审批** | 未审批的全局广播/自愈/外发默认禁止 |
| **最大并发** | maxConcurrency=2，防止资源耗尽 |
| **超时控制** | 每个 Agent 可配置 timeoutSeconds，防止僵尸进程 |
| **输出截断** | maxOutputKB 限制单任务输出大小 |
| **路径安全** | file: 代码块写入时拒绝 `..` 和绝对路径 |

---

## 📊 项目数据

- **78 个任务** 已执行（48 done / 23 cancelled / 6 failed / 1 pending）
- **5 种 CLI 工具** 已接入并测试通过
- **17 个 Bug** 已修复（3 Critical + 6 High + 8 Medium）
- **纯 Python 标准库** — 零外部依赖

---

## 📜 开发历程

| 日期 | 里程碑 |
|------|--------|
| 2026-06-14 | Phase 0 — 基础框架搭建 |
| 2026-06-17 | Phase 1 — 主控 ↔ Agent 闭环验证 |
| 2026-06-18 | Phase 2 — 多 Agent 扩展 + 安全闸门 |
| 2026-06-20 | Phase 3 — 真实 subagent 验证 + 消息总线 |
| 2026-06-25 | 真实执行引擎接入（executor_bridge） |
| 2026-06-30 | 全面审计 + 17 Bug 修复 + 死脚本清理 |
| 2026-07-01 | Dashboard 操作面板 + CLI 链路测试 + 文档收口 |

---

## 📖 文档

- [项目路线图](PROJECT_PLAN.md)
- [操作手册](docs/OPERATOR_RUNBOOK.md)
- [演示流程](docs/DEMO_WALKTHROUGH.md)
- [任务协议](docs/TASK_PROTOCOL.md)
- [安全说明](docs/SECURITY_NOTES.md)
- [系统架构](docs/SYSTEM_ARCHITECTURE.md)
- [命令参考](docs/COMMAND_REFERENCE.md)

---

## 🛠️ 技术栈

- **后端**: Python 3.10+（纯标准库，零依赖）
- **前端**: 原生 HTML/CSS/JS + Chart.js
- **通信**: REST API + SSE (Server-Sent Events)
- **数据存储**: JSON 文件（无需数据库）
- **CLI 工具**: Codex / CodeWhale / OpenCode / MiMo / Ollama

---
