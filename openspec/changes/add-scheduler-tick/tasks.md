## 1. Scaffold

- [ ] 1.1 Create `scripts/scheduler_tick.py` with UTF-8 output enforcement and argparse for `--dry-run`, `--once`, `--loop N`, `--execute-real`
- [ ] 1.2 Add module-level deprecation comment to `scripts/queue_dispatch.py` marking it as replaced by `scheduler_tick.py`

## 2. Config Loading

- [ ] 2.1 Implement agent config loader: read `config/agents.json`, extract agent list and `concurrency_cap` per agent, raise a clear error if file is missing or malformed
- [ ] 2.2 Add validation that rejects a tick start if any required agent config fields are absent

## 3. Task Selection

- [ ] 3.1 Implement `fetch_pending_tasks()`: call `db.list_tasks(status='pending')` and sort by priority (high > medium > low) then `created` ASC
- [ ] 3.2 Implement `count_in_progress(assignee)`: call `db.list_tasks(status='in_progress', assignee=assignee)` and return the count
- [ ] 3.3 Implement backpressure check: skip tasks for agents at or above `concurrency_cap`, log a per-agent skip message

## 4. Dispatch Logic

- [ ] 4.1 Implement `dispatch_task(task, dry_run)`: in dry-run mode log the would-be dispatch; in real mode call `executor_bridge.execute_cli` and `executor_bridge.update_task_status`
- [ ] 4.2 Wrap `dispatch_task` in a try/except: on failure log the error, call `db.update_task(task_id, status='failed')` (real mode only), and continue to next task
- [ ] 4.3 Skip tasks with no assignee set and log a warning per the safety constraint

## 5. Audit Trail

- [ ] 5.1 Emit `scheduler_tick_start` via `db.append_event` + `db.append_audit` at the top of each tick before any dispatch logic
- [ ] 5.2 Emit `scheduler_dispatch` via `db.append_event` + `db.append_audit` for each dispatched task (pass `task_id`)
- [ ] 5.3 Emit `scheduler_tick_done` via `db.append_event` + `db.append_audit` at the end of each tick with total dispatch count

## 6. Run Modes

- [ ] 6.1 Implement `run_once()`: execute one tick and exit with code 0 on success, non-zero if all tasks failed
- [ ] 6.2 Implement `run_loop(interval_seconds)`: call `run_once()` in a loop, sleep N seconds between ticks, exit cleanly on KeyboardInterrupt
- [ ] 6.3 Wire argparse flags to the correct mode: no flags or `--dry-run` -> dry-run tick and exit; `--once` -> `run_once()`; `--loop N` -> `run_loop(N)`

## 7. Verification

- [ ] 7.1 Run `python scripts/scheduler_tick.py --dry-run` against live `data/cluster.db` and confirm audit events are written and no task state is mutated
- [ ] 7.2 Run `python scripts/scheduler_tick.py --once --execute-real` in a controlled window and confirm a pending task transitions to in_progress/done and audit rows appear
- [ ] 7.3 Confirm `queue_dispatch.py` still runs without error (backward compatibility, no deletion)
