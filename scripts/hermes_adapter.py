#!/usr/bin/env python3
"""
hermes_adapter.py — Hermes Agent 适配器脚本

封装 Hermes CLI 调用，让 dispatch_task 可以通过本脚本把任务派发给
Hermes Agent 执行。

功能：
  1. 接受 --task-id Task-XXX 参数，从 tasks/tasks.json 读取任务详情
  2. 接受 --dry-run 参数，只打印将要执行的命令，不真正调用 Hermes
  3. 从任务的 title + notes 组合成 prompt 给 Hermes
  4. 调用 hermes chat -q "{prompt}" --quiet --max-turns 30
  5. 超时默认 1800 秒（30 分钟，与 policies.json maxRuntimeMinutes 一致）
  6. 捕获 stdout 作为执行结果
  7. 将结果写回任务的 output 字段（通过 update_task.py）
  8. 写审计日志（调用 audit_log.py 的 append_audit 函数）
  9. 退出码：0=成功，1=失败

用法:
    python scripts/hermes_adapter.py --task-id Task-001
    python scripts/hermes_adapter.py --task-id Task-001 --dry-run
    python scripts/hermes_adapter.py --task-id Task-001 --timeout 600

仅使用 Python 标准库，Python 3.8+ 兼容。
Windows 编码安全：所有 stdout/stderr 用 utf-8。
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 项目路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
POLICIES_FILE = PROJECT_ROOT / "config" / "policies.json"
UPDATE_TASK_SCRIPT = PROJECT_ROOT / "scripts" / "update_task.py"

# 导入审计日志模块
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from audit_log import append_audit  # type: ignore

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT_SECONDS = 1800  # 30 分钟，与 policies.json maxRuntimeMinutes 一致
HERMES_COMMAND = "hermes"
HERMES_ARGS_TEMPLATE = ["chat", "-q", "{prompt}", "--quiet", "--max-turns", "30"]
HERMES_WORK_DIR = r"G:\hermers\hermes-agent"
AGENT_ID = "agent-hermes-01"


# ---------------------------------------------------------------------------
# 编码安全：确保 stdout/stderr 使用 utf-8
# ---------------------------------------------------------------------------
def _ensure_utf8_streams():
    """在 Windows 上确保 stdout/stderr 使用 utf-8 编码。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


