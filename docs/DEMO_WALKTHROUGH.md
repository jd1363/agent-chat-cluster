# Agent Chat Cluster — 端到端演示流程

> 面向第一次接触本项目的人，展示从创建任务到执行完成的全链路。

## 演示环境

- **Python 3.10+**（`python --version` 确认）
- **已安装以下 CLI 之一**：`codex` / `codewhale` / `opencode` / `mimo`（用 `where codex` 确认）
- **项目路径**：`G:\agent-chat-cluster`
- **启动 Dashboard**：双击 `start_dashboard.bat`，或执行 `python web/server.py`
- **浏览器访问**：http://127.0.0.1:8765

---

## 演示路径 1：Dashboard 全流程（推荐）

### Step 1: 打开 Dashboard

- 浏览器访问 http://127.0.0.1:8765
- 看到 KPI 面板（任务总数、完成率、活跃 Agent 数）、任务表格、Agent 列表

### Step 2: 创建任务

在右侧"快速操作"面板填写：

| 字段 | 示例值 |
|------|--------|
| 任务标题 | 给天气项目加 /api/health 接口 |
| 任务描述 | 在 `G:\weather\weather-ai-project` 的 `app.py` 中添加 `/api/health` 健康检查接口，返回 `{"status":"ok","timestamp":"当前时间"}` |
| 指派给 | Codex |
| 优先级 | 中 |
| 项目路径 | `G:\weather\weather-ai-project` |

点击 **"创建并执行"**。

### Step 3: 观察执行

- 任务表格中出现新任务，状态变为 **IN PROGRESS**
- 点击任务行展开详情面板
- 实时查看日志输出（SSE 推送）
- 等待状态变为 **DONE**

### Step 4: 查看结果

- 任务详情中显示 **output** 字段，包含执行结果
- **Audit Log** 中显示执行记录（创建 → 派发 → 执行 → 完成）
- **Cost Chart** 中显示本次执行的成本

### Step 5: 重跑 / 取消

- 失败任务点 🔄 **重跑**：重新生成 prompt 并派发
- 运行中任务点 ⏹ **取消**：状态改为 cancelled
- **批量操作**：执行所有 Pending / 取消所有 Running

---

## 演示路径 2：命令行全流程

### Step 1: 环境检查

```powershell
cd G:\agent-chat-cluster
python scripts/check_env.py --skip-external
python scripts/validate_task.py
```

预期输出：`[OK]` 系列提示，确认台账、Agent 注册表、策略文件均正常。

### Step 2: 创建任务

```powershell
python scripts/create_task.py --title "测试任务" --description "Echo hello world" --priority low
```

预期输出：

```
[OK] 已创建 Task-XXX: 测试任务 (priority=low)
```

### Step 3: 派发并执行

```powershell
python scripts/dispatch_task.py --id Task-XXX --assignee agent-exec-01 --execute-real
```

此命令会：
1. 运行 preflight 校验（validate_task → assignee 检查 → policies 加载）
2. 更新任务状态为 `in_progress`
3. 生成 prompt 文件到 `tasks/dispatch/Task-XXX-prompt.txt`
4. 调用 `executor_bridge.py` 执行真实 CLI

### Step 4: 查看状态

```powershell
python scripts/list_tasks.py --status done
python scripts/show_audit.py --limit 5
```

### Step 5: 收集结果

```powershell
python scripts/openclaw_executor.py --task-id Task-XXX --collect
```

读取 `tasks/dispatch/Task-XXX-result.txt`，更新任务状态并写审计日志。

---

## 演示路径 3：多 Agent 并发

### Step 1: 创建多个任务

```powershell
python scripts/create_task.py --title "任务A" --description "做A" --priority medium
python scripts/create_task.py --title "任务B" --description "做B" --priority medium
```

### Step 2: 同时执行

打开两个终端窗口，同时运行：

```powershell
# 终端 1
python scripts/dispatch_task.py --id Task-XXX --assignee agent-exec-01 --execute-real
```

```powershell
# 终端 2
python scripts/dispatch_task.py --id Task-YYY --assignee agent-ext-01 --execute-real
```

### Step 3: 观察 Dashboard

两个任务同时显示 **IN PROGRESS**，各自独立完成后状态变为 **DONE**。Dashboard 实时刷新，可看到并发执行过程。

---

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 任务状态 **BLOCKED** | 输出质量检测未通过 | 人工审查 `tasks/dispatch/Task-XXX-result.txt` |
| 任务状态 **FAILED** | CLI 执行报错或超时 | 检查 `logs/runs/` 下的执行日志和 `executor_bridge` 输出 |
| CLI 未找到 | 工具未安装或不在 PATH | `where codex` 确认；或安装对应 CLI 工具 |
| 编码乱码 | 终端默认 GBK | `chcp 65001` 或设置环境变量 `PYTHONUTF8=1` |
| Dashboard 无法访问 | 服务未启动或端口占用 | 检查 `web_server_stdout.txt`；换端口 `python web/server.py --port 8766` |
| preflight 校验失败 | agents.json 或 policies.json 配置异常 | 运行 `python scripts/check_env.py` 查看详细错误 |
