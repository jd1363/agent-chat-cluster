#!/usr/bin/env python3
"""OpenClaw Executor — 通过 OpenClaw CLI 真实派工执行任务。

封装 `openclaw agent --message "PROMPT" --json` 调用，
将任务从 tasks.json 读取、构建 prompt、调用 OpenClaw 执行、
写回结果到任务台账并记录审计日志。

用法:
  python scripts/openclaw_executor.py --task-id Task-XXX
  python scripts/openclaw_executor.py --task-id Task-XXX --dry-run
  python scripts/openclaw_executor.py --task-id Task-XXX --timeout 600
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# ── 路径常量 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
POLICIES_FILE = PROJECT_ROOT / "config" / "policies.json"
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"
DISPATCH_DIR = PROJECT_ROOT / "tasks" / "dispatch"

# ── 编码安全 ──────────────────────────────────────────────
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _utf8_print(msg: str) -> None:
    """安全打印，避免 Windows GBK 崩溃。"""
    try:
        sys.stdout.buffer.write((msg + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
    except Exception:
        print(msg)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── 数据读取 ──────────────────────────────────────────────

def load_tasks() -> Dict[str, Any]:
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tasks(data: Dict[str, Any]) -> None:
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_task(data: Dict[str, Any], task_id: str) -> Optional[Dict[str, Any]]:
    for t in data.get("tasks", []):
        if t.get("id") == task_id:
            return t
    return None


def load_agents() -> Dict[str, Any]:
    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def find_agent(agents_data: Dict[str, Any], agent_id: str) -> Optional[Dict[str, Any]]:
    for a in agents_data.get("agents", []):
        if a.get("id") == agent_id:
            return a
    return None


def load_policies() -> Dict[str, Any]:
    with open(POLICIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_max_runtime_minutes(policies: Dict[str, Any]) -> int:
    try:
        return int(policies.get("policies", {}).get("execution", {})
                    .get("maxRuntimeMinutes", {}).get("value", 30))
    except (ValueError, TypeError):
        return 30


def get_max_output_kb(policies: Dict[str, Any]) -> int:
    try:
        return int(policies.get("policies", {}).get("execution", {})
                    .get("maxOutputKB", {}).get("value", 1024))
    except (ValueError, TypeError):
        return 1024


# ── 审计日志 ──────────────────────────────────────────────

def write_audit(event_type: str, task_id: str, details: str,
                environment: str = "production") -> None:
    """追加审计日志到 logs/audit/YYYY-MM-DD.jsonl"""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": _now_iso(),
        "eventType": event_type,
        "taskId": task_id,
        "details": details,
        "environment": environment,
    }
    log_file = AUDIT_DIR / f"{_today_str()}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Prompt 构建 ───────────────────────────────────────────

def build_prompt(task: Dict[str, Any], agent: Optional[Dict[str, Any]]) -> str:
    """从任务详情构建给 OpenClaw 的执行 prompt。"""
    parts = []
    parts.append(f"任务 ID: {task.get('id', 'unknown')}")
    parts.append(f"任务标题: {task.get('title', '')}")

    notes = task.get("notes", "")
    if notes:
        parts.append(f"任务说明: {notes}")

    parts.append("")
    parts.append("请在项目目录下执行上述任务，给出详细的执行过程和结果。")

    return "\n".join(parts)


# ── 执行 ──────────────────────────────────────────────────

def execute_openclaw(prompt: str, timeout: int, max_output_kb: int) -> Dict[str, Any]:
    """调用 openclaw agent --message PROMPT --json 执行任务。

    返回:
      {"success": bool, "output": str, "error": str}
    """
    cmd = ["openclaw", "agent", "--message", prompt, "--json"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": f"OpenClaw 执行超时 (>{timeout}s)"}
    except FileNotFoundError:
        return {"success": False, "output": "", "error": "openclaw 命令未找到，请确认已安装并在 PATH 中"}
    except Exception as e:
        return {"success": False, "output": "", "error": f"调用异常: {e}"}

    # 解析输出
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

    # 截断输出
    max_bytes = max_output_kb * 1024
    if len(stdout.encode("utf-8")) > max_bytes:
        stdout = stdout.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")
        stdout += "\n... [输出已截断]"

    # openclaw agent --json 返回 JSON，尝试解析
    parsed_output = stdout
    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, dict):
            parsed_output = parsed.get("response", parsed.get("message", parsed.get("content", stdout)))
            if not isinstance(parsed_output, str):
                parsed_output = json.dumps(parsed, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, ValueError):
        pass  # 不是 JSON，直接用原始输出

    success = result.returncode == 0
    error_msg = stderr.strip() if not success and stderr else ""

    return {"success": success, "output": parsed_output, "error": error_msg}


# ── 主流程 ────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="OpenClaw Executor — 通过 OpenClaw CLI 真实派工执行任务"
    )
    parser.add_argument("--task-id", required=True, help="要执行的任务 ID (如 Task-001)")
    parser.add_argument("--dry-run", action="store_true", help="只打印命令，不真实执行")
    parser.add_argument("--timeout", type=int, default=None,
                        help="超时秒数（默认从 policies.json 读取）")
    args = parser.parse_args()

    # ── 1. 读取任务 ──
    _utf8_print(f"[INFO] 读取任务 {args.task_id}...")
    tasks_data = load_tasks()
    task = find_task(tasks_data, args.task_id)
    if not task:
        _utf8_print(f"[ERROR] 任务 {args.task_id} 不存在")
        return 1

    _utf8_print(f"[OK] 任务标题: {task.get('title', '')}")

    # ── 2. 读取 Agent 信息 ──
    assignee = task.get("assignee")
    agent = None
    if assignee:
        agents_data = load_agents()
        agent = find_agent(agents_data, assignee)
        if agent:
            _utf8_print(f"[INFO] 指派 Agent: {assignee} (cwd={agent.get('cwd', 'N/A')})")
        else:
            _utf8_print(f"[WARN] Agent {assignee} 未在注册表中找到")
    else:
        _utf8_print("[INFO] 任务未指派 Agent，将使用默认 OpenClaw Agent")

    # ── 3. 读取策略 ──
    policies = load_policies()
    timeout = args.timeout or get_max_runtime_minutes(policies) * 60
    max_output_kb = get_max_output_kb(policies)
    _utf8_print(f"[INFO] 超时: {timeout}s  输出上限: {max_output_kb}KB")

    # ── 4. 构建 prompt ──
    prompt = build_prompt(task, agent)
    _utf8_print(f"[INFO] 构建 prompt ({len(prompt)} 字符)")

    # ── 5. dry-run 或真实执行 ──
    if args.dry_run:
        _utf8_print("")
        _utf8_print("[DRY-RUN] 以下是将要执行的命令：")
        _utf8_print(f"  命令: openclaw agent --message \"<prompt>\" --json")
        _utf8_print(f"  超时: {timeout}s")
        _utf8_print(f"  Prompt 内容:")
        _utf8_print("  " + "=" * 50)
        for line in prompt.split("\n"):
            _utf8_print("  " + line)
        _utf8_print("  " + "=" * 50)
        _utf8_print("[DRY-RUN] 未执行 OpenClaw，未修改任务状态。")
        write_audit("openclaw_executor_dry_run", args.task_id,
                     f"dry-run, prompt={len(prompt)}字符")
        _utf8_print("[OK] dry-run 完成，审计日志已记录")
        return 0

    # ── 6. 真实执行 ──
    _utf8_print(f"[INFO] 开始调用 OpenClaw Agent...")
    write_audit("openclaw_executor_start", args.task_id,
                f"assignee={assignee or 'default'}, timeout={timeout}s")

    start_time = time.time()
    result = execute_openclaw(prompt, timeout, max_output_kb)
    elapsed = time.time() - start_time

    if result["success"]:
        _utf8_print(f"[OK] OpenClaw 执行完成 ({elapsed:.1f}s)")
        _utf8_print(f"[INFO] 输出长度: {len(result['output'])} 字符")

        # 写回任务
        task["output"] = result["output"][:max_output_kb * 1024]
        task["status"] = "done"
        task["updatedAt"] = _now_iso()
        task["notes"] = (task.get("notes", "") + f"\n[OpenClaw Executor] 执行成功 ({elapsed:.1f}s)").strip()
        save_tasks(tasks_data)

        write_audit("openclaw_executor_success", args.task_id,
                    f"耗时={elapsed:.1f}s, 输出={len(result['output'])}字符")
        _utf8_print("[OK] 任务已标记 done，审计日志已记录")

        # 打印输出预览
        preview = result["output"][:500]
        _utf8_print("")
        _utf8_print("[OUTPUT PREVIEW]")
        _utf8_print(preview)
        if len(result["output"]) > 500:
            _utf8_print("... [仅显示前 500 字符]")

        return 0
    else:
        _utf8_print(f"[FAIL] OpenClaw 执行失败 ({elapsed:.1f}s)")
        _utf8_print(f"[ERROR] {result['error']}")

        task["status"] = "failed"
        task["updatedAt"] = _now_iso()
        task["notes"] = (task.get("notes", "") + f"\n[OpenClaw Executor] 执行失败: {result['error']}").strip()
        save_tasks(tasks_data)

        write_audit("openclaw_executor_failed", args.task_id,
                    f"耗时={elapsed:.1f}s, 错误={result['error'][:200]}")
        _utf8_print("[OK] 任务已标记 failed，审计日志已记录")
        return 1


if __name__ == "__main__":
    sys.exit(main())
