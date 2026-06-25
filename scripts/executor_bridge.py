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
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def build_command_args(
    executor_config: Dict[str, Any], prompt: str
) -> List[str]:
    """构建 CLI 命令参数列表（不经过 shell 解析）。

    将 executor_config 中的 {prompt} 占位符替换为真实 prompt 内容，
    返回 [command, arg1, arg2, ...] 列表，直接传给 subprocess.Popen，
    避免 shell=True 解析特殊字符导致 prompt 被截断。

    Args:
        executor_config: executor 配置字典
        prompt: 真实 prompt 文本

    Returns:
        命令参数列表，如 ['codex', 'exec', 'prompt content...']
    """
    command = executor_config.get("command", "")
    args = executor_config.get("args", [])

    # 替换 {prompt} 占位符
    resolved_args = [a.replace("{prompt}", prompt) for a in args]

    return [command] + resolved_args


def execute_cli(
    command: List[str],
    cwd: str,
    timeout: int,
    max_output_kb: int,
) -> Dict[str, Any]:
    """用 subprocess 执行 CLI 命令（不经过 shell），捕获输出。

    直接传参数列表给 Popen，不使用 shell=True，
    避免 shell 解析特殊字符导致 prompt 被截断。

    支持 .ps1/.cmd 脚本（codex/codewhale/opencode/mimo
    都是 npm 全局安装的 .ps1/.cmd 脚本）。

    使用 Popen + 进程组管理，确保超时时能 kill 整个进程树，
    避免 CLI 子进程（codex/ollama 等）残留吃内存。

    Args:
        command: 命令参数列表 ['cmd', 'arg1', 'arg2']
        cwd: 工作目录
        timeout: 超时秒数
        max_output_kb: 最大输出大小（KB）

    Returns:
        dict: {success: bool, output: str, error: str, elapsed: float}
    """
    start_time = time.monotonic()

    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

    # 创建进程组，使超时时能 kill 整个进程树
    if os.name == "nt":
        # Windows: CREATE_NEW_PROCESS_GROUP
        popen_kwargs: Dict[str, Any] = {
            "shell": False,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "cwd": cwd,
            "env": env,
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
        }
    else:
        # Unix: 新建会话/进程组
        popen_kwargs = {
            "shell": False,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "cwd": cwd,
            "env": env,
            "preexec_fn": os.setsid,
        }

    try:
        proc = subprocess.Popen(command, **popen_kwargs)
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

    # 等待进程完成或超时
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # 超时：先 terminate，等 3 秒
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            # 还没退，kill 整个进程组
            if os.name == "nt":
                # Windows: taskkill /T /F 递归 kill 进程树
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                    capture_output=True,
                )
            else:
                # Unix: kill 整个进程组
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass  # 进程已退出
            # 回收僵尸进程
            proc.wait()

        elapsed = time.monotonic() - start_time
        # 回收已有输出
        stdout_bytes, stderr_bytes = proc.communicate()
        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        # 输出截断
        max_bytes = max_output_kb * 1024
        if len(stdout.encode("utf-8")) > max_bytes:
            stdout = stdout.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")
            stdout += "\n... [输出已截断]"

        return {
            "success": False,
            "output": stdout,
            "error": f"执行超时 (>{timeout}s)",
            "elapsed": elapsed,
        }

    elapsed = time.monotonic() - start_time

    # 读取输出
    stdout_bytes, stderr_bytes = proc.communicate()
    stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
    stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

    # 输出截断
    max_bytes = max_output_kb * 1024
    if len(stdout.encode("utf-8")) > max_bytes:
        stdout = stdout.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")
        stdout += "\n... [输出已截断]"

    success = proc.returncode == 0
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


# ── 项目上下文 ─────────────────────────────────────────

# 排除的目录/文件模式
_EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', '.pytest_cache', '.venv', 'venv'}
_EXCLUDE_SUFFIXES = {'.pyc', '.pyo', '.so', '.dll', '.exe'}

# 单文件最大字符数 & 总字符上限
_MAX_FILE_CHARS = 2000  # 单文件最多 2000 字符（从 4000 降低）
_MAX_TOTAL_CHARS = 5000  # 总上下文最多 5000 字符（从 20000 降低）


