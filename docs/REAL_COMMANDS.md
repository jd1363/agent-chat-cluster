# 当前可用命令清单

本文档记录 MVP 阶段经实际验证、可靠可用的命令，以及暂不可直接执行的命令说明。

---

## 已验证命令

### OpenClaw Gateway 管理

```bash
openclaw gateway status
openclaw gateway start
openclaw gateway stop
openclaw gateway restart
```

**说明**：以上命令用于查看或控制 OpenClaw 网关状态。在 MVP 阶段，建议仅在 `scripts/check_env.py` 中做可用性探测，不纳入自动化流程。

### 建议的 ACP 调用方式

如需与 ACP 运行时交互，建议在 OpenClaw 工具/API 层使用 `sessions_spawn(runtime="acp", agentId=..., cwd=..., mode=...)` 显式创建会话。MVP 阶段**不要**在脚本中自动启动 ACP agent。

---

## 暂不可直接执行的命令

以下命令在原方案文档中有提及，但当前 MVP 阶段**未经验证**，请勿在自动化脚本中直接调用：

| 命令 / 路径 | 原因 |
|-------------|------|
| `/usage` | 未验证输出格式与稳定性 |
| `/task` | 任务系统已由本地 `tasks/tasks.json` + 脚本替代 |
| `/snapshot` | 未验证快照生成逻辑与存储位置 |
| `/audit` | 审计日志格式未标准化，需人工检查 |
| `/self-heal` | **明确禁止**：策略 `autoSelfHeal` 已关闭 |
| `/permission` | 权限系统未接入，需人工审批 |

---

## 使用建议

1. **优先使用本地脚本**：任务管理请使用 `scripts/create_task.py` 与 `scripts/update_task.py`。
2. **命令探测而非执行**：`check_env.py` 仅探测命令是否存在，不执行副作用操作。
3. **人工确认原则**：任何涉及 `start` / `restart` / `spawn` 的操作，需人工确认后再执行。

---

*文档版本：MVP-v1.0*
