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
        print(f"[PREFLIGHT FAIL] validate_task.py 未通过:\n{result.stdout}{result.stderr}")
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
    """生成 Markdown 格式的派工提示，约束从 policies.json 读取。"""
    now = datetime.now(timezone.utc).isoformat()

    exec_pol = policies.get("execution", {})
    comm_pol = policies.get("communication", {})
    audit_pol = policies.get("audit", {})

    max_runtime = exec_pol.get("maxRuntimeMinutes", {}).get("value", 30)
    max_output = exec_pol.get("maxOutputKB", {}).get("value", 1024)
    allowed_paths = exec_pol.get("allowedPaths", {}).get("value", ["scripts/", "tasks/", "logs/", "config/", "docs/"])
    max_concurrency = exec_pol.get("maxConcurrency", {}).get("value", 1)
    max_retries = exec_pol.get("maxRetries", {}).get("value", 1)

    auto_outbound = comm_pol.get("autoOutbound", {})
    dangerous_cmds = exec_pol.get("dangerousCommands", {})
    log_retention = audit_pol.get("logRetentionDays", 30)

    # 构建禁止行为列表
    prohibitions = []
    if not auto_outbound.get("allowed", False):
        prohibitions.append("1. 不得私自外发网络请求。")
    prohibitions.append("2. 不得启动其他 Agent。")
    prohibitions.append("3. 不得修改文件或目录权限。")
    if not dangerous_cmds.get("allowed", False):
        prohibitions.append("4. 不得执行 `rm -rf`、`format`、`fdisk`、`regedit` 等危险命令。")
    prohibitions.append("5. 不得访问 `G:\\agent chat` 原方案目录。")

    prohibit_block = "\n".join(prohibitions)
    allowed_paths_str = ", ".join(f"`{p}`" for p in allowed_paths)

    prompt = f"""# 派工提示 — {task['id']}

> 生成时间: {now}
> 指派给: {assignee}

## 任务信息

- **任务 ID**: {task['id']}
- **标题**: {task['title']}
- **优先级**: {task.get('priority', 'medium')}
- **状态**: in_progress（已派发）

## 执行约束（来源: config/policies.json）

- **最大运行时间**: {max_runtime} 分钟
- **最大输出大小**: {max_output} KB
- **最大并发**: {max_concurrency}
- **最大重试次数**: {max_retries}
- **工作目录**: `G:\\agent-chat-cluster`
- **允许路径**: {allowed_paths_str}

## 禁止行为

{prohibit_block}

## 期望输出

请按 docs/TASK_PROTOCOL.md 中定义的执行 Agent → 主控回报格式提供结果。

## 审计要求

- 记录所有执行的命令。
- 记录所有变更的文件。
- 主动报告识别到的风险。
- 日志保留天数: {log_retention} 天。
"""
    return prompt


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
    args = parser.parse_args()

    # === 阶段 2 前置安全闸第三块：完整 preflight ===
    policies = preflight(args.id, args.assignee)

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

    # 更新任务状态
    target["status"] = "in_progress"
    target["assignee"] = args.assignee
    target["updatedAt"] = datetime.now(timezone.utc).isoformat()
    save_tasks(data)

    # 生成派工提示文件
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    dispatch_path = RUNS_DIR / f"{task_id}_dispatch.md"
    prompt = generate_dispatch_prompt(target, args.assignee, policies)
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

    print(f"[OK] {task_id} 已派发至 {args.assignee}")
    print(f"[OK] 派工提示: {dispatch_path}")


if __name__ == "__main__":
    main()
