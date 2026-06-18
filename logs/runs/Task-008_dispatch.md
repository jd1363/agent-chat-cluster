# 派工提示 — Task-008

> 生成时间: 2026-06-18T11:53:29.659838+00:00
> 指派给: agent-ext-01

## 任务信息

- **任务 ID**: Task-008
- **标题**: 阶段3：code review scripts/resend_unacked.py (重试)
- **优先级**: medium
- **状态**: in_progress（已派发）

## 执行约束（来源: config/policies.json）

- **最大运行时间**: 30 分钟
- **最大输出大小**: 1024 KB
- **最大并发**: 1
- **最大重试次数**: 1
- **工作目录**: `G:\agent-chat-cluster`
- **允许路径**: `scripts/`, `tasks/`, `logs/`, `config/`, `docs/`

## 禁止行为

1. 不得私自外发网络请求。
2. 不得启动其他 Agent。
3. 不得修改文件或目录权限。
4. 不得执行 `rm -rf`、`format`、`fdisk`、`regedit` 等危险命令。
5. 不得访问 `G:\agent chat` 原方案目录。

## 期望输出

请按 docs/TASK_PROTOCOL.md 中定义的执行 Agent → 主控回报格式提供结果。

## 审计要求

- 记录所有执行的命令。
- 记录所有变更的文件。
- 主动报告识别到的风险。
- 日志保留天数: 30 天。