# ---------------------------------------------------------------------------
# 加载任务
# ---------------------------------------------------------------------------
def load_task(task_id: str) -> dict:
    """从 tasks/tasks.json 读取指定任务，返回任务字典。失败则 exit(1)。"""
    if not TASKS_FILE.is_file():
        print(f"[FAIL] 找不到文件: {TASKS_FILE}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"[FAIL] JSON 解析错误 (tasks.json): {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"[FAIL] 无法读取文件 (tasks.json): {e}", file=sys.stderr)
        sys.exit(1)

    tasks = data.get("tasks", [])
    if not isinstance(tasks, list):
        print("[FAIL] tasks.json: tasks 不是 list", file=sys.stderr)
        sys.exit(1)

    for task in tasks:
        if task.get("id") == task_id:
            return task

    print(f"[FAIL] 找不到任务: {task_id}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# 构建 prompt
# ---------------------------------------------------------------------------
def build_prompt(task: dict) -> str:
    """从任务的 title + notes 组合成给 Hermes 的指令。"""
    title = task.get("title", "")
    notes = task.get("notes", "")
    task_id = task.get("id", "")

    parts = []
    parts.append(f"任务 ID: {task_id}")
    parts.append(f"任务标题: {title}")
    if notes:
        parts.append(f"任务说明: {notes}")
    parts.append("")
    parts.append("请执行上述任务，给出详细的执行过程和结果。")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 从 policies.json 读取超时
# ---------------------------------------------------------------------------
def get_timeout_from_policies(default: int = DEFAULT_TIMEOUT_SECONDS) -> int:
    """从 policies.json 读取 maxRuntimeMinutes，转换为秒。"""
    if not POLICIES_FILE.is_file():
        return default
    try:
        with open(POLICIES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return default

    try:
        minutes = data["policies"]["execution"]["maxRuntimeMinutes"]["value"]
        return int(minutes) * 60
    except (KeyError, TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 更新任务 output 字段
# ---------------------------------------------------------------------------
def update_task_output(task_id: str, output: str):
    """通过 update_task.py 将结果写回任务的 output 字段。

    由于 update_task.py 的 CLI 不直接支持 --output 参数，
    这里直接读写 tasks.json 来更新 output 字段，同时写审计日志。
    """
    if not TASKS_FILE.is_file():
        print(f"[FAIL] 找不到文件: {TASKS_FILE}", file=sys.stderr)
        return False
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[FAIL] 无法读取 tasks.json: {e}", file=sys.stderr)
        return False

    tasks = data.get("tasks", [])
    found = False
    for task in tasks:
        if task.get("id") == task_id:
            task["output"] = output
            task["updatedAt"] = datetime.now(timezone.utc).isoformat()
            found = True
            break

    if not found:
        print(f"[FAIL] 找不到任务 {task_id}，无法更新 output", file=sys.stderr)
        return False

    try:
        with open(TASKS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[FAIL] 无法写入 tasks.json: {e}", file=sys.stderr)
        return False

    return True


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    _ensure_utf8_streams()

    parser = argparse.ArgumentParser(
        description="Hermes Agent 适配器 — 封装 hermes CLI 调用"
    )
    parser.add_argument(
        "--task-id",
        required=True,
        help="任务 ID，如 Task-001",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要执行的命令，不真正调用 Hermes",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help=f"超时秒数（默认从 policies.json 读取，回退 {DEFAULT_TIMEOUT_SECONDS}s）",
    )
    args = parser.parse_args()

    task_id = args.task_id

    # 1. 读取任务详情
    print(f"[INFO] 读取任务 {task_id}...")
    task = load_task(task_id)
    print(f"[OK] 任务标题: {task.get('title', '')}")

    # 2. 构建 prompt
    prompt = build_prompt(task)
    print(f"[INFO] 构建 prompt ({len(prompt)} 字符)")

    # 3. 确定超时
    timeout = args.timeout if args.timeout is not None else get_timeout_from_policies()
    print(f"[INFO] 超时设置: {timeout}s ({timeout // 60} 分钟)")

    # 4. 构建 hermes 命令
    hermes_args = [HERMES_COMMAND]
    for arg in HERMES_ARGS_TEMPLATE:
        if arg == "{prompt}":
            hermes_args.append(prompt)
        else:
            hermes_args.append(arg)

    print(f"[INFO] Hermes 命令: {HERMES_COMMAND} chat -q \"<prompt>\" --quiet --max-turns 30")
    print(f"[INFO] 工作目录: {HERMES_WORK_DIR}")

    # 5. dry-run 模式：只打印，不执行
    if args.dry_run:
        print("\n[DRY-RUN] 以下是将要执行的命令：")
        print(f"  命令: {HERMES_COMMAND} chat -q \"<prompt>\" --quiet --max-turns 30")
        print(f"  工作目录: {HERMES_WORK_DIR}")
        print(f"  超时: {timeout}s")
        print(f"  Prompt 内容:")
        print("  " + "=" * 58)
        for line in prompt.split("\n"):
            print(f"  {line}")
        print("  " + "=" * 58)
        print("[DRY-RUN] 未执行 Hermes，未修改任务状态。")

        # 写审计日志（dry-run 也记录）
        append_audit(
            event_type="hermes_adapter_dry_run",
            message=f"Hermes 适配器 dry-run: 任务 {task_id}",
            task_id=task_id,
            data={
                "agent": AGENT_ID,
                "command": f"{HERMES_COMMAND} chat -q <prompt> --quiet --max-turns 30",
                "workDir": HERMES_WORK_DIR,
                "timeout": timeout,
            },
        )
        print("[OK] dry-run 完成，审计日志已记录")
        sys.exit(0)

    # 6. 真正调用 Hermes
    print(f"[INFO] 调用 Hermes Agent (超时 {timeout}s)...")
    append_audit(
        event_type="hermes_adapter_start",
        message=f"Hermes 适配器开始执行任务 {task_id}",
        task_id=task_id,
        data={
            "agent": AGENT_ID,
            "command": f"{HERMES_COMMAND} chat -q <prompt> --quiet --max-turns 30",
            "workDir": HERMES_WORK_DIR,
            "timeout": timeout,
        },
    )

    try:
        result = subprocess.run(
            hermes_args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=HERMES_WORK_DIR,
        )
    except subprocess.TimeoutExpired:
        error_msg = f"Hermes 执行超时（>{timeout}s）"
        print(f"[FAIL] {error_msg}", file=sys.stderr)
        append_audit(
            event_type="hermes_adapter_timeout",
            message=error_msg,
            task_id=task_id,
            data={"agent": AGENT_ID, "timeout": timeout},
        )
        # 更新任务状态为 failed
        _update_task_status(task_id, "failed", f"Hermes 执行超时: {error_msg}")
        sys.exit(1)
    except FileNotFoundError:
        error_msg = f"找不到 hermes 命令，请确认 Hermes Agent 已安装并在 PATH 中"
        print(f"[FAIL] {error_msg}", file=sys.stderr)
        append_audit(
            event_type="hermes_adapter_error",
            message=error_msg,
            task_id=task_id,
            data={"agent": AGENT_ID, "error": "FileNotFoundError"},
        )
        _update_task_status(task_id, "failed", error_msg)
        sys.exit(1)
    except OSError as e:
        error_msg = f"调用 Hermes 时发生 OS 错误: {e}"
        print(f"[FAIL] {error_msg}", file=sys.stderr)
        append_audit(
            event_type="hermes_adapter_error",
            message=error_msg,
            task_id=task_id,
            data={"agent": AGENT_ID, "error": str(e)},
        )
        _update_task_status(task_id, "failed", error_msg)
        sys.exit(1)

    # 7. 处理结果
    stdout = result.stdout or ""
    stderr = result.stderr or ""

    if result.returncode == 0:
        print(f"[OK] Hermes 执行成功 (rc=0)")
        if stdout:
            print(f"[INFO] stdout 长度: {len(stdout)} 字符")

        # 写回任务 output
        # 截断过长的输出（遵守 maxOutputKB 策略，默认 1024 KB）
        max_output_bytes = _get_max_output_bytes()
        output_bytes = stdout.encode("utf-8")
        if len(output_bytes) > max_output_bytes:
            truncated = True
            stdout = output_bytes[:max_output_bytes].decode("utf-8", errors="replace")
            stdout += "\n... [输出已截断，超出 maxOutputKB 限制]"
            print(f"[WARN] 输出已截断 ({len(output_bytes)} > {max_output_bytes} bytes)")
        else:
            truncated = False

        success = update_task_output(task_id, stdout)
        if success:
            print(f"[OK] 任务 {task_id} output 已写回")
        else:
            print(f"[WARN] 任务 {task_id} output 写回失败", file=sys.stderr)

        # 更新任务状态为 done
        _update_task_status(task_id, "done", "Hermes 执行成功")

        append_audit(
            event_type="hermes_adapter_success",
            message=f"Hermes 适配器成功完成任务 {task_id}",
            task_id=task_id,
            data={
                "agent": AGENT_ID,
                "returnCode": 0,
                "outputLength": len(stdout),
                "truncated": truncated,
            },
        )
        print(f"[OK] 审计日志已记录")
        sys.exit(0)
    else:
        error_output = stderr if stderr else stdout
        print(f"[FAIL] Hermes 执行失败 (rc={result.returncode})", file=sys.stderr)
        if stderr:
            print(f"[INFO] stderr:\n{stderr}", file=sys.stderr)

        _update_task_status(task_id, "failed", f"Hermes 执行失败 (rc={result.returncode}): {error_output[:500]}")

        append_audit(
            event_type="hermes_adapter_failed",
            message=f"Hermes 适配器执行任务 {task_id} 失败 (rc={result.returncode})",
            task_id=task_id,
            data={
                "agent": AGENT_ID,
                "returnCode": result.returncode,
                "stderrLength": len(stderr),
            },
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# 辅助：更新任务状态
# ---------------------------------------------------------------------------
def _update_task_status(task_id: str, status: str, notes: str = ""):
    """通过 update_task.py 更新任务状态。"""
    try:
        cmd = [sys.executable, str(UPDATE_TASK_SCRIPT), "--id", task_id, "--status", status]
        if notes:
            cmd.extend(["--notes", notes])
        subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except Exception as e:
        print(f"[WARN] 更新任务状态失败: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 辅：从 policies.json 读取 maxOutputKB
# ---------------------------------------------------------------------------
def _get_max_output_bytes() -> int:
    """从 policies.json 读取 maxOutputKB，返回字节数。默认 1024*1024。"""
    if not POLICIES_FILE.is_file():
        return 1024 * 1024
    try:
        with open(POLICIES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        kb = data["policies"]["execution"]["maxOutputKB"]["value"]
        return int(kb) * 1024
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
        return 1024 * 1024


if __name__ == "__main__":
    main()