def build_project_context(project_path: str, max_chars: int = _MAX_TOTAL_CHARS) -> str:
    """遍历项目目录，构建上下文字符串供 CLI Agent 参考。

    生成文件树（排除 .git/__pycache__/node_modules 等），
    读取所有 .py 和 .md 文件内容（每文件限 _MAX_FILE_CHARS 字符，总计 max_chars），
    拼成 Markdown 格式的上下文字符串。

    Args:
        project_path: 项目根目录的绝对路径
        max_chars: 上下文最大字符数，默认 _MAX_TOTAL_CHARS (5000)

    Returns:
        Markdown 格式的项目上下文字符串
    """
    root = Path(project_path)
    if not root.is_dir():
        _utf8_print(f"[WARN] 项目路径不存在或不是目录: {project_path}")
        return ""

    # ── 生成文件树 ──
    tree_lines: list[str] = []
    file_entries: list[Path] = []

    for entry in sorted(root.rglob("*")):
        # 排除目录
        if any(part in _EXCLUDE_DIRS for part in entry.relative_to(root).parts[:-1]):
            continue
        # 排除 .env
        if entry.name == ".env":
            continue
        # 排除后缀
        if entry.suffix in _EXCLUDE_SUFFIXES:
            continue

        if entry.is_file():
            file_entries.append(entry)
            rel = entry.relative_to(root).as_posix()
            tree_lines.append(f"  {rel}")

    tree_text = "\n".join(tree_lines) if tree_lines else "  (空目录)"

    # ── 读取关键文件内容 ──
    content_parts: list[str] = []
    total_chars = 0

    for fp in file_entries:
        if total_chars >= max_chars:
            break
        if fp.suffix not in (".py", ".md"):
            continue

        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # 截断单文件
        if len(text) > _MAX_FILE_CHARS:
            text = text[:_MAX_FILE_CHARS] + "\n... [文件已截断]"

        rel_path = fp.relative_to(root).as_posix()
        lang = "python" if fp.suffix == ".py" else "markdown"
        block = f"#### {rel_path}\n```{lang}\n{text}\n```\n"

        remaining = max_chars - total_chars
        if len(block) > remaining:
            block = block[:remaining] + "\n... [上下文已截断]\n"

        content_parts.append(block)
        total_chars += len(block)

    content_text = "\n".join(content_parts) if content_parts else "(无 .py/.md 文件)"

    return (
        "## 项目上下文\n\n"
        "### 文件结构\n"
        "```\n"
        f"{tree_text}\n"
        "```\n\n"
        "### 关键文件内容\n\n"
        f"{content_text}"
    )


def parse_and_write_output(output: str, project_path: str) -> list[str]:
    """解析 Agent 输出中的 ```file:路径 代码块，写入目标文件。

    代码块格式约定::

        ```file:backend/weather_core.py
        # 文件内容
        ```

    安全检查：跳过包含 ``..`` 或绝对路径的文件路径。

    Args:
        output: Agent 的完整输出文本
        project_path: 项目根目录路径，文件将写入此路径下

    Returns:
        成功写入的文件相对路径列表
    """
    root = Path(project_path)
    pattern = re.compile(r"```file:(.+?)\n(.*?)```", re.DOTALL)
    written: list[str] = []

    for m in pattern.finditer(output):
        rel_path = m.group(1).strip()
        content = m.group(2)

        # 安全检查：跳过路径遍历和绝对路径
        if ".." in rel_path:
            _utf8_print(f"[WARN] 跳过不安全路径（含 ..）: {rel_path}")
            continue
        if os.path.isabs(rel_path):
            _utf8_print(f"[WARN] 跳过绝对路径: {rel_path}")
            continue

        target = root / rel_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(rel_path)
        except OSError as e:
            _utf8_print(f"[WARN] 写入失败 {rel_path}: {e}")

    return written


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
    parser.add_argument("--project", default=None,
                        help="目标项目路径，启用上下文注入和输出写入（如 G:\\\\weather\\\\weather-ai-project）")
    parser.add_argument("--write-output", action="store_true",
                        help="解析 Agent 输出中的 ```file:路径 代码块，写入目标文件")
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

    # 项目模式：超时至少 600 秒
    if not args.timeout and args.project:
        timeout = max(config_timeout, 600)
        _utf8_print(f"[INFO] 项目模式: 超时调整为 {timeout}s")

    _utf8_print(f"[INFO] executor: command={command}, args={args_list}")
    _utf8_print(f"[INFO] workDir={work_dir}, timeout={timeout}s, maxOutput={max_output_kb}KB")

    # ── 2. 读取 prompt 文件 ──
    _utf8_print(f"[INFO] 读取 prompt 文件: tasks/dispatch/{task_id}-prompt.txt")
    prompt = read_prompt_file(task_id)
    _utf8_print(f"[INFO] prompt 长度: {len(prompt)} 字符")

    # ── 2.5 项目上下文注入 ──
    if args.project:
        _utf8_print(f"[INFO] 注入项目上下文: {args.project}")
        context = build_project_context(args.project, max_chars=5000)
        if context:
            prompt = context + "\n\n---\n\n## 执行任务\n\n" + prompt
            _utf8_print(f"[INFO] 上下文已注入，prompt 长度: {len(prompt)} 字符")
        else:
            _utf8_print("[WARN] 项目上下文为空，跳过注入")

    # ── 3. 构建命令 ──
    cmd_args = build_command_args(executor_config, prompt)
    cmd_display = f"{command} {' '.join(executor_config.get('args', []))}"

    # ── dry-run 模式 ──
    if args.dry_run:
        _utf8_print("")
        _utf8_print("[DRY-RUN] 将执行以下命令:")
        _utf8_print("=" * 60)
        _utf8_print(f"命令: {cmd_display}")
        _utf8_print(f"prompt 长度: {len(prompt)} 字符")
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

    result = execute_cli(cmd_args, work_dir, timeout, max_output_kb)

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

    # ── 8. 输出解析写入 ──
    if args.write_output and args.project and success:
        written = parse_and_write_output(output, args.project)
        if written:
            _utf8_print(f"[OK] 已写入 {len(written)} 个文件:")
            for f in written:
                _utf8_print(f"  - {f}")
        else:
            _utf8_print("[INFO] 未找到可写入的 file: 代码块")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
