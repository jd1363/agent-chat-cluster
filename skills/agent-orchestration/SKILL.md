---
name: agent-orchestration
description: Agent Chat Cluster 多 Agent 协作编排指南。任务拆解、Agent 选择、并发控制、结果汇总规范。
---

# Agent 编排指南

> 适用于主控 Agent 和调度系统。子 Agent 不需要读本文件。

## 1. Agent 能力矩阵

| Agent | CLI 工具 | 擅长 | 限制 | 超时 |
|-------|---------|------|------|------|
| Codex (agent-exec-01) | codex exec | 通用编码、快速响应 | 无文件操作权限 | 120s |
| CodeWhale (agent-ext-01) | codewhale exec --auto | 复杂任务、文件读写、工具调用 | 启动慢、需 done 检测 | 300s |
| OpenCode (agent-ext-02) | opencode run | 文件操作、代码修改 | 中文输出可能乱码 | 120s |
| Ollama (agent-ext-03) | ollama run (Qwen2.5-14B) | 本地推理、离线运行 | 无工具调用能力 | 120s |
| MiMo (agent-ext-04) | mimo run | 文件操作、代码修改 | 较慢 | 120s |
| Codex-2 (agent-ext-05) | codex exec | 通用编码（第二实例） | 同 Codex | 300s |
| CodeWhale-2 (agent-ext-06) | codewhale exec --auto | 复杂任务（第二实例） | 同 CodeWhale | 300s |

## 2. 任务分配策略

| 任务类型 | 推荐 Agent | 理由 |
|---------|-----------|------|
| 快速代码修改（单文件） | OpenCode 或 MiMo | 有文件操作权限，响应快 |
| 复杂多步骤任务 | CodeWhale | 支持 --auto 工具调用 |
| 纯文本/分析任务 | Codex 或 Ollama | 不需要文件操作 |
| 并发执行（2 个同时） | OpenCode + MiMo | 已验证并发兼容 |
| 重型任务（可能>120s） | CodeWhale 或 Codex-2 | 300s 超时 |

### 并发规则
- 最大并发数: 2（policies.json 规定）
- 并发安全: tasks.json 已有 file_lock 保护
- 已验证组合: OpenCode(读) + MiMo(写) 同时执行无冲突
- 禁止: 两个 Agent 同时写同一文件

### 失败重试
- 最多重试 1 次（policies.json maxRetries）
- 重试前检查：CLI 是否安装、超时是否够、prompt 是否清晰
- 第二次失败标记 failed，转人工复核

## 3. 任务生命周期

```
创建 (create_task)
  → 派工 (dispatch_task --execute)
    → 生成 prompt (openclaw_executor)
      → CLI 执行 (executor_bridge)
        → 成功: complete_task
        → 失败: 重试(最多1次) → 仍失败标记 failed
```

## 4. Prompt 编写规范

给 CLI Agent 的 prompt 必须包含：
1. 任务描述：清晰、具体的行动指令
2. 工作目录：`G:\agent-chat-cluster`
3. 输出要求：明确产出物的格式和位置
4. 约束：不要修改 tasks.json、不要修改 config/、不要执行危险命令

## 5. 结果验收标准

1. 文件存在：产出文件路径正确、文件非空
2. 语法正确：Python 脚本能 `python -m py_compile` 通过
3. 功能完整：核心功能实现，没有 TODO 占位
4. 无副作用：没有意外修改关键文件
5. git diff 只包含预期变更

## 6. 安全红线

- 禁止自动启动 ACP/全局广播/自愈/外发
- 禁止执行危险命令（rm -rf, format 等）
- Agent 只允许在 scripts/ tasks/ logs/ config/ docs/ 目录内读写
- 所有外部操作需人工审批
