#!/usr/bin/env python3
"""
dispatch_task.py — 任务派发脚本（阶段 1）

从 tasks/tasks.json 中选择一个 pending 任务：
    - 默认取第一个 pending 任务。
    - 支持 --id Task-001 指定任务。

生成派工提示文件到 logs/runs/Task-XXX_dispatch.md，
更新任务状态为 in_progress，并记录审计日志。

**重要**：本阶段不启动任何 ACP agent，不调用 opencode，仅生成提示文件。

用法:
    python scripts/dispatch_task.py [--id Task-001] [--assignee agent-exec-01]

仅使用 Python 标准库。
"""

import argparse
import json
import subprocess
import sys

# 强制 UTF-8 输出，避免 GBK 乱码
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))
from fix_encoding import setup_utf8_stdout
setup_utf8_stdout()
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
POLICIES_FILE = PROJECT_ROOT / "config" / "policies.json"
RUNS_DIR = PROJECT_ROOT / "logs" / "runs"
VALIDATE_SCRIPT = PROJECT_ROOT / "scripts" / "validate_task.py"

# 导入审计日志模块
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from audit_log import append_audit  # type: ignore
from file_lock import file_lock  # type: ignore
from event_log import build_event, append_event  # type: ignore

VALID_STATUSES = {"pending", "in_progress", "done", "failed", "blocked", "cancelled"}


def load_tasks():
    if not TASKS_FILE.is_file():
        print(f"[FAIL] 找不到文件: {TASKS_FILE}")
        sys.exit(1)
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        print(f"[FAIL] JSON 解析错误: {e}")
        sys.exit(1)
    except OSError as e:
        print(f"[FAIL] 无法读取文件: {e}")
        sys.exit(1)


