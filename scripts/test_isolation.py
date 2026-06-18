#!/usr/bin/env python3
"""
test_isolation.py — Agent 环境隔离校验脚本

对 config/agents.json 中每个 Agent 执行隔离边界检查：
  1. cwd 目录存在性（仅 enabled=true 的 Agent）
  2. cwd 是否在项目根目录内
  3. cwd 之间是否互不重叠（防止 Agent 间越权）
  4. allowedPaths 是否会产生越界风险
  5. 模拟路径边界检查（内部 + 跨 Agent + 逃逸）

用法:
    python scripts/test_isolation.py
    python scripts/test_isolation.py --json

仅使用 Python 标准库。
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
POLICIES_FILE = PROJECT_ROOT / "config" / "policies.json"

# ── 模拟边界测试用的路径（相对于项目根目录）──────────────────────────
SIMULATED_TEST_PATHS = [
    ("agents/resident/exec01/output.log", "inside_cwd"),
    ("scripts/test_runner.py", "outside_cwd_in_allowed"),
    ("tasks/task-001.json", "outside_cwd_in_allowed"),
    ("logs/audit/session.log", "outside_cwd_in_allowed"),
    ("../../../etc/passwd", "outside_project_root"),
    ("C:/Windows/System32/drivers/etc/hosts", "absolute_system_path"),
    ("agents/ext/ext01/config.json", "overlap_other_agent_cwd"),
    ("config/agents.json", "project_root_shared"),
]


# ── 输出 / 状态辅助 ───────────────────────────────────────────────
exit_code = 0
_json_mode = False  # 由 main() 在解析参数后设置


def _out():
    """返回当前输出目标（JSON 模式用 stderr 避免污染 stdout）。"""
    import sys as _sys
    return _sys.stderr if _json_mode else _sys.stdout


def fail(msg: str):
    global exit_code
    print(f"[FAIL] {msg}", file=_out())
    exit_code = 1


def warn(msg: str):
    print(f"[WARN] {msg}", file=_out())


def ok(msg: str):
    print(f"[OK] {msg}", file=_out())


def load_json(filepath: Path) -> dict | None:
    if not filepath.is_file():
        fail(f"找不到文件: {filepath}")
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        fail(f"JSON 解析错误 ({filepath.name}): {e}")
        return None
    except OSError as e:
        fail(f"无法读取文件 ({filepath.name}): {e}")
        return None


# ── 路径辅助 ──────────────────────────────────────────────────────
def is_within(parent: Path, child: Path) -> bool:
    """child 是否在 parent 目录树内（含相等）。"""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def is_equal_or_within(parent: Path, child: Path) -> bool:
    """child 等于 parent 或在 parent 目录树内。"""
    rp = parent.resolve()
    rc = child.resolve()
    return rp == rc or is_within(rp, rc)


# ── 校验逻辑 ──────────────────────────────────────────────────────
def check_cwd_exists(agent: dict):
    """检查 enabled Agent 的 cwd 目录是否存在。"""
    cwd = agent.get("cwd", "")
    if not cwd:
        fail(f"[{agent['id']}] cwd 字段缺失或为空")
        return False
    cwd_path = PROJECT_ROOT / cwd
    if not cwd_path.is_dir():
        fail(f"[{agent['id']}] cwd 目录不存在: {cwd}")
        return False
    ok(f"[{agent['id']}] cwd 目录存在: {cwd}")
    return True


def check_cwd_in_project(agent: dict, resolved_project: Path) -> bool:
    """检查 cwd 是否在项目根目录内。"""
    cwd = agent.get("cwd", "")
    if not cwd:
        return False
    cwd_path = (PROJECT_ROOT / cwd).resolve()
    if not is_equal_or_within(resolved_project, cwd_path):
        fail(f"[{agent['id']}] cwd 逃逸到项目根目录外: {cwd} -> {cwd_path}")
        return False
    ok(f"[{agent['id']}] cwd 在项目根目录内")
    return True


def check_cwd_overlap(agents: list[dict], resolved_project: Path) -> bool:
    """检查任意两个 Agent 的 cwd 是否互不重叠。"""
    agent_cwds = []
    for a in agents:
        cwd = a.get("cwd", "")
        if cwd:
            agent_cwds.append((a["id"], (PROJECT_ROOT / cwd).resolve()))

    all_ok = True
    for i in range(len(agent_cwds)):
        for j in range(i + 1, len(agent_cwds)):
            id_a, pa = agent_cwds[i]
            id_b, pb = agent_cwds[j]
            if is_equal_or_within(pa, pb) or is_equal_or_within(pb, pa):
                fail(f"cwd 重叠: [{id_a}] ({pa}) 与 [{id_b}] ({pb}) 存在包含关系")
                all_ok = False

    if all_ok:
        ok("所有 Agent cwd 互不重叠")
    return all_ok


def get_allowed_paths(policies: dict) -> list[str]:
    """从 policies.json 提取全局 allowedPaths 列表。"""
    try:
        return policies["policies"]["execution"]["allowedPaths"]["value"]
    except (KeyError, TypeError):
        fail("policies.json: 无法读取 policies.execution.allowedPaths.value")
        return []


def check_allowed_paths_escape(agent: dict, allowed_paths: list[str],
                               resolved_project: Path) -> bool:
    """检查 allowedPaths 是否会造成越界（逃出项目根目录）。"""
    agent_id = agent["id"]
    cwd_str = agent.get("cwd", "")
    agent_cwd = (PROJECT_ROOT / cwd_str).resolve() if cwd_str else resolved_project

    all_ok = True
    for ap in allowed_paths:
        ap_path = (PROJECT_ROOT / ap).resolve()
        # 允许：在项目根目录内，或在 agent cwd 内
        if is_equal_or_within(resolved_project, ap_path):
            continue
        if is_equal_or_within(agent_cwd, ap_path):
            continue
        # 逃逸到外部
        fail(f"[{agent_id}] allowedPath 越界: {ap} -> {ap_path} (超出项目根目录与 agent cwd)")
        all_ok = False

    if all_ok:
        ok(f"[{agent_id}] allowedPaths 未发现越界风险 ({len(allowed_paths)} 条)")
    return all_ok


def simulate_boundary_checks(agent: dict, all_agents: list[dict],
                             allowed_paths: list[str],
                             resolved_project: Path) -> list[dict]:
    """对给定 test paths 做模拟边界检查。"""
    agent_id = agent["id"]
    cwd_str = agent.get("cwd", "")
    agent_cwd = (PROJECT_ROOT / cwd_str).resolve() if cwd_str else resolved_project

    # 收集其他 Agent 的 cwd
    other_cwds: dict[str, Path] = {}
    for a in all_agents:
        if a["id"] == agent_id:
            continue
        oc = a.get("cwd", "")
        if oc:
            other_cwds[a["id"]] = (PROJECT_ROOT / oc).resolve()

    results = []
    for test_path, category in SIMULATED_TEST_PATHS:
        # 解析测试路径（相对项目根目录，模拟 Agent 试图访问的路径）
        tp = Path(test_path)
        if tp.is_absolute():
            resolved = tp.resolve()
        else:
            resolved = (resolved_project / tp).resolve()

        # 判定逻辑（按优先级依次判定）
        # 1) 在 agent 自己的 cwd 内 → PASS
        if is_equal_or_within(agent_cwd, resolved):
            result = "PASS"
            reason = "路径在 agent cwd 内"

        # 2) 在项目根目录内 → 进一步细分
        elif is_equal_or_within(resolved_project, resolved):
            # 2a) 先检查是否落在其他 Agent 的 cwd（跨 Agent 越权）→ FAIL
            overlap_agent = None
            for oid, ocwd in other_cwds.items():
                if is_equal_or_within(ocwd, resolved):
                    overlap_agent = oid
                    break
            if overlap_agent:
                result = "FAIL"
                reason = f"路径落在 Agent [{overlap_agent}] 的 cwd 内（跨 Agent 越权）"
            # 2b) 不在其他 Agent cwd，检查是否在 allowedPaths 中 → WARN
            elif any(is_equal_or_within((PROJECT_ROOT / ap).resolve(), resolved)
                     for ap in allowed_paths):
                result = "WARN"
                reason = "路径在 allowedPaths 内但不在 agent cwd 内"
            # 2c) 不在 allowedPaths → FAIL
            else:
                result = "FAIL"
                reason = "路径在项目根目录内但不在 allowedPaths 中"

        # 3) 逃逸到项目根目录外 → FAIL
        else:
            result = "FAIL"
            reason = "路径逃逸到项目根目录外"

        print(f"  [{agent_id}] 模拟 {category}: {test_path} -> {resolved}", file=_out())
        print(f"    结果: [{result}] {reason}", file=_out())

        results.append({
            "test_path": test_path,
            "category": category,
            "resolved": str(resolved),
            "result": result,
            "reason": reason,
        })

    return results


# ── 主流程 ────────────────────────────────────────────────────────
def main():
    global exit_code, _json_mode

    parser = argparse.ArgumentParser(
        description="Agent 环境隔离校验脚本"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果",
    )
    args = parser.parse_args()

    _json_mode = args.json
    resolved_project = PROJECT_ROOT.resolve()

    if not args.json:
        print("=" * 60)
        print("Agent Chat Cluster — 环境隔离校验")
        print(f"项目根目录: {resolved_project}")
        print("=" * 60)

    # 加载配置
    agents_data = load_json(AGENTS_FILE)
    policies_data = load_json(POLICIES_FILE)

    if agents_data is None or policies_data is None:
        sys.exit(1)

    agents_list: list[dict] = agents_data.get("agents", [])
    if not isinstance(agents_list, list):
        fail("config/agents.json: agents 不是 list")
        sys.exit(1)

    if not agents_list:
        if not args.json:
            ok("agents 列表为空，无需校验")
        sys.exit(0)

    allowed_paths = get_allowed_paths(policies_data)

    json_output: dict = {
        "project_root": str(resolved_project),
        "agents": [],
        "summary": {},
    }

    # 初始化 json_output 中每个 Agent 的基础结构
    for agent in agents_list:
        json_output["agents"].append({
            "id": agent.get("id", "?"),
            "enabled": agent.get("enabled", False),
            "cwd": agent.get("cwd", ""),
            "checks": {},
            "boundary_tests": [],
        })

    def _agent_entry(aid: str) -> dict | None:
        """返回 json_output 中对应 agent 的条目。"""
        for e in json_output["agents"]:
            if e["id"] == aid:
                return e
        return None

    # ── 第 1 步：cwd 目录存在性（仅 enabled）───────────────────────
    if not args.json:
        print("\n[1/5] 检查 enabled Agent 的 cwd 目录存在性...")

    for agent in agents_list:
        if agent.get("enabled"):
            cwd_ok = check_cwd_exists(agent)
            entry = _agent_entry(agent["id"])
            if entry:
                entry["checks"]["cwd_exists"] = "PASS" if cwd_ok else "FAIL"

    # ── 第 2 步：cwd 在项目根目录内 ────────────────────────────────
    if not args.json:
        print("\n[2/5] 检查 cwd 是否在项目根目录内...")

    for agent in agents_list:
        cwd_in = check_cwd_in_project(agent, resolved_project)
        entry = _agent_entry(agent["id"])
        if entry:
            entry["checks"]["cwd_in_project"] = "PASS" if cwd_in else "FAIL"

    # ── 第 3 步：cwd 之间互不重叠 ──────────────────────────────────
    if not args.json:
        print("\n[3/5] 检查 cwd 之间是否互不重叠...")

    overlap_ok = check_cwd_overlap(agents_list, resolved_project)
    for entry in json_output["agents"]:
        entry["checks"]["cwd_overlap"] = "PASS" if overlap_ok else "FAIL"

    # ── 第 4 步：allowedPaths 越界检查（仅 enabled）───────────────
    if not args.json:
        print("\n[4/5] 检查 allowedPaths 越界风险（仅 enabled Agent）...")

    for agent in agents_list:
        if not agent.get("enabled"):
            if not args.json:
                print(f"[SKIP] [{agent['id']}] 未启用，跳过 allowedPaths 检查")
            continue
        ap_ok = check_allowed_paths_escape(agent, allowed_paths, resolved_project)
        entry = _agent_entry(agent["id"])
        if entry:
            entry["checks"]["allowed_paths_escape"] = "PASS" if ap_ok else "FAIL"

    # ── 第 5 步：模拟路径边界检查（仅 enabled）────────────────────
    if not args.json:
        print("\n[5/5] 模拟路径边界检查（仅 enabled Agent）...")

    for agent in agents_list:
        if not agent.get("enabled"):
            if not args.json:
                print(f"[SKIP] [{agent['id']}] 未启用，跳过边界模拟")
            continue

        if not args.json:
            print(f"\n  ── [{agent['id']}] 边界模拟 (cwd={agent.get('cwd','')}) ──")

        bt_results = simulate_boundary_checks(
            agent, agents_list, allowed_paths, resolved_project
        )
        entry = _agent_entry(agent["id"])
        if entry:
            entry["boundary_tests"] = bt_results

    # ── 汇总 ───────────────────────────────────────────────────────
    if not args.json:
        print("\n" + "=" * 60)

    # 统计
    pass_count = 0
    warn_count = 0
    fail_count = 0

    # 统计 checks 中的 FAIL
    for entry in json_output["agents"]:
        for check_name, check_result in entry.get("checks", {}).items():
            if check_result == "FAIL":
                fail_count += 1
            elif check_result == "PASS":
                pass_count += 1
            elif check_result == "WARN":
                warn_count += 1

        # 统计 boundary_tests (仅统计 enabled agent 的测试结果)
        for bt in entry.get("boundary_tests", []):
            if bt["result"] == "FAIL":
                fail_count += 1
            elif bt["result"] == "WARN":
                warn_count += 1
            elif bt["result"] == "PASS":
                pass_count += 1

    json_output["summary"] = {
        "total_agents": len(agents_list),
        "enabled_agents": sum(1 for a in agents_list if a.get("enabled")),
        "total_checks": pass_count + warn_count + fail_count,
        "pass": pass_count,
        "warn": warn_count,
        "fail": fail_count,
    }

    if args.json:
        print(json.dumps(json_output, ensure_ascii=False, indent=2))
    else:
        # 逐 Agent 输出结构化报告
        for entry in json_output["agents"]:
            aid = entry["id"]
            enabled = "启用" if entry["enabled"] else "禁用"
            print(f"\nAgent: {aid} [{enabled}]")
            print(f"  cwd: {entry['cwd']}")
            checks = entry.get("checks", {})
            for cname in ["cwd_exists", "cwd_in_project", "cwd_overlap",
                          "allowed_paths_escape"]:
                if cname in checks:
                    marker = checks[cname]
                    print(f"  {cname}: [{marker}]")

            bt = entry.get("boundary_tests", [])
            if bt:
                print(f"  边界测试 ({len(bt)} 项):")
                bt_fails = [t for t in bt if t["result"] == "FAIL"]
                bt_warns = [t for t in bt if t["result"] == "WARN"]
                bt_passes = [t for t in bt if t["result"] == "PASS"]
                print(f"    PASS={len(bt_passes)} WARN={len(bt_warns)} FAIL={len(bt_fails)}")
                for t in bt:
                    if t["result"] != "PASS":
                        print(f"    [{t['result']}] {t['test_path']} — {t['reason']}")

        s = json_output["summary"]
        print(f"\n{'=' * 60}")
        print(f"汇总: {s['total_agents']} Agent ({s['enabled_agents']} 启用), "
              f"共 {s['total_checks']} 项检查")
        print(f"  PASS: {s['pass']}   WARN: {s['warn']}   FAIL: {s['fail']}")

        if s["fail"] > 0:
            print(f"\n[FAIL] 隔离校验未通过，发现 {s['fail']} 处严重问题")
        elif s["warn"] > 0:
            print(f"\n[OK] 隔离校验基本通过，存在 {s['warn']} 处警告")
        else:
            print(f"\n[OK] 所有隔离校验通过")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
