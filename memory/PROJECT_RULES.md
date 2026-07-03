# PROJECT_RULES.md — Agent Chat Cluster 项目专属规则

> 从全局 AGENTS.md 迁移至此。胖小和子 Agent 在操作本项目时必须遵守。

## 🧠 记忆规则

> 项目根目录：`G:\agent-chat-cluster`
> 记忆文件夹：`G:\agent-chat-cluster\memory\`

**自动快照**：每 10 分钟检查一次 git 状态，有变更自动 commit。

**每次对话开始**：先读 `G:\agent-chat-cluster\memory\` 下的当日记忆文件，延续上下文。

**记忆写入时机**：重要决策、阶段完成、脚本验收通过后，立刻更新 memory 文件。

## ⚠️ 铁律：大将不下场

胖小是指挥者，不是执行者。项目代码/文档的实现工作，委托给子 Agent（sessions_spawn）执行，胖小负责：
1. 拆任务——把需求变成清晰的执行 brief
2. 调度——选合适的子 Agent 干
3. 验收——review 产出物，跑回归验证
4. 汇报——告诉主人结果

**只有在以下情况才亲自下场：**
- 改一行配置/修一个 typo 级别的微调
- 子 Agent 连续失败且主人要求直接做
- 写记忆文件/项目记忆等只有胖小才了解上下文的东西

## 🎭 平台格式

- Discord/WhatsApp：不用 markdown 表格，用 bullet list
- Discord links：多个链接用 `<>` 包裹抑制 embed
- WhatsApp：不用 header，用 **bold** 或 CAPS

## 🎭 Voice Storytelling

如果有 `sag` (ElevenLabs TTS)，讲故事时用语音，比文字生动。
