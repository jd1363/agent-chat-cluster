# Skills 目录索引

> 位置：`G:\agent-chat-cluster\skills\`
> 所有 Agent（包括主控胖小和 5 个 CLI Agent）均可读取使用。

## 项目自有技能

| 技能 | 文件 | 用途 |
|------|------|------|
| **project-conventions** | `project-conventions/SKILL.md` | 项目编码规范、目录结构、文件锁、安全红线、API 端点 |
| **script-reference** | `script-reference/SKILL.md` | 所有 Python 脚本的用法参考（create/dispatch/execute/audit/cost） |
| **task-execution-guide** | `task-execution-guide/SKILL.md` | 子 Agent 接收任务后的行为规范、输出格式、完成标准 |
| **agent-orchestration** | `agent-orchestration/SKILL.md` | 多 Agent 协作编排：能力矩阵、任务分配策略、并发规则 |

## SkillHub 安装的可视化技能

| 技能 | 文件 | 用途 |
|------|------|------|
| **dashboard-design** | `dashboard-design/SKILL.md` | 冰蓝毛玻璃设计系统（CSS 令牌、材质、布局、图表选型） |
| **realtime-dashboard** | `realtime-dashboard/SKILL.md` | 实时仪表盘指南（SSE/WebSocket、React Hooks） |
| **data-charts-visualization** | `data-charts-visualization/SKILL.md` | 结构化数据图表生成（柱/折/饼/散点/雷达） |
| **chartjs** | `chartjs/SKILL.md` | Chart.js 前端图表技能 |
| **superdesign** | `superdesign/SKILL.md` | 专家级前端设计指南 |

## 使用方式

### 子 Agent（CLI Agent）
在 prompt 中加入提示：
```
项目技能文件在 G:\agent-chat-cluster\skills\ 目录下。
执行任务前请阅读 skills/task-execution-guide/SKILL.md 了解行为规范。
需要查脚本用法时看 skills/script-reference/SKILL.md。
需要了解项目规范时看 skills/project-conventions/SKILL.md。
```

### 主控 Agent（胖小）
直接读取需要的 SKILL.md 文件即可。

### 派子 Agent 时
在 `sessions_spawn` 的 task 中加入：
```
## 技能文件
执行前阅读 G:\agent-chat-cluster\skills\task-execution-guide\SKILL.md
```
