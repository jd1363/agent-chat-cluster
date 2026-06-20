#!/usr/bin/env python3
"""
snapshot_config.py — 配置快照 / 列表 / 恢复

对应旧方案里的“配置快照 + 一键备份/恢复”，但用当前项目真实能力落地：
- 仅使用 Python 标准库
- 快照写入 snapshots/<name>/
- 默认备份 config/、tasks/tasks.json、关键项目文档
- 恢复前强制创建 restore 前备份，降低误操作风险
- 所有 save/restore 操作写入 audit_log

用法：
    python scripts/snapshot_config.py save --name before-ext02
    python scripts/snapshot_config.py list
    python scripts/snapshot_config.py show --name before-ext02
    python scripts/snapshot_config.py restore --name before-ext02 --yes
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = PROJECT_ROOT / "snapshots"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from audit_log import append_audit  # type: ignore

BACKUP_PATHS = [
    "config/agents.json",
    "config/policies.json",
    "config/.round_robin_state",
    "tasks/tasks.json",
    "README.md",
    "PROJECT_PLAN.md",
    "docs/OPERATOR_RUNBOOK.md",
    "docs/SECURITY_NOTES.md",
    "docs/TASK_PROTOCOL.md",
    "state/system_state.json",
]

RESTORE_PATHS = [
    "config/agents.json",
    "config/policies.json",
    "config/.round_robin_state",
    "tasks/tasks.json",
]

NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(name: str) -> str:
    if not NAME_RE.match(name):
        print("[FAIL] 快照名称只能包含 A-Z a-z 0-9 . _ -，长度 1-64", file=sys.stderr)
        sys.exit(1)
    if name in {".", ".."}:
        print("[FAIL] 非法快照名称", file=sys.stderr)
        sys.exit(1)
    return name


def snapshot_dir(name: str) -> Path:
    safe = safe_name(name)
    path = SNAPSHOT_ROOT / safe
    resolved_root = SNAPSHOT_ROOT.resolve()
    resolved_path = path.resolve()
    if resolved_root not in resolved_path.parents and resolved_path != resolved_root:
        print("[FAIL] 快照路径越界", file=sys.stderr)
        sys.exit(1)
    return path


def copy_file(src_rel: str, dst_root: Path) -> bool:
    src = PROJECT_ROOT / src_rel
    if not src.exists():
        return False
    if not src.is_file():
        return False
    dst = dst_root / src_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def write_manifest(dst_root: Path, name: str, copied: List[str], missing: List[str], reason: str) -> None:
    manifest = {
        "schemaVersion": "1.0",
        "name": name,
        "createdAt": utc_now(),
        "reason": reason,
        "copied": copied,
        "missing": missing,
        "restorePaths": RESTORE_PATHS,
    }
    with open(dst_root / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)


def save_snapshot(name: str, reason: str, overwrite: bool = False) -> Path:
    dst_root = snapshot_dir(name)
    if dst_root.exists():
        if not overwrite:
            print(f"[FAIL] 快照已存在: {name}；如需覆盖请加 --overwrite", file=sys.stderr)
            sys.exit(1)
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True, exist_ok=True)

    copied: List[str] = []
    missing: List[str] = []
    for rel in BACKUP_PATHS:
        if copy_file(rel, dst_root):
            copied.append(rel)
        else:
            missing.append(rel)

    write_manifest(dst_root, name, copied, missing, reason)
    append_audit(
        event_type="snapshot_saved",
        message=f"保存配置快照: {name}",
        data={"name": name, "reason": reason, "copied": copied, "missing": missing},
    )
    return dst_root


def list_snapshots(json_output: bool = False) -> None:
    SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    items: List[Dict[str, object]] = []
    for child in sorted(SNAPSHOT_ROOT.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        manifest: Dict[str, object] = {}
        if manifest_path.is_file():
            try:
                with open(manifest_path, "r", encoding="utf-8") as fh:
                    manifest = json.load(fh)
            except (OSError, json.JSONDecodeError):
                manifest = {"warning": "manifest unreadable"}
        items.append({"name": child.name, "path": str(child.relative_to(PROJECT_ROOT)), "manifest": manifest})

    if json_output:
        print(json.dumps({"snapshots": items}, ensure_ascii=True, indent=2))
        return

    if not items:
        print("[INFO] 暂无快照")
        return
    for item in items:
        manifest = item.get("manifest") or {}
        created = manifest.get("createdAt", "unknown") if isinstance(manifest, dict) else "unknown"
        reason = manifest.get("reason", "") if isinstance(manifest, dict) else ""
        print(f"- {item['name']} | {created} | {reason}")


def show_snapshot(name: str, json_output: bool = False) -> None:
    root = snapshot_dir(name)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        print(f"[FAIL] 找不到快照 manifest: {name}", file=sys.stderr)
        sys.exit(1)
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    if json_output:
        print(json.dumps(manifest, ensure_ascii=True, indent=2))
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))


def restore_snapshot(name: str, yes: bool = False) -> None:
    src_root = snapshot_dir(name)
    manifest_path = src_root / "manifest.json"
    if not manifest_path.is_file():
        print(f"[FAIL] 找不到快照: {name}", file=sys.stderr)
        sys.exit(1)
    if not yes:
        print("[FAIL] restore 会覆盖 config 与 tasks，请确认后加 --yes", file=sys.stderr)
        sys.exit(1)

    pre_name = "pre-restore-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    save_snapshot(pre_name, reason=f"automatic backup before restoring {name}")

    restored: List[str] = []
    missing: List[str] = []
    for rel in RESTORE_PATHS:
        src = src_root / rel
        dst = PROJECT_ROOT / rel
        if not src.is_file():
            missing.append(rel)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        restored.append(rel)

    append_audit(
        event_type="snapshot_restored",
        message=f"恢复配置快照: {name}",
        data={"name": name, "preRestoreSnapshot": pre_name, "restored": restored, "missing": missing},
    )
    print(f"[OK] 已恢复快照: {name}")
    print(f"[OK] 恢复前自动备份: {pre_name}")
    if missing:
        print(f"[WARN] 快照中缺失: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="配置快照 / 列表 / 恢复")
    sub = parser.add_subparsers(dest="command", required=True)

    p_save = sub.add_parser("save", help="保存配置快照")
    p_save.add_argument("--name", required=True, help="快照名称，仅允许 A-Z a-z 0-9 . _ -")
    p_save.add_argument("--reason", default="manual snapshot", help="保存原因")
    p_save.add_argument("--overwrite", action="store_true", help="覆盖同名快照")

    p_list = sub.add_parser("list", help="列出快照")
    p_list.add_argument("--json", action="store_true", help="输出 JSON")

    p_show = sub.add_parser("show", help="查看快照 manifest")
    p_show.add_argument("--name", required=True, help="快照名称")
    p_show.add_argument("--json", action="store_true", help="输出 JSON")

    p_restore = sub.add_parser("restore", help="恢复配置快照")
    p_restore.add_argument("--name", required=True, help="快照名称")
    p_restore.add_argument("--yes", action="store_true", help="确认覆盖 config 与 tasks")

    args = parser.parse_args()
    if args.command == "save":
        path = save_snapshot(args.name, reason=args.reason, overwrite=args.overwrite)
        print(f"[OK] 快照已保存: {path.relative_to(PROJECT_ROOT)}")
    elif args.command == "list":
        list_snapshots(json_output=args.json)
    elif args.command == "show":
        show_snapshot(args.name, json_output=args.json)
    elif args.command == "restore":
        restore_snapshot(args.name, yes=args.yes)


if __name__ == "__main__":
    main()
