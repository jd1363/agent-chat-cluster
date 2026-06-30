#!/usr/bin/env python3
"""run.py — 一站式任务执行入口（大脑专用）

创建任务 → 生成 prompt → 执行 CLI → 输出结果到 stdout

用法:
  # 基本用法
  python scripts/run.py --description "任务描述" --assignee agent-ext-02

  # 指定目标项目目录
  python scripts/run.py --description "给 api.py 加一个 /health 端点" --assignee agent-ext-01 --project 'G:/my-project'

  # 自定义超时（秒）
  python scripts/run.py --description "..." --assignee agent-ext-04 --timeout 300

  # dry-run（只打印不执行）
  python scripts/run.py --description "..." --assignee agent-ext-02 --dry-run

仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="一站式任务执行")
    parser.add_argument("--description", required=True, help="任务描述（原样传给 CLI 工具）")
    parser.add_argument("--assignee", default="agent-ext-02", help="执行 Agent ID (默认: agent-ext-02)")
    parser.add_argument("--title", default=None, help="任务标题（默认取 description 前 40 字）")
    parser.add_argument("--project", default=None, help="目标项目路径")
    parser.add_argument("--timeout", type=int, default=None, help="超时秒数（透传给 executor_bridge）")
    parser.add_argument("--write-output", action="store_true", help="解析输出中的 file: 块写入文件")
    parser.add_argument("--dry-run", action="store_true", help="只打印不执行")
    args = parser.parse_args()

    title = args.title or args.description[:40]
    if len(args.description) > 40 and not args.title:
        title += "..."

    # 步骤 1: 创建任务
    print(f"[1/3] 创建任务...", flush=True)
    create_cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "create_task.py"),
                  "--title", title, "--description", args.description, "--priority", "medium"]
    result = subprocess.run(create_cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    # 安全输出：避免 GBK 编码崩溃
    try:
        sys.stdout.buffer.write(result.stdout.encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        print(result.stdout.encode("ascii", errors="replace").decode(), end="")
    if result.returncode != 0:
        try:
            sys.stdout.buffer.write(result.stderr.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        except Exception:
            print(result.stderr.encode("ascii", errors="replace").decode(), end="", file=sys.stderr)
        sys.exit(1)

    # 提取 task_id：从 tasks.json 读最新创建的任务
    import json
    tasks_file = PROJECT_ROOT / "tasks" / "tasks.json"
    try:
        with open(tasks_file, "r", encoding="utf-8") as f:
            tasks_data = json.load(f)
        tasks_list = tasks_data.get("tasks", [])
        if tasks_list:
            task_id = tasks_list[-1].get("id")
    except Exception as e:
        print(f"[FAIL] 读取 tasks.json 失败: {e}", file=sys.stderr)

    print(f"[OK] task_id={task_id}", flush=True)

    # 步骤 2: 派工 + 执行
    print(f"[2/3] 派工并执行 (assignee={args.assignee})...", flush=True)
    dispatch_cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "dispatch_task.py"),
                    "--id", task_id, "--assignee", args.assignee, "--execute-real"]

    if args.project:
        dispatch_cmd += ["--project", args.project]
    if args.write_output:
        dispatch_cmd += ["--write-output"]
    if args.timeout:
        dispatch_cmd += ["--timeout", str(args.timeout)]
    if args.dry_run:
        dispatch_cmd += ["--dry-run"]

    # 直接继承 stdout/stderr，实时输出
    proc = subprocess.run(dispatch_cmd, cwd=PROJECT_ROOT)
    if proc.returncode != 0:
        print(f"[FAIL] 执行失败，exit code={proc.returncode}", file=sys.stderr)
        sys.exit(1)

    # 步骤 3: 读取结果
    print(f"[3/3] 读取结果...", flush=True)
    result_file = PROJECT_ROOT / "tasks" / "dispatch" / f"{task_id}-result.txt"
    if result_file.is_file():
        content = result_file.read_text(encoding="utf-8")
        print(f"\n{'='*60}")
        print(f"结果 ({task_id}):")
        print(f"{'='*60}")
        try:
            sys.stdout.buffer.write(content.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        except Exception:
            print(content.encode("ascii", errors="replace").decode())
    else:
        print(f"[WARN] 结果文件未找到: {result_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
