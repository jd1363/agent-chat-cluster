## ADDED Requirements

### Requirement: Priority-ordered task selection
The scheduler SHALL read pending tasks from SQLite via `db.list_tasks(status='pending')` and sort them priority high > medium > low, then by `created` timestamp ascending within each priority band. No flat-file reads SHALL occur during a tick.

#### Scenario: Tasks dispatched in priority order
- **WHEN** pending tasks exist with mixed priorities (high, medium, low)
- **THEN** all high-priority tasks are evaluated before medium, and medium before low

#### Scenario: Tie-breaking within same priority
- **WHEN** two pending tasks share the same priority
- **THEN** the task with the earlier `created` timestamp is evaluated first

#### Scenario: No pending tasks
- **WHEN** `db.list_tasks(status='pending')` returns an empty list
- **THEN** the tick completes without dispatching anything and logs a summary of zero dispatches

### Requirement: Per-agent backpressure enforcement
Before dispatching any task to agent X, the scheduler SHALL count `in_progress` tasks for X via `db.list_tasks(status='in_progress', assignee=X)`. If the count is greater than or equal to the agent's `concurrency_cap` from `config/agents.json`, the scheduler SHALL skip all tasks assigned to X for the current tick.

#### Scenario: Agent at capacity
- **WHEN** agent X has `concurrency_cap=2` and 2 tasks already in_progress
- **THEN** no further tasks are dispatched to agent X in this tick

#### Scenario: Agent under capacity
- **WHEN** agent X has `concurrency_cap=2` and 1 task in_progress
- **THEN** up to 1 additional task may be dispatched to agent X

#### Scenario: Agent config missing or malformed
- **WHEN** `config/agents.json` cannot be read or is missing required fields
- **THEN** the tick fails with a clear error message and no tasks are dispatched

### Requirement: Dry-run mode (default)
When invoked without `--once` or `--loop`, or with `--dry-run`, the scheduler SHALL print which tasks it would dispatch without calling `executor_bridge` or mutating any task status in SQLite.

#### Scenario: Default invocation prints only
- **WHEN** the scheduler is run with no mode flags
- **THEN** it logs candidate tasks and backpressure decisions and exits without writing to SQLite

#### Scenario: Explicit --dry-run flag
- **WHEN** the scheduler is run with `--dry-run`
- **THEN** behavior is identical to the default no-flag invocation

### Requirement: Once mode
When invoked with `--once`, the scheduler SHALL execute one tick: evaluate pending tasks, enforce backpressure, and dispatch eligible tasks if `--execute-real` is also set, then exit.

#### Scenario: Single tick and exit
- **WHEN** the scheduler is run with `--once --execute-real`
- **THEN** one full tick runs, eligible tasks are dispatched via executor_bridge, and the process exits with code 0

#### Scenario: Once without --execute-real
- **WHEN** the scheduler is run with `--once` but without `--execute-real`
- **THEN** the tick runs in dry-run mode (no real dispatch) and exits

### Requirement: Loop mode
When invoked with `--loop N`, the scheduler SHALL run ticks repeatedly, sleeping N seconds between each tick, until terminated by SIGINT (Ctrl-C).

#### Scenario: Repeating ticks
- **WHEN** the scheduler is run with `--loop 30`
- **THEN** it runs a tick, sleeps 30 seconds, runs the next tick, and continues until interrupted

#### Scenario: Graceful stop on Ctrl-C
- **WHEN** the user sends SIGINT during a sleep interval
- **THEN** the scheduler exits cleanly without leaving a partial tick in an inconsistent state

### Requirement: Real execution gated behind --execute-real
`executor_bridge.execute_cli` and `executor_bridge.update_task_status` SHALL only be called when the `--execute-real` flag is present. Without it, the scheduler SHALL not mutate task state in SQLite regardless of run mode.

#### Scenario: Dispatch without --execute-real
- **WHEN** a task is eligible for dispatch and `--execute-real` is absent
- **THEN** the scheduler logs the would-be dispatch and does not call executor_bridge

#### Scenario: Dispatch with --execute-real
- **WHEN** a task is eligible and `--execute-real` is present
- **THEN** `executor_bridge.execute_cli` is called and task status is updated in SQLite

### Requirement: Audit trail per tick
The scheduler SHALL emit structured audit events at three points in every tick: tick start, each dispatch decision, and tick end.

- Tick start: `db.append_event(event_type='scheduler_tick_start', ...)` and `db.append_audit(event_type='scheduler_tick_start', ...)`
- Per dispatch: `db.append_event(event_type='scheduler_dispatch', ...)` and `db.append_audit(event_type='scheduler_dispatch', task_id=<id>, ...)`
- Tick end: `db.append_event(event_type='scheduler_tick_done', ...)` and `db.append_audit(event_type='scheduler_tick_done', ...)` with total dispatch count

#### Scenario: Audit written at tick start
- **WHEN** a tick begins
- **THEN** a `scheduler_tick_start` event is written to both events and audit tables before any dispatch logic runs

#### Scenario: Audit written per dispatch
- **WHEN** a task is dispatched (real or dry-run notation)
- **THEN** a `scheduler_dispatch` event is written with the task_id

#### Scenario: Audit written at tick end
- **WHEN** a tick completes
- **THEN** a `scheduler_tick_done` event is written with the count of tasks dispatched in the tick

### Requirement: Batch resilience - no abort on single task failure
If dispatching an individual task raises an exception (from executor_bridge or db), the scheduler SHALL log the error, mark that task as failed in SQLite (when `--execute-real` is set), and continue processing remaining eligible tasks.

#### Scenario: One task fails, others continue
- **WHEN** executor_bridge raises an exception for task T
- **THEN** task T is marked failed, the error is logged, and the next eligible task is processed

#### Scenario: All tasks fail
- **WHEN** every eligible task fails dispatch
- **THEN** the scheduler completes the tick with zero successful dispatches and exits with a non-zero code

### Requirement: Safety constraints
The scheduler SHALL NOT perform global broadcast, self-heal, or external-send operations. It SHALL NOT auto-promote or auto-assign tasks not already assigned in SQLite.

#### Scenario: No unassigned task auto-assignment
- **WHEN** a pending task has no assignee set
- **THEN** the scheduler skips that task and logs a warning

#### Scenario: No external communication
- **WHEN** any tick runs
- **THEN** no HTTP requests, file writes outside SQLite, or shell commands outside executor_bridge are made
