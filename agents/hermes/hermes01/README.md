# Hermes Agent 01 工作空间

## 基本信息

- **Agent ID**: agent-hermes-01
- **类型**: hermes
- **角色**: executor
- **后端**: Hermes CLI (`hermes chat -q ... --quiet`)
- **版本**: v0.10.0
- **模型**: doubao-seed-2-0-code-preview-260215
- **风险等级**: medium

## 说明

此目录是 Hermes Agent 在 Agent Chat Cluster 中的工作空间。

Hermes Agent 是第一个真实可执行的 AI Agent 后端，通过 `hermes chat --quiet` CLI 接收任务指令并返回执行结果。

适配器脚本位于 `scripts/hermes_adapter.py`，由 `dispatch_task.py` 调用。

## 后端配置

```json
{
  "type": "hermes-cli",
  "command": "hermes",
  "args": ["chat", "-q", "{prompt}", "--quiet", "--max-turns", "30"],
  "workDir": "G:\\hermers\\hermes-agent"
}
```

## 相关文件

- 注册配置: `config/agents.json`
- 适配器脚本: `scripts/hermes_adapter.py`
- Hermes 项目: `G:\hermers\hermes-agent`
