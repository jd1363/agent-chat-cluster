#!/usr/bin/env python3
"""
check_alerts.py — 多维度只读告警检查

第一版：只读扫描系统状态/日志，输出告警摘要，不做任何自动修复。
检查维度：
  1. failed 任务数量
  2. 任务超时（in_progress 超过 maxRuntimeMinutes）
  3. Agent 禁用状态检查
  4. 审计日志异常事件（task_failed / force_override）
  5. 消息未 ACK 堆积
  6. 成本超预算提示
  7. 磁盘日志体积

CLI:
  python scripts/check_alerts.py
  python scripts/check_alerts.py --json
  python scripts/check_alerts.py --severity warning
  python scripts/check_alerts.py --quiet   # 只输出 warning+critical

退出码：
  0 = 无告警或有 info 告警
  1 = 有 warning 告警
  2 = 有 critical 告警
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── 路径定位 ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
POLICIES_FILE = PROJECT_ROOT / "config" / "policies.json"
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"
MESSAGES_DIR = PROJECT_ROOT / "logs" / "messages"
COST_DIR = PROJECT_ROOT / "logs" / "cost"
LOGS_DIR = PROJECT_ROOT / "logs"

# ── 辅助函数 ──────────────────────────────────────────────

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _parse_iso(ts):
    """解析 ISO 时间戳，返回 epoch 秒；失败返回 None。"""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None

def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _read_jsonl(path):
    """读取 JSONL 文件，跳过坏行。"""
    results = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return results

def _dir_size_mb(path):
    """递归计算目录大小（MB）。"""
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except Exception:
        pass
    return round(total / (1024 * 1024), 2)

# ── 告警类 ────────────────────────────────────────────────

class Alert:
    def __init__(self, severity, category, message, detail=None):
        self.severity = severity  # info / warning / critical
        self.category = category
        self.message = message
        self.detail = detail or {}

    def to_dict(self):
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "detail": self.detail,
        }

    def __str__(self):
        tag = {"info": "[INFO]", "warning": "[WARN]", "critical": "[CRIT]"}[self.severity]
        return f"{tag} {self.category}: {self.message}"

# ── 检查器 ────────────────────────────────────────────────

def check_failed_tasks(tasks_data, _policies, _now):
    alerts = []
    tasks = tasks_data.get("tasks", []) if tasks_data else []
    failed = [t for t in tasks if t.get("status") == "failed"]
    if failed:
        sev = "critical" if len(failed) >= 3 else "warning"
        alerts.append(Alert(
            severity=sev,
            category="task",
            message=f"{len(failed)} 个任务状态为 failed",
            detail={"taskIds": [t["id"] for t in failed]}
        ))
    return alerts

def check_task_timeout(tasks_data, policies, now):
    alerts = []
    if not tasks_data or not policies:
        return alerts
    tasks = tasks_data.get("tasks", [])
    exec_p = policies.get("policies", {}).get("execution", {})
    max_minutes = exec_p.get("maxRuntimeMinutes", {}).get("value", 30)
    in_progress = [t for t in tasks if t.get("status") == "in_progress"]
    for t in in_progress:
        updated = _parse_iso(t.get("updatedAt") or t.get("createdAt"))
        if updated and (now - updated) > max_minutes * 60:
            elapsed = round((now - updated) / 60, 1)
            alerts.append(Alert(
                severity="warning",
                category="task_timeout",
                message=f"任务 {t['id']} 处于 in_progress 已 {elapsed} 分钟（上限 {max_minutes} 分钟）",
                detail={"taskId": t["id"], "elapsedMinutes": elapsed, "maxMinutes": max_minutes}
            ))
    return alerts

def check_disabled_agents(_tasks_data, _policies, _now):
    alerts = []
    agents_data = _load_json(AGENTS_FILE)
    if not agents_data:
        alerts.append(Alert("warning", "config", "无法读取 config/agents.json"))
        return alerts
    agents = agents_data.get("agents", [])
    enabled = [a for a in agents if a.get("enabled")]
    disabled = [a for a in agents if not a.get("enabled")]
    if len(enabled) == 0:
        alerts.append(Alert(
            severity="critical",
            category="agent",
            message="没有任何启用的 Agent，系统无法派工"
        ))
    elif len(enabled) == 1:
        alerts.append(Alert(
            severity="info",
            category="agent",
            message=f"仅 1 个 Agent 启用（{enabled[0]['id']}），无冗余",
            detail={"enabledCount": len(enabled), "disabledCount": len(disabled)}
        ))
    if disabled:
        alerts.append(Alert(
            severity="info",
            category="agent",
            message=f"{len(disabled)} 个 Agent 处于禁用状态: {', '.join(a['id'] for a in disabled)}",
            detail={"disabledIds": [a["id"] for a in disabled]}
        ))
    return alerts

def check_audit_anomalies(_tasks_data, _policies, _now):
    alerts = []
    if not AUDIT_DIR.exists():
        return alerts
    # 扫描最近 3 天的审计日志
    cutoff = now_ts = _now - (3 * 24 * 3600)
    anomaly_types = {"task_failed", "force_override", "dispatch_blocked", "broadcast_blocked"}
    found = []
    for af in sorted(AUDIT_DIR.glob("*.jsonl"), reverse=True)[:3]:
        entries = _read_jsonl(af)
        for e in entries:
            ts = _parse_iso(e.get("timestamp"))
            if ts and ts >= cutoff and e.get("eventType") in anomaly_types:
                found.append(e)
    if found:
        sev = "warning" if len(found) >= 3 else "info"
        alerts.append(Alert(
            severity=sev,
            category="audit",
            message=f"最近 3 天有 {len(found)} 条异常审计事件",
            detail={"eventTypes": list({e["eventType"] for e in found}),
                    "count": len(found)}
        ))
    return alerts

def check_unacked_messages(_tasks_data, _policies, _now):
    alerts = []
    if not MESSAGES_DIR.exists():
        return alerts
    unacked = 0
    for mf in MESSAGES_DIR.glob("*.jsonl"):
        entries = _read_jsonl(mf)
        for e in entries:
            if e.get("status") == "sent" and not e.get("readAt"):
                unacked += 1
    if unacked > 0:
        sev = "warning" if unacked >= 5 else "info"
        alerts.append(Alert(
            severity=sev,
            category="message",
            message=f"{unacked} 条消息未被 ACK",
            detail={"unackedCount": unacked}
        ))
    return alerts

def check_cost_budget(_tasks_data, _policies, _now):
    alerts = []
    if not COST_DIR.exists():
        return alerts
    total_cost = 0.0
    for cf in COST_DIR.glob("*.jsonl"):
        entries = _read_jsonl(cf)
        for e in entries:
            total_cost += float(e.get("estimatedCost", 0) or 0)
    # 从 policies 读取预算（如果有）
    # policies.json 目前没有 budget 字段，使用默认值
    default_budget = 50.0  # 默认预算 $50
    if total_cost > default_budget * 0.8:
        sev = "critical" if total_cost >= default_budget else "warning"
        alerts.append(Alert(
            severity=sev,
            category="cost",
            message=f"成本估算 ${total_cost:.2f}，接近预算 ${default_budget:.2f}",
            detail={"totalCost": round(total_cost, 4), "budget": default_budget,
                    "ratio": round(total_cost / default_budget, 4)}
        ))
    return alerts

def check_log_size(_tasks_data, _policies, _now):
    alerts = []
    if not LOGS_DIR.exists():
        return alerts
    size_mb = _dir_size_mb(LOGS_DIR)
    if size_mb > 500:
        alerts.append(Alert(
            severity="warning",
            category="disk",
            message=f"logs/ 目录体积 {size_mb} MB，超过 500 MB 阈值",
            detail={"sizeMB": size_mb, "thresholdMB": 500}
        ))
    elif size_mb > 100:
        alerts.append(Alert(
            severity="info",
            category="disk",
            message=f"logs/ 目录体积 {size_mb} MB",
            detail={"sizeMB": size_mb}
        ))
    return alerts

# ── 主流程 ────────────────────────────────────────────────

CHECKERS = [
    ("failed_tasks", check_failed_tasks),
    ("task_timeout", check_task_timeout),
    ("disabled_agents", check_disabled_agents),
    ("audit_anomalies", check_audit_anomalies),
    ("unacked_messages", check_unacked_messages),
    ("cost_budget", check_cost_budget),
    ("log_size", check_log_size),
]

def run_checks(severity_filter=None, quiet=False):
    tasks_data = _load_json(TASKS_FILE)
    policies = _load_json(POLICIES_FILE)
    now = time.time()

    all_alerts = []
    for _name, checker in CHECKERS:
        try:
            alerts = checker(tasks_data, policies, now)
            all_alerts.extend(alerts)
        except Exception as e:
            all_alerts.append(Alert(
                severity="warning",
                category="system",
                message=f"检查器 {_name} 执行异常: {type(e).__name__}: {e}"
            ))

    # 过滤
    if quiet:
        all_alerts = [a for a in all_alerts if a.severity in ("warning", "critical")]
    if severity_filter:
        all_alerts = [a for a in all_alerts if a.severity == severity_filter]

    # 排序：critical > warning > info
    order = {"critical": 0, "warning": 1, "info": 2}
    all_alerts.sort(key=lambda a: order.get(a.severity, 3))

    return all_alerts

def main():
    parser = argparse.ArgumentParser(description="多维度只读告警检查（不自动修复）")
    parser.add_argument("--json", action="store_true", help="输出纯 JSON")
    parser.add_argument("--severity", choices=["info", "warning", "critical"],
                        help="只显示指定级别告警")
    parser.add_argument("--quiet", action="store_true",
                        help="只显示 warning 和 critical")
    args = parser.parse_args()

    alerts = run_checks(severity_filter=args.severity, quiet=args.quiet)

    # 退出码
    max_sev = "info"
    for a in alerts:
        if a.severity == "critical":
            max_sev = "critical"
            break
        elif a.severity == "warning":
            max_sev = "warning"

    exit_code = {"info": 0, "warning": 1, "critical": 2}.get(max_sev, 0)

    if args.json:
        output = {
            "schemaVersion": "1.0",
            "generatedAt": _now_iso(),
            "totalAlerts": len(alerts),
            "maxSeverity": max_sev,
            "alerts": [a.to_dict() for a in alerts],
        }
        sys.stdout.buffer.write(json.dumps(output, ensure_ascii=False, indent=2).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    else:
        lines = []
        if not alerts:
            lines.append("[OK] no alerts, system status normal.")
        else:
            lines.append(f"Alert check results ({len(alerts)} alerts)")
            lines.append("=" * 60)
            for a in alerts:
                tag = {"info": "[INFO]", "warning": "[WARN]", "critical": "[CRIT]"}[a.severity]
                lines.append(f"{tag} {a.category}: {a.message}")
                if a.detail:
                    for k, v in a.detail.items():
                        lines.append(f"    {k}: {v}")
            lines.append("=" * 60)
            lines.append(f"Max severity: {max_sev}")
        sys.stdout.buffer.write("\n".join(lines).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
