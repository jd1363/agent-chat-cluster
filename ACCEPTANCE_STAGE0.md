# 阶段 0 验收报告

验收时间：2026-06-14
验收人：胖小（项目管理员 / 架构决策 / 验收负责人）
执行工程师：OpenCode

## 结论

**阶段 0：通过。**

当前项目已完成 MVP 骨架搭建，满足“主控/管理员负责决策，OpenCode/ACP Agent 负责执行”的角色划分。项目未启动任何 ACP agent，未安装依赖，未执行危险命令。

## 项目位置

```text
G:\agent-chat-cluster
```

## 已完成文件

```text
README.md
PROJECT_PLAN.md
ACCEPTANCE_STAGE0.md
config/agents.json
config/policies.json
docs/REAL_COMMANDS.md
docs/SECURITY_NOTES.md
scripts/check_env.py
scripts/create_task.py
scripts/update_task.py
tasks/tasks.json
```

## 已完成目录

```text
agents/resident/
agents/ext/ext01~ext06/
config/
docs/
logs/audit/
logs/runs/
scripts/
tasks/
```

## 验收项

### 1. 目录结构

通过。关键目录均存在：

- `config`
- `docs`
- `scripts`
- `tasks`
- `logs/audit`
- `logs/runs`
- `agents/resident`
- `agents/ext`

### 2. JSON 配置

通过。以下 JSON 均可解析：

- `config/agents.json`
- `config/policies.json`
- `tasks/tasks.json`

### 3. OpenClaw Gateway 检查

通过。`scripts/check_env.py` 能找到：

```text
C:\Users\jjd\AppData\Roaming\npm\openclaw.CMD
```

并成功执行：

```text
openclaw gateway status
```

检测结果：

```text
RPC probe: ok
Dashboard: http://127.0.0.1:18789/
```

### 4. 任务台账初始状态

通过。最终 `tasks/tasks.json` 已重置为空台账：

```json
{
  "schemaVersion": "1.0",
  "nextId": 1,
  "tasks": []
}
```

### 5. 脚本语法检查

通过。已执行：

```text
python -m py_compile scripts\check_env.py scripts\create_task.py scripts\update_task.py
```

无语法错误。

### 6. 文档口径

通过。已修正：

- OpenClaw 主会话 / 项目经理 = 主控/管理员/决策
- OpenCode / ACP Agent = 执行工程师
- `sessions_spawn` 被正确描述为 OpenClaw 工具/API 层能力，而不是 shell CLI 命令

## 已修复问题

### 问题 1：`check_env.py` 假阳性

原问题：找不到 `openclaw` 时仍返回成功。

修复：

- 使用 `shutil.which` 查找 `openclaw` / `openclaw.cmd` / `openclaw.exe`
- 找不到即失败
- `openclaw gateway status` 返回非 0 即失败
- 超时即失败

### 问题 2：测试任务污染台账

原问题：测试时创建的 `Task-001` / `Task-002` 残留在初始台账。

修复：

- 最终重置 `tasks/tasks.json` 为空台账

### 问题 3：角色口径错误

原问题：README 把 OpenCode 写成主控节点。

修复：

- README 已改为：OpenClaw 主会话/项目经理负责决策，OpenCode/ACP Agent 负责执行。

### 问题 4：`sessions_spawn` 写成 CLI 命令

原问题：`REAL_COMMANDS.md` 把工具/API 层能力写成了 bash 命令。

修复：

- 已改为 OpenClaw 工具/API 层调用说明。

## 当前红线

阶段 1 开始前仍然保持：

- 不启动任何 ACP agent，除非单独派发阶段 1 任务
- 不开启全局广播
- 不自动外发消息
- 不自动自愈
- 不执行危险命令
- 不安装新依赖
- 不扩容 ext01~ext06

## 下一阶段建议

进入阶段 1：主控-单执行 Agent 闭环验证。

建议让 OpenCode 实现：

1. `logs/audit/` 审计日志写入工具
2. `logs/runs/` 单次运行记录格式
3. 任务状态流转规范：`pending -> in_progress -> done/failed/blocked`
4. `scripts/dispatch_task.py` 草案：只生成派工提示，不实际启动 ACP
5. `docs/TASK_PROTOCOL.md`：主控给执行 Agent 的任务消息格式

注意：阶段 1 仍然不自动启动 ACP Agent，先做“派工协议 + 审计日志 + 人工执行闭环”。
