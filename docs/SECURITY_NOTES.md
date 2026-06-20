# 安全备忘

本文档列出 Agent Chat Cluster 在 MVP 及后续阶段需持续关注的安全风险与缓解措施。

---

## 1. 提示注入（Prompt Injection）

**风险**：Agent 接收到的任务内容或外部输入可能包含恶意指令，导致 Agent 偏离原定目标、泄漏信息或执行未授权操作。

**缓解**：
- 对所有输入进行上下文隔离，Agent 无法直接访问主控的系统级提示。
- 任务内容在传递前做基础校验（长度、敏感关键词过滤）。
- 高危险操作必须经主控人工确认，不依赖 Agent 自主判断。

---

## 2. 密钥泄漏（Secret Leakage）

**风险**：Agent 在执行任务时可能将 API Key、Token、密码等敏感信息输出到日志或返回结果中。

**缓解**：
- 禁止在 `tasks/tasks.json`、`logs/` 及任何版本控制中硬编码密钥。
- Agent 的 `cwd` 隔离，限制其对敏感配置文件的访问。
- 日志脱敏：对 stdout/stderr 进行正则扫描，自动掩码疑似密钥内容。
- 定期审计 `logs/audit` 目录，发现泄漏立即轮换凭证。

---

## 3. 全局广播 / 受控主控多播（Global Broadcast）

**风险**：未经授权的全局消息广播可能导致信息交叉污染、权限扩散或拒绝服务。

**缓解**：
- 策略 `globalBroadcast` 默认关闭。脚本层面读取 `config/policies.json`，未显式 `--manual-approval` 时拒绝 `--to all`。
- 当前允许的只是“主控受控多播到所有已启用 Agent”，不是 Agent 群聊；Agent 仍禁止直接向其他 Agent 发送消息。
- 多播审计事件 `broadcast_sent` 必须记录 `recipientCount`、收件人列表和 `manualApproval` 字段。
- 优先使用点对点消息；多播只用于维护通知、巡检等低风险场景。

---

## 4. 文件冲突（File Conflicts）

**风险**：多个 Agent 同时读写同一文件，可能导致数据损坏、竞态条件或信息泄漏。

**缓解**：
- MVP 阶段最大并发为 1，从机制上避免多 Agent 同时操作。
- Agent 的 `cwd` 严格隔离，默认不可跨目录访问。
- 共享资源（如 `tasks/tasks.json`）仅由主控脚本操作，Agent 无直接写权限。
- 后续阶段如需共享文件，引入文件锁（file lock）或事务日志。

---

## 5. 第三方 Agent 供应链风险

**风险**：引入的外部 Agent（ext 席位）可能携带恶意代码、后门或不可预期行为。

**缓解**：
- 所有 ext Agent 默认 `enabled: false`，启用前需代码审查与环境隔离验证。
- 限制 ext Agent 的 `riskLevel` 为 medium，禁止直接提升至高权限。
- 对 ext Agent 的执行输出进行额外审计，与 resident Agent 区分日志路径。
- 禁止自动从远程拉取或更新 Agent 代码，所有变更需人工审核后部署。

---

## 安全红线

1. **不自动执行危险命令**：`rm -rf`、`format`、`fdisk`、`regedit` 等默认禁止。
2. **不自动自愈**：任何修复动作需人工确认。
3. **不自动外发**：Agent 不得自动发起外部网络请求。
4. **最小权限**：Agent 只能访问其 `cwd` 与明确授权的路径。
5. **审计优先**：任何异常或权限变更必须留下不可篡改的日志。

---

*文档版本：Phase3-v1.1*
