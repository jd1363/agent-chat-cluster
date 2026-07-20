You are implementing a Python script for an existing multi-agent cluster project. Write ONLY the file scripts/scheduler_tick.py. Follow the spec contract exactly. Use Python 3 standard library only. Force UTF-8 stdout/stderr at the top to avoid Windows GBK mojibake. Write ALL comments/strings in English ASCII only (no unicode dashes, use regular '-').

## Context: existing modules you MUST reuse (do not reinvent)

scripts/db.py (import as: `import db` when run from scripts/, or `from scripts import db`) provides:
- db.list_tasks(status=None, assignee=None, limit=200) -> list[dict]
- db.get_task(task_id) -> dict | None
- db.update_task(task_id, **fields) -> dict | None
- db.append_audit(event_type: str, message: str, task_id=None, data: dict=None, environment=None) -> None
- db.append_event(event_type: str, source: str, correlation_id=None, causation_id=None, payload: dict=None, policy_snapshot=None, status='pending') -> str

A task dict has keys: id, title, description, status, priority, assignee, output, notes, created_at, updated_at.
Task statuses used: pending, in_progress, done, failed, blocked, cancelled.
priority values: high, medium, low.

config/agents.json structure: {"schemaVersion":..., "agents":[ {"id","role","type","enabled","executor":{...}, ...}, ... ]}.
NOTE: agents.json entries currently do NOT have a "concurrency_cap" field. Your loader must default concurrency_cap to 1 when the field is absent, and read it from the agent entry when present. Only consider agents with enabled==true as dispatchable.

## Real dispatch: reuse existing dispatch_task.py via subprocess (same pattern as queue_dispatch.py)
Real execution is done by calling the existing script via subprocess:
  python scripts/dispatch_task.py --task-id <ID> --assignee <AGENT> --execute-real
Do NOT call executor_bridge directly. Capture returncode/stdout/stderr. A non-zero return means dispatch failure.

## Behavior contract (from OpenSpec spec)

1. Priority-ordered selection: read pending tasks via db.list_tasks(status='pending'), sort by priority high>medium>low then created_at ascending. No flat-file reads.

2. Per-agent backpressure: before dispatching to agent X, count in_progress via db.list_tasks(status='in_progress', assignee=X). If count >= concurrency_cap (default 1), skip all tasks for X this tick. Track dispatches made during the tick so the in-tick count also counts toward the cap.

3. Skip tasks whose assignee is empty/None: log a warning, do not auto-assign.

4. Dispatch:
   - dry-run: log the would-be dispatch (task id, assignee, priority), do NOT call subprocess, do NOT mutate SQLite.
   - real (--execute-real): call dispatch_task.py via subprocess. On success continue; on failure log error and call db.update_task(task_id, status='failed', notes=...) then continue to next task (do not abort the whole tick).

5. Run modes (argparse):
   - no mode flag OR --dry-run  -> single dry-run tick, then exit
   - --once                     -> one real tick (real dispatch only if --execute-real also set; else dry-run tick)
   - --loop N                   -> repeat run_once every N seconds, sleep between ticks, exit cleanly on KeyboardInterrupt (SIGINT)
   - --execute-real             -> gate for real dispatch. Without it, no subprocess call and no SQLite mutation regardless of mode.

6. Audit trail per tick (call BOTH append_event and append_audit):
   - tick start: event_type='scheduler_tick_start' (source='scheduler_tick')
   - per dispatch: event_type='scheduler_dispatch' with task_id
   - tick end: event_type='scheduler_tick_done' with total dispatch count in payload/data
   In dry-run also emit these audit events (a tick still ran) but mark dry_run=True in the data/payload.

7. Exit codes: run_once returns 0 on success; if there were eligible tasks and ALL of them failed dispatch, exit non-zero.

8. Safety: no HTTP, no global broadcast, no self-heal, no external send. Only SQLite + the dispatch_task.py subprocess.

## Structure
- UTF-8 setup, imports, robust sys.path so `import db` works whether run as `python scripts/scheduler_tick.py` from project root.
- load_agent_config() -> dict[agent_id] = {'enabled':bool, 'concurrency_cap':int}; raise clear error if file missing/malformed.
- fetch_pending_tasks() -> sorted list
- count_in_progress(assignee) -> int
- dispatch_task(task, dry_run, execute_real) -> bool  (returns True if dispatched/would-dispatch ok)
- run_once(dry_run, execute_real) -> int (exit code)
- run_loop(interval, execute_real)
- main() with argparse
- if __name__ == '__main__': sys.exit(main())

Output the COMPLETE file content. Do not include explanations outside the code. Start the file with a module docstring describing usage.