def save_tasks(data):
    try:
        with open(TASKS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[FAIL] 无法写入文件: {e}")
        sys.exit(1)


def load_policies() -> dict:
    """读取 config/policies.json，返回 policies 字典。"""
    if not POLICIES_FILE.is_file():
        print(f"[FAIL] 找不到策略文件: {POLICIES_FILE}")
        sys.exit(1)
    try:
        with open(POLICIES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"[FAIL] 策略文件 JSON 解析错误: {e}")
        sys.exit(1)
    except OSError as e:
        print(f"[FAIL] 无法读取策略文件: {e}")
        sys.exit(1)
    return data.get("policies", {})


def preflight(task_id: str | None, assignee: str) -> dict:
    """
    完整 preflight 校验：
      1. 运行 validate_task.py 校验台账与 Agent 注册表。
      2. 校验 assignee 是否存在且已启用。
      3. 加载并校验 policies.json。
    返回 policies 字典。
    """
    # 1. 运行 validate_task.py
    print("[PREFLIGHT] 步骤 1/3: 校验任务台账与 Agent 注册表...")
    result = subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",

    )
    if result.returncode != 0:
        # 安全输出：避免 GBK 编码崩溃
        fail_msg = f"[PREFLIGHT FAIL] validate_task.py 未通过:\n{result.stdout}{result.stderr}"
        try:
            sys.stdout.buffer.write((fail_msg + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()
        except Exception:
            print(fail_msg.encode("ascii", errors="replace").decode())
        sys.exit(1)
    print("[PREFLIGHT OK] 台账与注册表校验通过")

    # 2. 校验 assignee
    print("[PREFLIGHT] 步骤 2/3: 校验指派 Agent...")
    agents_map = load_agents()
    validate_assignee(assignee, agents_map)
    print(f"[PREFLIGHT OK] assignee '{assignee}' 存在且已启用")

    # 3. 加载 policies
    print("[PREFLIGHT] 步骤 3/3: 加载执行策略...")
    policies = load_policies()
    if not policies:
        print("[PREFLIGHT FAIL] policies.json 为空或缺少 policies 字段")
        sys.exit(1)
    print("[PREFLIGHT OK] 策略加载成功")

    return policies


def generate_dispatch_prompt(task: dict, assignee: str, policies: dict) -> str:
    """生成给 CLI 工具的执行 prompt。"""
    title = task.get('title', '')
    description = task.get('description', '').strip()

    # 如果有详细描述，直接透传（这是 CLI 工具真正需要的）
    # 如果没有，用标题兜底
    if description:
        return description
    else:
        return f"{title}"


def load_agents() -> dict:
    """读取 config/agents.json，返回 {agent_id: agent_obj} 映射。"""
    if not AGENTS_FILE.is_file():
        print(f"[FAIL] 找不到文件: {AGENTS_FILE}")
        sys.exit(1)
    try:
        with open(AGENTS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"[FAIL] JSON 解析错误 (agents.json): {e}")
        sys.exit(1)
    except OSError as e:
        print(f"[FAIL] 无法读取文件 (agents.json): {e}")
        sys.exit(1)

    agents_list = data.get("agents", [])
    if not isinstance(agents_list, list):
        print("[FAIL] config/agents.json: agents 不是 list")
        sys.exit(1)

    agents_map: dict = {}
    for agent in agents_list:
        aid = agent.get("id", "")
        if aid:
            agents_map[aid] = agent
    return agents_map


def validate_assignee(assignee: str, agents_map: dict) -> None:
    """校验 assignee 是否存在于 agents.json 且 enabled=true。失败则 exit 1。"""
    if assignee is None or assignee.strip() == "":
        print("[FAIL] assignee 不能为空")
        sys.exit(1)
    if assignee not in agents_map:
        print(f"[FAIL] assignee '{assignee}' 不在 config/agents.json 中")
        sys.exit(1)
    agent_obj = agents_map[assignee]
    if not agent_obj.get("enabled", False):
        print(f"[FAIL] assignee '{assignee}' 未启用 (enabled=false)。拒绝派发。")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="派发 pending 任务")
    parser.add_argument("--id", help="指定任务 ID，如 Task-001")
    parser.add_argument("--assignee", default="agent-exec-01", help="指派给哪个 Agent（默认: agent-exec-01）")
    parser.add_argument("--execute", action="store_true", help="派工后自动调用 openclaw_executor 生成执行 prompt 文件")
    parser.add_argument("--execute-real", action="store_true",
                        help="派工后自动生成 prompt + 调用 executor_bridge 执行真实 CLI（一步到位）")
    parser.add_argument("--project", default=None,
                        help="目标项目路径，透传给 executor_bridge（如 G:\\weather\\weather-ai-project）")
    parser.add_argument("--write-output", action="store_true",
                        help="透传给 executor_bridge：解析 Agent 输出中的 file: 代码块写入目标文件")
    parser.add_argument("--timeout", type=int, default=None,
                        help="超时秒数，透传给 executor_bridge")
    parser.add_argument("--dry-run", action="store_true", help="只打印提示，不修改任务状态")
    args = parser.parse_args()

    # === 阶段 2 前置安全闸第三块：完整 preflight ===
    policies = preflight(args.id, args.assignee)

    # read-modify-write 原子操作，加排他锁
    try:
        with file_lock(str(TASKS_FILE), mode='exclusive'):
            data = load_tasks()
            tasks = data.get("tasks", [])

            target = None
            if args.id:
                for t in tasks:
                    if t.get("id") == args.id:
                        target = t
                        break
                if target is None:
                    print(f"[FAIL] 找不到任务: {args.id}")
                    sys.exit(1)
                if target.get("status") != "pending":
                    print(f"[FAIL] 任务 {args.id} 状态不是 pending（当前: {target.get('status')}）")
                    sys.exit(1)
            else:
                for t in tasks:
                    if t.get("status") == "pending":
                        target = t
                        break
                if target is None:
                    print("[FAIL] 当前没有 pending 任务可派发")
                    sys.exit(1)

            task_id = target["id"]

            # 生成 prompt（dry-run 时需要打印）
            prompt = generate_dispatch_prompt(target, args.assignee, policies)

            if args.dry_run:
                print(f"[DRY-RUN] 任务 {task_id} 状态未修改")
                print(f"[DRY-RUN] prompt: {prompt}")
                return

            # 更新任务状态
            target["status"] = "in_progress"
            target["assignee"] = args.assignee
            target["updatedAt"] = datetime.now(timezone.utc).isoformat()
            save_tasks(data)
    except TimeoutError as e:
        print(f"[FAIL] 获取文件锁超时: {e}")
        sys.exit(1)

    # 生成派工提示文件
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    dispatch_path = RUNS_DIR / f"{task_id}_dispatch.md"
    try:
        with open(dispatch_path, "w", encoding="utf-8") as fh:
            fh.write(prompt)
    except OSError as e:
        print(f"[FAIL] 无法写入派工提示: {e}")
        sys.exit(1)

    # 写审计日志
    append_audit(
        event_type="task_dispatched",
        message=f"任务已派发至 {args.assignee}",
        task_id=task_id,
        data={"assignee": args.assignee, "dispatchFile": str(dispatch_path.relative_to(PROJECT_ROOT))},
    )

    # 写事件日志
    try:
        event = build_event(
            event_type="task.dispatched",
            source="dispatch_task",
            correlation_id=task_id,
            payload={"taskId": task_id, "assignee": args.assignee},
        )
        append_event(event)
    except Exception as e:
        print(f"[WARN] 事件日志追加失败: {e}")

    print(f"[OK] {task_id} 已派发至 {args.assignee}")
    print(f"[OK] 派工提示: {dispatch_path}")

    # === --execute: 调用 openclaw_executor 生成执行 prompt 文件 ===
    if args.execute:
        executor_script = PROJECT_ROOT / "scripts" / "openclaw_executor.py"
        if not executor_script.is_file():
            print(f"[WARN] --execute 指定但 openclaw_executor.py 未找到，跳过执行步骤")
        else:
            print(f"[INFO] --execute: 调用 openclaw_executor 生成执行 prompt...")
            exec_cmd = [sys.executable, str(executor_script), "--task-id", task_id]
            if args.dry_run:
                exec_cmd.append("--dry-run")
            try:
                result = subprocess.run(
                    exec_cmd,
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                print(result.stdout, end="")
                if result.stderr:
                    print(result.stderr, end="", file=sys.stderr)
                if result.returncode != 0:
                    print(f"[WARN] openclaw_executor 退出码 {result.returncode}")
                else:
                    print(f"[OK] 执行 prompt 已生成，主控可用 sessions_spawn 派子 Agent 执行")
                    print(f"[INFO] 执行完成后运行: python scripts/openclaw_executor.py --task-id {task_id} --collect")
            except Exception as e:
                print(f"[WARN] 调用 openclaw_executor 异常: {e}")

    # === --execute-real: 自动生成 prompt + 调用 executor_bridge 执行真实 CLI（一步到位） ===
    if args.execute_real:
        executor_bridge_script = PROJECT_ROOT / "scripts" / "executor_bridge.py"
        if not executor_bridge_script.is_file():
            print(f"[FAIL] --execute-real 指定但 executor_bridge.py 未找到: {executor_bridge_script}")
            sys.exit(1)

        # 步骤 1: 检查 prompt 文件是否存在，不存在则自动生成
        prompt_file = PROJECT_ROOT / "tasks" / "dispatch" / f"{task_id}-prompt.txt"
        if not prompt_file.is_file():
            print(f"[INFO] prompt 文件不存在，自动生成...")
            executor_script = PROJECT_ROOT / "scripts" / "openclaw_executor.py"
            if not executor_script.is_file():
                print(f"[FAIL] openclaw_executor.py 未找到，无法生成 prompt")
                sys.exit(1)
            exec_cmd = [sys.executable, str(executor_script), "--task-id", task_id]
            if args.dry_run:
                exec_cmd.append("--dry-run")
            try:
                result = subprocess.run(
                    exec_cmd,
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                print(result.stdout, end="")
                if result.stderr:
                    print(result.stderr, end="", file=sys.stderr)
                if result.returncode != 0:
                    print(f"[FAIL] openclaw_executor 退出码 {result.returncode}")
                    sys.exit(1)
                print(f"[OK] prompt 文件已生成: {prompt_file}")
            except Exception as e:
                print(f"[FAIL] 调用 openclaw_executor 异常: {e}")
                sys.exit(1)
        else:
            print(f"[INFO] prompt 文件已存在: {prompt_file}")

        # 步骤 2: 调用 executor_bridge 执行
        bridge_cmd = [sys.executable, str(executor_bridge_script),
                      "--task-id", task_id, "--assignee", args.assignee]

        # 透传 --project
        if args.project:
            bridge_cmd += ["--project", args.project]
        # 透传 --write-output
        if args.write_output:
            bridge_cmd.append("--write-output")
        # 透传 --timeout
        if args.timeout:
            bridge_cmd += ["--timeout", str(args.timeout)]

        if args.dry_run:
            bridge_cmd.append("--dry-run")
            print(f"[DRY-RUN] 将执行: {' '.join(bridge_cmd)}")
        else:
            print(f"[INFO] --execute-real: 调用 executor_bridge 执行真实 CLI...")
            try:
                result = subprocess.run(bridge_cmd, cwd=PROJECT_ROOT)
                if result.returncode != 0:
                    print(f"[WARN] executor_bridge 退出码 {result.returncode}")
            except Exception as e:
                print(f"[WARN] 调用 executor_bridge 异常: {e}")
            print(f"[INFO] 执行完成，可用 python scripts/openclaw_executor.py --task-id {task_id} --collect 收集结果")


if __name__ == "__main__":
    main()
