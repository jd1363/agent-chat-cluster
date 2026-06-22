# 验收文档：成本/Token 估算台账 (ACCEPTANCE_COST_LEDGER.md)

> 验收时间：2026-06-22
> 验收人：胖小（主控）
> 对应脚本：`scripts/record_cost.py` + `scripts/show_cost.py`

## 一、验收范围

原始方案中 `/usage` 系列命令的安全替代第一版：
- 手动/半自动记录成本估算
- 按 Agent/任务汇总
- 预算阈值提示（不自动暂停）

## 二、功能清单与验证结果

| # | 功能 | 验证命令 | 结果 |
|---|------|---------|------|
| 1 | 手动记录成本 | `record_cost.py --agent-id agent-ext-01 --task-id Task-010 --input-tokens 1200 --output-tokens 800 --estimated-cost 0.03` | ✅ PASS |
| 2 | 估算模式（dry-run） | `record_cost.py --agent-id agent-ext-01 --input-tokens 1000 --output-tokens 500 --rate-input-per-1k 0.002 --rate-output-per-1k 0.006 --dry-run` | ✅ PASS |
| 3 | 按 Agent 汇总 | `show_cost.py --by-agent` | ✅ PASS |
| 4 | 按任务汇总 | `show_cost.py --by-task` | ✅ PASS |
| 5 | JSON 输出 | `show_cost.py --json --by-agent` | ✅ PASS（`ensure_ascii=True`，UTF-8 稳定） |
| 6 | 预算阈值提示 | `show_cost.py --agent-id agent-ext-01 --budget 5` | ✅ PASS（显示 0.03/5.00，预算内） |
| 7 | 明细列表 | `show_cost.py`（默认） | ✅ PASS |
| 8 | JSONL 存储 | `logs/cost/2026-06-22.jsonl` | ✅ PASS（UTF-8，追加写入） |

## 三、已知限制

1. **不自动暂停 Agent**：出于安全考虑，预算超限只提示不自动暂停
2. **不承诺精确账单**：成本为手动估算或速率计算，非真实 API 账单
3. **无 CSV 导出**：当前只支持 JSON 输出，未实现 CSV 格式
4. **无自动日报/周报**：需手动调用 `show_cost.py` 查看

## 四、安全边界

- 不自动暂停 Agent（`policies.json` 未授权 `auto-pause`）
- 不自动采集 API 账单（需人工录入或脚本对接）
- 不发送外部网络请求

## 五、结论

**PASS** — 成本/Token 估算台账功能完整，作为 `/usage` 安全替代第一版可接受。

## 六、后续建议

- 可考虑增加 CSV 导出（`--format csv`）
- 可考虑通过 OpenClaw `cron` 定时生成成本日报
- 真实 API 账单对接需确认 OpenClaw 是否暴露 token 统计接口
