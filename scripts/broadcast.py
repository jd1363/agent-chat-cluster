#!/usr/bin/env python3
"""
broadcast.py - Send one message to all enabled Agents.

Usage:
    python scripts/broadcast.py --message "maintenance notice"

Uses only Python standard library modules.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from send_message import send_broadcast  # type: ignore
from event_log import build_event, append_event  # type: ignore


def main() -> None:
    parser = argparse.ArgumentParser(description="Broadcast a message to all enabled Agents")
    parser.add_argument("--message", required=True, help="Message content")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    parser.add_argument(
        "--manual-approval",
        action="store_true",
        help="Confirm human approval when globalBroadcast is disabled by policy",
    )
    args = parser.parse_args()

    result = send_broadcast(args.message, manual_approval=args.manual_approval)
    try:
        _evt = build_event(
            event_type="message.broadcast",
            source="broadcast",
            correlation_id=result["parent"]["id"],
            payload={
                "messageId": result["parent"]["id"],
                "from": "master",
                "recipients": len(result["children"]),
                "subject": args.message[:80],
            },
        )
        append_event(_evt)
    except Exception as e:
        print(f"[WARN] 事件日志追加失败: {e}")
    if args.json_output:
        print(json.dumps({"ok": True, "broadcast": result}, ensure_ascii=False, indent=2))
    else:
        print(f"[OK] {result['parent']['id']} broadcast to {len(result['children'])} agents")


if __name__ == "__main__":
    main()
