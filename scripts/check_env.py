#!/usr/bin/env python3
"""
check_env.py — 环境自检脚本

检查项：
1. 关键目录是否存在
2. 配置 JSON 是否可解析
3. OpenClaw gateway status 命令是否可运行（timeout=10s）

仅使用 Python 标准库。
"""

import json
import os
import shutil
import subprocess
import sys

# 相对于项目根目录的关键路径
REQUIRED_DIRS = [
    "config",
    "docs",
    "scripts",
    "tasks",
    "logs/audit",
    "logs/runs",
    "agents/resident",
    "agents/ext",
]

REQUIRED_FILES = [
    "config/agents.json",
    "config/policies.json",
    "tasks/tasks.json",
]

COMMAND_PROBE = ["openclaw", "gateway", "status"]
TIMEOUT_SECONDS = 10
SKIP_EXTERNAL = False  # controlled via --skip-external CLI flag


def check_directories():
    ok = True
    for d in REQUIRED_DIRS:
        if os.path.isdir(d):
            print(f"[OK] 目录存在: {d}")
        else:
            print(f"[FAIL] 目录缺失: {d}")
            ok = False
    return ok


def check_json_files():
    ok = True
    for f in REQUIRED_FILES:
        if not os.path.isfile(f):
            print(f"[FAIL] 文件缺失: {f}")
            ok = False
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                json.load(fh)
            print(f"[OK] JSON 可解析: {f}")
        except json.JSONDecodeError as e:
            print(f"[FAIL] JSON 解析错误 ({f}): {e}")
            ok = False
        except OSError as e:
            print(f"[FAIL] 无法读取 ({f}): {e}")
            ok = False
    return ok


def check_command():
    print(f"[INFO] 探测命令: {' '.join(COMMAND_PROBE)} (timeout={TIMEOUT_SECONDS}s)")

    # 优先查找可执行文件
    executable = None
    for name in ("openclaw", "openclaw.cmd", "openclaw.exe"):
        executable = shutil.which(name)
        if executable:
            break

    if not executable:
        print(f"[FAIL] 命令未找到: openclaw / openclaw.cmd / openclaw.exe")
        return False

    print(f"[INFO] 找到可执行文件: {executable}")

    try:
        result = subprocess.run(
            [executable, "gateway", "status"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode == 0:
            print(f"[OK] 命令成功 (rc=0)")
        else:
            print(f"[FAIL] 命令返回非零 (rc={result.returncode})")
        if result.stdout:
            print(f"[INFO] stdout:\n{result.stdout.strip()}")
        if result.stderr:
            print(f"[INFO] stderr:\n{result.stderr.strip()}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"[FAIL] 命令超时 (> {TIMEOUT_SECONDS}s)")
        return False
    except OSError as e:
        print(f"[FAIL] 命令执行异常: {e}")
        return False


def main():
    global SKIP_EXTERNAL
    SKIP_EXTERNAL = "--skip-external" in sys.argv

    print("=" * 50)
    print("Agent Chat Cluster — 环境自检")
    print("=" * 50)

    ok = True
    print("\n[1/3] 检查目录...")
    ok = check_directories() and ok

    print("\n[2/3] 检查配置文件...")
    ok = check_json_files() and ok

    print("\n[3/3] 检查外部命令...")
    if SKIP_EXTERNAL:
        print("[SKIP] 跳过外部命令检查 (--skip-external)")
    else:
        ok = check_command() and ok

    print("\n" + "=" * 50)
    if ok:
        print("结果: 全部通过")
        sys.exit(0)
    else:
        print("结果: 存在失败项，请修复后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
