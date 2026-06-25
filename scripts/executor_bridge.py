#!/usr/bin/env python3
"""Executor Bridge — 把派工 prompt 转发给真实 CLI 执行引擎。

读取 Agent 的 executor 配置，调用真实 CLI 工具（codex/codewhale/opencode/mimo/ollama）
执行任务，捕获输出，写结果文件，更新任务状态，记录审计日志。

用法:
  # 执行指定任务
  python scripts/executor_bridge.py --task-id Task-XXX --assignee agent-exec-01

  # dry-run 模式（只打印命令，不执行）
  python scripts/executor_bridge.py --task-id Task-XXX --assignee agent-exec-01 --dry-run

  # 自定义超时
  python scripts/executor_bridge.py --task-id Task-XXX --assignee agent-ext-03 --timeout 300

仅使用 Python 标准库。
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
DISPATCH_DIR = PROJECT_ROOT / "tasks" / "dispatch"
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"

# 导入项目模块
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from file_lock import file_lock  # type: ignore
from audit_log import append_audit  # type: ignore

# ── 编码安全 ──────────────────────────────────────────────
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _utf8_print(msg: str) -> None:
    """安全 print：直接写 stdout.buffer，避免 Windows 控制台编码问题。"""
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
    """读取 JSON 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    """写入 JSON 文件（utf-8，缩进 2 空格）。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_task(data: Dict[str, Any], task_id: str) -> Optional[Dict[str, Any]]:
    """在 tasks 列表中查找指定任务。"""
    for t in data.get("tasks", []):
        if t.get("id") == task_id:
            return t
    return None


def find_agent(agents_data: Dict[str, Any], agent_id: str) -> Optional[Dict[str, Any]]:
    """在 agents 列表中查找指定 Agent。"""
    for a in agents_data.get("agents", []):
        if a.get("id") == agent_id:
            return a
    return None


# ── 核心函数 ──────────────────────────────────────────────

def load_agent_executor(agent_id: str) -> Dict[str, Any]:
    """从 agents.json 读取指定 Agent 的 executor 配置。

    返回:
        executor 配置字典，包含 command, args, workDir, timeoutSeconds, maxOutputKB

    异常:
        SystemExit — Agent 不存在、未启用、或缺少 executor 配置时退出
    """
    if not AGENTS_FILE.is_file():
        _utf8_print(f"[FAIL] 找不到文件: {AGENTS_FILE}")
        sys.exit(1)

    try:
        agents_data = load_json(AGENTS_FILE)
    except json.JSONDecodeError as e:
        _utf8_print(f"[FAIL] agents.json JSON 解析错误: {e}")
        sys.exit(1)
    except OSError as e:
        _utf8_print(f"[FAIL] 无法读取 agents.json: {e}")
        sys.exit(1)

    agent = find_agent(agents_data, agent_id)
    if agent is None:
        _utf8_print(f"[FAIL] Agent '{agent_id}' 不在 config/agents.json 中")
        sys.exit(1)

    if not agent.get("enabled", False):
        _utf8_print(f"[FAIL] Agent '{agent_id}' 未启用 (enabled=false)")
        sys.exit(1)

    # 优先取 executor 字段，兼容 backend 字段（hermes 等）
    executor_config = agent.get("executor") or agent.get("backend")
    if not executor_config:
        _utf8_print(f"[FAIL] Agent '{agent_id}' 缺少 executor/backend 配置")
        sys.exit(1)

    exec_type = executor_config.get("type", "")
    if exec_type not in ("cli", "hermes-cli"):
        _utf8_print(f"[FAIL] Agent '{agent_id}' executor type 不是 cli/hermes-cli: {exec_type}")
        sys.exit(1)

    return executor_config


def read_prompt_file(task_id: str) -> str:
    """读取 tasks/dispatch/{task_id}-prompt.txt 文件内容。

    异常:
        SystemExit — 文件不存在或读取失败时退出
    """
    prompt_file = DISPATCH_DIR / f"{task_id}-prompt.txt"
    if not prompt_file.is_file():
        _utf8_print(f"[FAIL] 找不到 prompt 文件: {prompt_file}")
        _utf8_print("[INFO] 请先运行 dispatch_task.py + openclaw_executor.py 生成 prompt 文件")
        sys.exit(1)

    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        _utf8_print(f"[FAIL] 读取 prompt 文件失败: {e}")
        sys.exit(1)


def build_command(executor_config: Dict[str, Any], prompt: str) -> str:
    """构建 CLI 命令字符串。

    将 executor_config 中的 {prompt} 占位符替换为真实 prompt 内容，
    然后拼接成完整的命令字符串。

    对于 Windows 上的 .ps1/.cmd 脚本（codex/codewhale/opencode/mimo），
    使用 shell=True 执行，因此需要将命令拼成字符串。

    Args:
        executor_config: executor 配置字典
        prompt: 真实 prompt 文本

    Returns:
        完整的命令字符串，如 'codex exec "..."'
    """
    command = executor_config.get("command", "")
    args = executor_config.get("args", [])

    # 替换 {prompt} 占位符
    resolved_args = [a.replace("{prompt}", prompt) for a in args]

    # 拼接成命令字符串
    # prompt 中可能包含特殊字符，用双引号包裹并对内部双引号转义
    parts = [command]
    for arg in resolved_args:
        # 如果参数包含空格或特殊字符，用双引号包裹
        if " " in arg or '"' in arg or "'" in arg:
            # 转义双引号
            escaped = arg.replace('"', '\\"')
            parts.append(f'"{escaped}"')
        else:
            parts.append(arg)

    return " ".join(parts)


def execute_cli(
    command: str,
    cwd: str,
    timeout: int,
    max_output_kb: int,
) -> Dict[str, Any]:
    """用 subprocess 执行 CLI 命令，捕获输出。

    在 Windows 上使用 shell=True 以支持 .ps1 脚本（codex/codewhale/opencode/mimo
    都是 npm 全局安装的 .ps1/.cmd 脚本）。

    Args:
        command: 完整的命令字符串
        cwd: 工作目录
        timeout: 超时秒数
        max_output_kb: 最大输出大小（KB）

    Returns:
        dict: {success: bool, output: str, error: str, elapsed: float}
    """
    start_time = time.monotonic()

    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start_time
        return {
            "success": False,
            "output": "",
            "error": f"执行超时 (>{timeout}s)",
            "elapsed": elapsed,
        }
    except FileNotFoundError:
        elapsed = time.monotonic() - start_time
        return {
            "success": False,
            "output": "",
            "error": f"命令未找到: {command.split()[0] if command else ''}",
            "elapsed": elapsed,
        }
    except Exception as e:
        elapsed = time.monotonic() - start_time
        return {
            "success": False,
            "output": "",
            "error": f"调用异常: {e}",
            "elapsed": elapsed,
        }

    elapsed = time.monotonic() - start_time

    # 解码输出
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

    # 输出截断
    max_bytes = max_output_kb * 1024
    if len(stdout.encode("utf-8")) > max_bytes:
        stdout = stdout.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")
        stdout += "\n... [输出已截断]"

    success = result.returncode == 0
    error_msg = stderr.strip() if not success and stderr else ""

    return {
        "success": success,
        "output": stdout,
        "error": error_msg,
        "elapsed": elapsed,
    }


def write_result_file(task_id: str, result_text: str) -> Path:
    """将执行结果写入 tasks/dispatch/{task_id}-result.txt。

    如果执行失败，结果开头标记 [EXECUTION FAILED]，
    openclaw_executor --collect 会据此标记任务为 failed。

    Args:
        task_id: 任务 ID
        result_text: 结果文本

    Returns:
        结果文件路径
    """
    DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    result_file = DISPATCH_DIR / f"{task_id}-result.txt"
    with open(result_file, "w", encoding="utf-8") as f:
        f.write(result_text)
    return result_file


def update_task_status(task_id: str, status: str, output: str) -> None:
    """加排他锁更新 tasks.json 中任务状态。

    read-modify-write 原子操作：
      1. 加排他锁
      2. 重新加载最新 tasks.json
      3. 找到目标任务，更新 status/output/updatedAt
      4. 写回文件

    Args:
        task_id: 任务 ID
        status: 新状态（done / failed）
        output: 执行输出
    """
    try:
        with file_lock(str(TASKS_FILE), mode="exclusive"):
            data = load_json(TASKS_FILE)
            task = find_task(data, task_id)
            if not task:
                _utf8_print(f"[ERROR] 任务 {task_id} 不存在（重载后）")
                return
            task["status"] = status
            task["output"] = output[:1024 * 1024]  # 限制 1MB
            task["updatedAt"] = _now_iso()
            save_json(TASKS_FILE, data)
    except TimeoutError as e:
        _utf8_print(f"[ERROR] 获取文件锁超时: {e}")


def write_audit_log(event_type: str, task_id: str, details: str) -> None:
    """写审计日志到 logs/audit/{date}.jsonl。

    使用 audit_log.append_audit 函数，保持与项目其他脚本一致的日志格式。

    Args:
        event_type: 事件类型
        task_id: 任务 ID
        details: 事件详情
    """
    append_audit(
        event_type=event_type,
        message=details,
        task_id=task_id,
    )


# ── 主流程 ────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executor Bridge — 把派工 prompt 转发给真实 CLI 执行引擎"
    )
    parser.add_argument("--task-id", required=True, help="要执行的任务 ID (如 Task-001)")
    parser.add_argument("--assignee", required=True, help="执行 Agent ID (如 agent-exec-01)")
    parser.add_argument("--timeout", type=int, default=None,
                        help="超时秒数（默认从 Agent executor 配置读取）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印命令，不真实执行")
    args = parser.parse_args()

    task_id = args.task_id
    agent_id = args.assignee

    # ── 1. 读取 Agent executor 配置 ──
    _utf8_print(f"[INFO] 加载 Agent '{agent_id}' executor 配置...")
    executor_config = load_agent_executor(agent_id)

    command = executor_config.get("command", "")
    args_list = executor_config.get("args", [])
    work_dir = executor_config.get("workDir", str(PROJECT_ROOT))
    config_timeout = executor_config.get("timeoutSeconds", 120)
    config_max_output = executor_config.get("maxOutputKB", 1024)

    timeout = args.timeout or config_timeout
    max_output_kb = config_max_output

    _utf8_print(f"[INFO] executor: command={command}, args={args_list}")
    _utf8_print(f"[INFO] workDir={work_dir}, timeout={timeout}s, maxOutput={max_output_kb}KB")

    # ── 2. 读取 prompt 文件 ──
    _utf8_print(f"[INFO] 读取 prompt 文件: tasks/dispatch/{task_id}-prompt.txt")
    prompt = read_prompt_file(task_id)
    _utf8_print(f"[INFO] prompt 长度: {len(prompt)} 字符")

    # ── 3. 构建命令 ──
    cmd_str = build_command(executor_config, prompt)

    # ── dry-run 模式 ──
    if args.dry_run:
        _utf8_print("")
        _utf8_print("[DRY-RUN] 将执行以下命令:")
        _utf8_print("=" * 60)
        _utf8_print(f"命令: {cmd_str}")
        _utf8_print(f"工作目录: {work_dir}")
        _utf8_print(f"超时: {timeout}s")
        _utf8_print(f"最大输出: {max_output_kb}KB")
        _utf8_print("=" * 60)
        write_audit_log("executor_bridge_dry_run", task_id,
                        f"dry-run, agent={agent_id}, command={command}")
        _utf8_print("[OK] dry-run 完成")
        return 0

    # ── 4. 执行 CLI 命令 ──
    _utf8_print(f"[INFO] 执行命令: {command} ...")
    write_audit_log("executor_bridge_start", task_id,
                    f"agent={agent_id}, command={command}, timeout={timeout}s")

    result = execute_cli(cmd_str, work_dir, timeout, max_output_kb)

    elapsed = result["elapsed"]
    success = result["success"]
    output = result["output"]
    error = result["error"]

    if success:
        _utf8_print(f"[OK] 执行完成 ({elapsed:.1f}s)")
    else:
        _utf8_print(f"[FAIL] 执行失败 ({elapsed:.1f}s): {error}")

    # ── 5. 写结果文件 ──
    if success:
        result_text = output
    else:
        # 失败时结果开头标记 [EXECUTION FAILED]
        # openclaw_executor --collect 会据此标记任务为 failed
        error_line = f"[EXECUTION FAILED] {error}" if error else "[EXECUTION FAILED]"
        result_text = error_line + "\n" + output

    result_file = write_result_file(task_id, result_text)
    _utf8_print(f"[OK] 结果文件已写入: {result_file}")

    # ── 6. 更新任务状态 ──
    new_status = "done" if success else "failed"
    update_task_status(task_id, new_status, output if success else (error or "执行失败"))
    _utf8_print(f"[OK] 任务已标记 {new_status}")

    # ── 7. 写审计日志 ──
    if success:
        write_audit_log("executor_bridge_success", task_id,
                        f"agent={agent_id}, command={command}, "
                        f"耗时={elapsed:.1f}s, 输出={len(output)}字符")
    else:
        write_audit_log("executor_bridge_failed", task_id,
                        f"agent={agent_id}, command={command}, "
                        f"耗时={elapsed:.1f}s, 错误={error[:200]}")

    # ── 输出预览 ──
    if output:
        _utf8_print("")
        _utf8_print("[OUTPUT PREVIEW]")
        preview = output[:500]
        for line in preview.split("\n"):
            _utf8_print(line)
        if len(output) > 500:
            _utf8_print("... [更多输出已省略]")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
