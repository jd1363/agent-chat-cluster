## Context

`queue_dispatch.py` is a manual batch script that reads from `tasks/tasks.json` (a flat-file legacy store). It has no backpressure, no audit trail, and no loop mode. The cluster's real data layer is SQLite (`data/cluster.db`) managed through `scripts/db.py`. A proper scheduler must drive the SQLite layer to be viable for continuous multi-agent operation.

Current state: tasks are dispatched by running `queue_dispatch.py` by hand. There is no mechanism to prevent overloading an agent or to observe what was dispatched and why.

Constraints: stdlib only, Windows + Python 3, UTF-8 output enforcement, single-process (no threads/async), SQLite concurrency handled by serializing reads and writes within a tick.

## Goals / Non-Goals

**Goals:**
- Replace manual `queue_dispatch.py` with `scheduler_tick.py` driven by SQLite.
- Enforce per-agent concurrency caps before dispatching any task.
- Dispatch in deterministic priority order: high > medium > low, then created ASC.
- Emit structured audit events at tick start, each dispatch decision, and tick end.
- Support three run modes: dry-run (default), once, loop N seconds.
- Gate real execution behind an explicit `--execute-real` flag.

**Non-Goals:**
- Automatic global broadcast, self-heal, or external-send of any kind.
- Multi-process or async scheduling.
- Replacing or modifying `db.py` or `executor_bridge.py` internals.
- Deleting `queue_dispatch.py` (it is deprecated but kept on disk).
- Reading from `tasks/tasks.json` at dispatch time (may remain for seeding only).

## Decisions

### Decision: SQLite as the single source of truth for task state

`db.list_tasks(status='pending')` and `db.list_tasks(status='in_progress', assignee=<agent>)` are the only inputs to the scheduling decision. No flat-file reads at dispatch time.

**Why over flat-file:** SQLite provides atomic updates and a consistent read view across a tick. Flat-file reads are racy and cannot be updated transactionally.

### Decision: Per-agent backpressure via concurrency_cap from config/agents.json

Before dispatching any task assigned to agent X, count `in_progress` tasks for X. If count >= `concurrency_cap`, skip all tasks for X in this tick.

**Why at config level:** Caps are operator-controlled and differ per agent capability. Hard-coding or deriving from task counts would lose that signal.

**Alternative considered:** Global concurrency cap. Rejected because different agents have different throughput - a single global cap would either starve fast agents or overload slow ones.

### Decision: Dry-run is the default mode

Without `--once` or `--loop N`, the scheduler prints what it would dispatch but does not call `executor_bridge` or mutate task state.

**Why:** Prevents accidental mass dispatch during development or misconfiguration. Real execution is always an explicit opt-in.

### Decision: Audit via db.append_event + db.append_audit at three points

Emit `scheduler_tick_start` at the top of each tick, `scheduler_dispatch` per dispatched task, and `scheduler_tick_done` at the end with a summary count.

**Why:** These three points are the minimum needed to reconstruct "what happened in a tick" from the audit log without querying task state mid-run.

### Decision: Do not abort the full batch on a single task failure

If dispatching task T fails (executor_bridge raises), log the error, mark T as failed, and continue to the next task.

**Why over fail-fast:** A single bad task (malformed command, missing assignee) should not block all other ready tasks. Consistent with the project's existing stdlib-first, no-exception-abort convention.

## Risks / Trade-offs

- **SQLite write contention during loop mode** - If another process writes to cluster.db during a tick, SQLite's default locking may cause a brief retry delay. Mitigation: keep tick logic short; use WAL mode if contention becomes measurable (out of scope for this change).
- **concurrency_cap misconfiguration** - If `config/agents.json` is missing or malformed, the scheduler cannot enforce caps. Mitigation: fail the tick with a clear error message rather than dispatching uncapped.
- **No task re-prioritization within a tick** - Priority order is fixed at the start of the tick. Tasks promoted mid-tick are not re-evaluated until the next tick. Acceptable for the current MVP cadence.
- **Loop mode has no signal-based stop** - `--loop N` relies on Ctrl-C (KeyboardInterrupt) for termination. Mitigation: document the expected shutdown mechanism clearly.

## Migration Plan

1. Add `scheduler_tick.py` to `scripts/`.
2. Run in `--dry-run` mode against the live cluster.db to validate output matches expectations.
3. Run `--once --execute-real` in a controlled window to verify end-to-end dispatch.
4. Switch recurring dispatch to `--loop 30 --execute-real` (or equivalent cron/Task Scheduler entry).
5. Mark `queue_dispatch.py` deprecated in its module docstring; do not delete.

Rollback: stop `scheduler_tick.py`, resume manual `queue_dispatch.py` runs. No schema changes are made by this feature.

## Open Questions

- Should `--loop N` write a PID file to prevent duplicate scheduler instances? (Not in scope for initial implementation; operator responsibility for now.)
- Should `scheduler_tick_done` include per-agent dispatch counts in the audit payload, or just a total? (Prefer per-agent for observability; confirm with team before implementing.)
