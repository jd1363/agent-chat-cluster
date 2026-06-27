---
name: task-execution-guide
description: 子 Agent 接收任务后的执行指南。规范了任务理解、文件操作、输出格式和完成标准。
---

# 任务执行指南

> 本文件是子 Agent 接收任务后的行为规范。无论你是什么 CLI 工具（Codex/CodeWhale/OpenCode/MiMo/Ollama），执行任务时都应遵循。

## 1. 理解任务

收到的 prompt 文件格式通常为：

```
# Task: Task-XXX — 标题

## 任务描述
...

## 执行要求
- 在项目目录 G:\agent-chat-cluster 内操作
- 修改的文件必须列出
- 完成后输出执行结果摘要

## 项目上下文
- 项目编码规范见 skills/project-conventions/SKILL.md
- 脚本用法见 skills/script-reference/SKILL.md
```

## 2. 文件操作规范

### 路径
- 所有路径用绝对路径：`G:/agent-chat-cluster/...`
- Python 中用 raw string 或正斜杠
- 不要用相对路径（当前工作目录可能不对）

### 编码
- 文件读写一律 UTF-8
- JSON 读写必须 `encoding='utf-8'`
- 中文输出用 `ensure_ascii=False`

### 并发安全
- 写 `tasks/tasks.json` 必须加文件锁：
```python
import sys; sys.path.insert(0, 'scripts')
from file_lock import FileLock
with FileLock('tasks/tasks.json'):
    # 读 → 改 → 写
    pass
```

### 禁止操作
- 不要删除整个目录
- 不要修改 `config/policies.json`（安全策略）
- 不要修改 `config/agents.json`（Agent 配置）
- 不要执行网络请求
- 不要安装新包

## 3. 代码风格

### Python
- 类型注解：`def foo(x: str) -> dict:`
- Docstring：简单函数也要有一行说明
- 错误处理：`try/except` 不要裸 `except`
- 日志：`print(f"[OK] ...")` 或 `print(f"[ERROR] ...")`

### 前端（HTML/CSS/JS）
- 单文件自包含（CSS + JS inline）
- Chart.js 用 CDN: `https://cdn.jsdelivr.net/npm/chart.js`
- 无 UI 框架（纯 CSS Grid/Flex）
- 响应式：`@media (max-width: 1024px)` 断点

## 4. 输出格式

任务完成后，在 stdout 输出：

```
## 执行结果

- 状态：成功/失败
- 修改文件：
  - path/to/file1.py (新增)
  - path/to/file2.py (修改)
- 关键改动：
  1. xxx
  2. xxx
- 测试：通过/未运行/失败
- 耗时：约 Xs
```

executor_bridge 会自动捕获 stdout 作为执行结果。

## 5. 完成标准

任务算"完成"需要满足：
1. ✅ 代码能运行（语法正确）
2. ✅ 不破坏现有功能
3. ✅ 输出格式正确
4. ✅ 没有引入新依赖（除非任务要求）
5. ✅ 中文注释和输出

如果任务无法完成：
- 在输出中说明原因
- 列出已尝试的方案
- 建议下一步

## 6. 常见任务类型

### 代码实现
- 读需求 → 读现有代码 → 写代码 → 测试 → 输出结果
- 不要只写代码不测试

### Bug 修复
- 读代码定位问题 → 修复 → 验证修复 → 输出结果
- 说明根因

### 文档编写
- 读代码/需求 → 写文档 → 输出文件路径
- Markdown 格式

### 测试
- 读代码 → 写测试 → 跑测试 → 输出结果
- 测试框架：pytest

## 7. CodeWhale 特殊注意

CodeWhale 在 `--auto` 模式下：
- 完成任务后进程可能不退出（executor_bridge 会检测 `{"type":"done"}` 并 kill）
- 所以任务完成后要确保 stdout 中有完整的结果输出
- 不要在 stdout 打印大量调试信息（会干扰完成检测）
- stderr 可以打印调试信息

## 8. 错误处理

遇到错误时：
1. **不要崩溃** — try/except 捕获，输出错误信息
2. **不要静默** — 错误必须打印到 stderr
3. **不要重试危险操作** — 比如文件删除失败不要自动重试
4. **输出明确** — "ERROR: ..." 而不是模糊的 traceback
