# 命令映射验收 (ACCEPTANCE_COMMAND_MAP.md)

> 验收时间：2026-06-22
> 验收对象：`scripts/command_map.py`、`docs/REAL_COMMANDS.md`

## 1. 验收范围

验证旧方案文档中的伪命令是否能被 `command_map.py` 正确映射到当前真实替代方式或标记为 forbidden/pending。

## 2. 验收清单

### 2.1 已替换命令（replaced）

| 旧命令 | 映射结果 | 验证 |
|--------|---------|------|
| `/task list` | `python scripts/list_tasks.py` | ✅ |
| `/task create` | `python scripts/create_task.py --title "..." --priority high/medium/low` | ✅ |
| `/task transfer` | `python scripts/update_task.py --id Task-XXX --assignee agent-ext-01` | ✅ |
| `/task stop` | `python scripts/update_task.py --status cancelled` | ✅ |
| `/audit enable` | `scripts/audit_log.py` 默认按需写入 | ✅ |
| `/audit export` | `python scripts/show_audit.py --json` | ✅ |
| `/snapshot save` | `python scripts/snapshot_config.py save --name NAME --reason "..."` | ✅ |
| `/snapshot list` | `python scripts/snapshot_config.py list` | ✅ |
| `/snapshot restore` | `python scripts/snapshot_config.py restore --name NAME --yes` | ✅ |

### 2.2 部分替换命令（partially_replaced）

| 旧命令 | 映射结果 | 验证 |
|--------|---------|------|
| `/usage export` | `python scripts/show_cost.py --json --by-agent / --by-task` | ✅ |
| `/usage report` | `python scripts/show_cost.py --by-agent / --by-task` | ✅ |
| `/permission set` | `python scripts/test_isolation.py` + `config/policies.json` allowedPaths | ✅ |

### 2.3 待实现命令（pending）

| 旧命令 | 映射结果 | 验证 |
|--------|---------|------|
| `/usage set-budget` | pending — 第一版仅支持 `record_cost.py` 与 `show_cost.py --budget` | ✅ |
| `/acp group start/stop/kill` | pending — 当前仅通过 `config/agents.json` enabled 字段管理 | ✅ |
| `/tag add` | pending — 未实现 | ✅ |
| `/alias add` | pending — 未实现 | ✅ |

### 2.4 禁止命令（forbidden）

| 旧命令 | 映射结果 | 验证 |
|--------|---------|------|
| `/self-heal` | forbidden — `policies.json` 明确禁用自动自愈 | ✅ |
| `openclaw --web` | forbidden_until_verified — 使用 `openclaw gateway status/start/restart` | ✅ |
| `/acp spawn` | forbidden_until_verified — 需先确认 OpenClaw 真实 ACP 创建方式 | ✅ |

### 2.5 受控命令（replaced_guarded）

| 旧命令 | 映射结果 | 验证 |
|--------|---------|------|
| `/acp broadcast` | `python scripts/broadcast.py --message "..." --manual-approval` | ✅ |
| `/acp group broadcast` | `python scripts/send_message.py --to all --manual-approval` | ✅ |

## 3. CLI 验证

```
python scripts/command_map.py --old "/task list"
python scripts/command_map.py --old "/usage set-budget agent codex 25" --json
python scripts/command_map.py --list
```

全部输出正确，退出码 0。

## 4. 结论

**PASS** — 旧方案伪命令映射器功能完整，所有命令类别（replaced / partially_replaced / pending / forbidden / replaced_guarded）均能正确映射并给出真实替代方式。未知命令默认返回 forbidden 提示。
