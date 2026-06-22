# ACCEPTANCE_CONFIG_SNAPSHOT.md — 配置快照模块验收

> 验收时间：2026-06-22
> 验收对象：`scripts/snapshot_config.py`
> 验收人：胖小（主控/项目管理）

## 1. 验收范围

| 功能 | 状态 |
|------|------|
| `save` 保存快照 | ✅ |
| `list` 列出快照 | ✅ |
| `show` 查看快照详情 | ✅ |
| `restore` 恢复快照 | ✅ |
| 恢复前自动 pre-restore 备份 | ✅ |
| 写入审计日志 | ✅ |
| `--json` 机器可解析输出 | ✅ |
| `--yes` 跳过确认提示 | ✅ |

## 2. 验证过程

### 2.1 保存快照

```bash
python scripts/snapshot_config.py save --name test-verify --reason "Block 3C verification test"
```

**结果**：[OK] 快照已保存: `snapshots/test-verify`

**快照内容**：
- config/agents.json
- config/policies.json
- config/.round_robin_state
- tasks/tasks.json
- README.md
- PROJECT_PLAN.md
- docs/OPERATOR_RUNBOOK.md
- docs/SECURITY_NOTES.md
- docs/TASK_PROTOCOL.md
- state/system_state.json

### 2.2 列出快照

```bash
python scripts/snapshot_config.py list
```

**结果**：
- baseline-old-scheme | 2026-06-20T10:38:07 | 旧方案基线
- test-verify | 2026-06-22T01:38:55 | Block 3C verification test

### 2.3 查看快照详情

```bash
python scripts/snapshot_config.py show --name test-verify
```

**结果**：输出 schemaVersion / name / createdAt / reason / copied / missing / restorePaths，结构正确。

### 2.4 恢复快照

```bash
python scripts/snapshot_config.py restore --name test-verify --yes
```

**结果**：
- [OK] 已恢复快照: test-verify
- [OK] 恢复前自动备份: pre-restore-20260622-013926

### 2.5 JSON 输出

```bash
python scripts/snapshot_config.py show --name test-verify --json
```

**结果**：输出合法 JSON，`json.loads` 可解析。

### 2.6 清理

测试快照 `test-verify` 和 `pre-restore-20260622-013926` 已清理，仅保留基线 `baseline-old-scheme`。

## 3. 安全性检查

| 检查项 | 结果 |
|--------|------|
| 恢复前是否自动创建 pre-restore 备份 | ✅ 是 |
| 是否写入审计日志 | ✅ 是 |
| 恢复操作是否需要 `--yes` 确认 | ✅ 是 |
| 快照目录是否在 .gitignore 中排除 | ✅ 是（snapshots/ 已在 .gitignore） |

## 4. 已知限制

- 快照不包含 `logs/` 目录（审计日志/消息日志不回滚）
- 快照不包含 `scripts/` 目录（代码版本由 Git 管理）
- 恢复操作会覆盖 config/tasks/state 中的文件，但不会删除新增文件
- 无定时自动快照（可通过 OpenClaw cron 实现）

## 5. 验收结论

**PASS** — 配置快照模块功能完整、安全约束到位，可正式投入运维使用。
