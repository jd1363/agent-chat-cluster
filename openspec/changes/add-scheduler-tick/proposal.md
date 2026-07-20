## Why

`queue_dispatch.py` reads from the legacy flat-file `tasks/tasks.json` and has no backpressure, no audit trail, and no loop mode, making it unsuitable for continuous operation in the multi-agent cluster. A proper scheduler is needed that drives the SQLite data layer and respects per-agent concurrency caps.

## What Changes

- **New**: `scheduler_tick.py` - a SQLite-backed scheduler that replaces manual batch dispatch.
- **Removed**: dependency on `tasks/tasks.json` for dispatch (file may remain for seeding but is no longer the source of truth at runtime).
- Dispatch priority order: `high > medium > low`, then by `created` timestamp ascending.
- Backpressure: per-agent in-progress count checked against `concurrency_cap` before dispatch.
- Three run modes: `--dry-run` (default, no real execution), `--once` (single tick), `--loop N` (tick every N seconds).
- Audit events written via `db.append_event` + `db.append_audit` at tick start, each dispatch, and tick end.
- Real execution gated behind explicit `--execute-real` flag.

## Capabilities

### New Capabilities

- `scheduler-tick`: Priority-ordered, backpressure-aware task dispatcher backed by SQLite with dry-run/once/loop modes and a full audit trail.

### Modified Capabilities

<!-- None: queue_dispatch.py has no existing spec. -->

## Impact

- **Replaces**: `scripts/queue_dispatch.py` (kept on disk but deprecated).
- **Reads**: `db.list_tasks(status='pending')`, `db.list_tasks(status='in_progress', assignee=<agent>)`.
- **Writes**: `db.update_task(task_id, status=...)` on dispatch, `db.append_audit`, `db.append_event`.
- **Calls**: `executor_bridge.execute_cli` / `executor_bridge.update_task_status` for real execution path.
- **Config**: `config/agents.json` for agent list and `concurrency_cap` per agent.
- **No new dependencies**: stdlib only.
