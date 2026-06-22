#!/usr/bin/env python3
"""OpenClaw Executor — 任务执行调度器。

生成执行 prompt 并写入 dispatch 目录，供主控（OpenClaw 主会话）
通过 sessions_spawn 派发子 Agent 执行。

执行流程:
  1. openclaw_executor 生成 prompt 文件到 tasks/dispatch/Task-XXX-prompt.txt
  2. 将任务状态更新为 in_progress
  3. 写审计日志
  4. 主控检测到 in_progress + prompt 文件，用 sessions_spawn 派子 Agent
  5. 子 Agent 读取 prompt 文件执行，结果写回 tasks/dispatch/Task-XXX-result.txt
  6. openclaw_executor --collect 读取结果文件，更新任务状态为 done/failed

用法:
  # 生成执行 prompt（主控调用）
  python scripts/openclaw_executor.py --task-id Task-XXX

  # dry-run 模式
  python scripts/openclaw_executor.py --task-id Task-XXX --dry-run

  # 收集执行结果（子 Agent 完成后调用）
  python scripts/openclaw_executor.py --task-id Task-XXX --collect

  # 直接执行（调用 openclaw agent CLI，需要独立 session）
  python scripts/openclaw_executor.py --task-id Task-XXX --direct --timeout 120
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
from shutil import which
from typing import Any, Dict, Optional

# ── 路径常量 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 导入文件锁
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from file_lock import file_lock  # type: ignore

TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
POLICIES_FILE = PROJECT_ROOT / "config" / "policies.json"
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"
DISPATCH_DIR = PROJECT_ROOT / "tasks" / "dispatch"

# ── 编码安全 ──────────────────────────────────────────────
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _utf8_print(msg: str) -> None:
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

def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_task(data: Dict[str, Any], task_id: str) -> Optional[Dict[str, Any]]:
    for t in data.get("tasks", []):
        if t.get("id") == task_id:
            return t
    return None


def find_agent(agents_data: Dict[str, Any], agent_id: str) -> Optional[Dict[str, Any]]:
    for a in agents_data.get("agents", []):
        if a.get("id") == agent_id:
            return a
    return None


def get_policy_value(policies: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(policies.get("policies", {}).get("execution", {})
                    .get(key, {}).get("value", default))
    except (ValueError, TypeError):
        return default


# ── 审计日志 ──────────────────────────────────────────────

def write_audit(event_type: str, task_id: str, details: str,
                environment: str = "production") -> None:
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
    parts = []
    parts.append(f"任务 ID: {task.get('id', 'unknown')}")
    parts.append(f"任务标题: {task.get('title', '')}")
    notes = task.get("notes", "")
    if notes:
        parts.append(f"任务说明: {notes}")
    parts.append("")
    parts.append("请在项目目录下执行上述任务，给出详细的执行过程和结果。")
    return "\n".join(parts)


# ── Dispatch 文件 ─────────────────────────────────────────

def write_prompt_file(task_id: str, prompt: str) -> Path:
    DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    prompt_file = DISPATCH_DIR / f"{task_id}-prompt.txt"
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    return prompt_file


def read_result_file(task_id: str) -> Optional[str]:
    result_file = DISPATCH_DIR / f"{task_id}-result.txt"
    if result_file.exists():
        with open(result_file, "r", encoding="utf-8") as f:
            return f.read()
    return None


def write_result_file(task_id: str, result: str) -> Path:
    DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    result_file = DISPATCH_DIR / f"{task_id}-result.txt"
    with open(result_file, "w", encoding="utf-8") as f:
        f.write(result)
    return result_file


# ── 直接执行模式（openclaw agent CLI）────────────────────

def execute_direct(prompt: str, timeout: int, max_output_kb: int) -> Dict[str, Any]:
    """调用 openclaw agent CLI 执行任务。"""
    openclaw_cmd = "openclaw"
    for candidate in ["openclaw.cmd", "openclaw"]:
        if which(candidate):
            openclaw_cmd = candidate
            break

    session_key = f"agent:main:executor:{int(time.time())}"
    cmd = [openclaw_cmd, "agent", "--agent", "main",
           "--session-key", session_key,
           "--message", prompt, "--json"]

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
        return {"success": False, "output": "", "error": "openclaw 命令未找到"}
    except Exception as e:
        return {"success": False, "output": "", "error": f"调用异常: {e}"}

    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

    max_bytes = max_output_kb * 1024
    if len(stdout.encode("utf-8")) > max_bytes:
        stdout = stdout.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")
        stdout += "\n... [输出已截断]"

    parsed_output = stdout
    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, dict):
            for key in ("response", "message", "content", "reply"):
                if key in parsed and isinstance(parsed[key], str):
                    parsed_output = parsed[key]
                    break
            else:
                parsed_output = json.dumps(parsed, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, ValueError):
        pass

    success = result.returncode == 0
    error_msg = stderr.strip() if not success and stderr else ""
    return {"success": success, "output": parsed_output, "error": error_msg}


# ── 主流程 ────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="OpenClaw Executor — 任务执行调度器"
    )
    parser.add_argument("--task-id", required=True, help="要执行的任务 ID (如 Task-001)")
    parser.add_argument("--dry-run", action="store_true", help="只打印命令，不真实执行")
    parser.add_argument("--direct", action="store_true",
                        help="直接调用 openclaw agent CLI 执行（重量级，可能较慢）")
    parser.add_argument("--collect", action="store_true",
                        help="收集执行结果文件并更新任务状态")
    parser.add_argument("--timeout", type=int, default=None,
                        help="超时秒数（--direct 模式，默认从 policies.json 读取）")
    args = parser.parse_args()

    # ── 读取任务（加共享锁） ──
    try:
        with file_lock(str(TASKS_FILE), mode='shared'):
            tasks_data = load_json(TASKS_FILE)
            task = find_task(tasks_data, args.task_id)
    except TimeoutError as e:
        _utf8_print(f"[ERROR] 获取文件锁超时: {e}")
        return 1

    if not task:
        _utf8_print(f"[ERROR] 任务 {args.task_id} 不存在")
        return 1

    # ── collect 模式：收集结果 ──
    if args.collect:
        _utf8_print(f"[INFO] 收集 {args.task_id} 执行结果...")
        result_text = read_result_file(args.task_id)
        if result_text is None:
            _utf8_print(f"[ERROR] 未找到结果文件 tasks/dispatch/{args.task_id}-result.txt")
            return 1

        # 判断成功/失败
        is_success = not result_text.startswith("[EXECUTION FAILED]")

        # read-modify-write 原子操作，加排他锁
        try:
            with file_lock(str(TASKS_FILE), mode='exclusive'):
                # 重新加载最新数据
                tasks_data = load_json(TASKS_FILE)
                task = find_task(tasks_data, args.task_id)
                if not task:
                    _utf8_print(f"[ERROR] 任务 {args.task_id} 不存在（重载后）")
                    return 1
                task["output"] = result_text[:1024 * 1024]
                task["status"] = "done" if is_success else "failed"
                task["updatedAt"] = _now_iso()
                save_json(TASKS_FILE, tasks_data)
        except TimeoutError as e:
            _utf8_print(f"[ERROR] 获取文件锁超时: {e}")
            return 1

        event = "openclaw_executor_success" if is_success else "openclaw_executor_failed"
        write_audit(event, args.task_id, f"collect, output={len(result_text)}字符")
        _utf8_print(f"[OK] 任务已标记 {'done' if is_success else 'failed'}，审计日志已记录")
        return 0 if is_success else 1

    # ── 读取 Agent + 策略 ──
    assignee = task.get("assignee")
    agent = None
    if assignee:
        agents_data = load_json(AGENTS_FILE)
        agent = find_agent(agents_data, assignee)
        if agent:
            _utf8_print(f"[INFO] 指派 Agent: {assignee} (cwd={agent.get('cwd', 'N/A')})")

    policies = load_json(POLICIES_FILE)
    timeout = args.timeout or get_policy_value(policies, "maxRuntimeMinutes", 30) * 60
    max_output_kb = get_policy_value(policies, "maxOutputKB", 1024)

    prompt = build_prompt(task, agent)
    _utf8_print(f"[INFO] 构建 prompt ({len(prompt)} 字符)")

    # ── dry-run ──
    if args.dry_run:
        _utf8_print("")
        _utf8_print("[DRY-RUN] Prompt 内容:")
        _utf8_print("=" * 50)
        for line in prompt.split("\n"):
            _utf8_print(line)
        _utf8_print("=" * 50)
        if args.direct:
            _utf8_print(f"[DRY-RUN] 将调用: openclaw agent --agent main --session-key <auto> --json")
            _utf8_print(f"  超时: {timeout}s")
        else:
            _utf8_print(f"[DRY-RUN] 将生成 prompt 文件到 tasks/dispatch/{args.task_id}-prompt.txt")
            _utf8_print(f"  主控检测到 prompt 文件后用 sessions_spawn 派子 Agent 执行")
        write_audit("openclaw_executor_dry_run", args.task_id,
                    f"dry-run, mode={'direct' if args.direct else 'dispatch'}, prompt={len(prompt)}字符")
        _utf8_print("[OK] dry-run 完成")
        return 0

    # ── direct 模式：直接调用 CLI ──
    if args.direct:
        _utf8_print(f"[INFO] 直接调用 OpenClaw Agent (timeout={timeout}s)...")
        write_audit("openclaw_executor_start", args.task_id,
                    f"direct mode, timeout={timeout}s")
        start = time.time()
        result = execute_direct(prompt, timeout, max_output_kb)
        elapsed = time.time() - start

        if result["success"]:
            _utf8_print(f"[OK] 执行完成 ({elapsed:.1f}s)")
            # read-modify-write 原子操作，加排他锁
            try:
                with file_lock(str(TASKS_FILE), mode='exclusive'):
                    tasks_data = load_json(TASKS_FILE)
                    task = find_task(tasks_data, args.task_id)
                    if not task:
                        _utf8_print(f"[ERROR] 任务 {args.task_id} 不存在（重载后）")
                        return 1
                    task["output"] = result["output"]
                    task["status"] = "done"
                    task["updatedAt"] = _now_iso()
                    task["notes"] = (task.get("notes", "") +
                                     f"\n[OpenClaw Executor] direct 执行成功 ({elapsed:.1f}s)").strip()
                    save_json(TASKS_FILE, tasks_data)
            except TimeoutError as e:
                _utf8_print(f"[ERROR] 获取文件锁超时: {e}")
                return 1
            write_audit("openclaw_executor_success", args.task_id,
                        f"direct, 耗时={elapsed:.1f}s, 输出={len(result['output'])}字符")
            _utf8_print("[OK] 任务已标记 done")
            preview = result["output"][:500]
            _utf8_print("")
            _utf8_print("[OUTPUT PREVIEW]")
            _utf8_print(preview)
            return 0
        else:
            _utf8_print(f"[FAIL] 执行失败 ({elapsed:.1f}s): {result['error']}")
            # read-modify-write 原子操作，加排他锁
            try:
                with file_lock(str(TASKS_FILE), mode='exclusive'):
                    tasks_data = load_json(TASKS_FILE)
                    task = find_task(tasks_data, args.task_id)
                    if not task:
                        _utf8_print(f"[ERROR] 任务 {args.task_id} 不存在（重载后）")
                        return 1
                    task["status"] = "failed"
                    task["updatedAt"] = _now_iso()
                    task["notes"] = (task.get("notes", "") +
                                     f"\n[OpenClaw Executor] direct 执行失败: {result['error']}").strip()
                    save_json(TASKS_FILE, tasks_data)
            except TimeoutError as e:
                _utf8_print(f"[ERROR] 获取文件锁超时: {e}")
                return 1
            write_audit("openclaw_executor_failed", args.task_id,
                        f"direct, 耗时={elapsed:.1f}s, 错误={result['error'][:200]}")
            return 1

    # ── dispatch 模式（默认）：生成 prompt 文件 + 更新任务状态 ──
    _utf8_print(f"[INFO] 生成执行 prompt 文件...")
    prompt_file = write_prompt_file(args.task_id, prompt)

    # read-modify-write 原子操作，加排他锁
    try:
        with file_lock(str(TASKS_FILE), mode='exclusive'):
            tasks_data = load_json(TASKS_FILE)
            task = find_task(tasks_data, args.task_id)
            if not task:
                _utf8_print(f"[ERROR] 任务 {args.task_id} 不存在（重载后）")
                return 1
            task["status"] = "in_progress"
            task["updatedAt"] = _now_iso()
            save_json(TASKS_FILE, tasks_data)
    except TimeoutError as e:
        _utf8_print(f"[ERROR] 获取文件锁超时: {e}")
        return 1

    write_audit("openclaw_executor_start", args.task_id,
                f"dispatch mode, prompt_file={prompt_file.name}")

    _utf8_print(f"[OK] Prompt 文件已生成: {prompt_file}")
    _utf8_print(f"[OK] 任务已标记 in_progress")
    _utf8_print(f"[INFO] 主控检测到 prompt 文件后，用 sessions_spawn 派子 Agent 执行")
    _utf8_print(f"[INFO] 子 Agent 完成后，将结果写入 tasks/dispatch/{args.task_id}-result.txt")
    _utf8_print(f"[INFO] 然后运行: python scripts/openclaw_executor.py --task-id {args.task_id} --collect")
    return 0


if __name__ == "__main__":
    sys.exit(main())
