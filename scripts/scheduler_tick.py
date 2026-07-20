import sys
import os
import json
import time
import argparse
from typing import Dict, List, Optional, Any

# Insert script directory into sys.path so that 'import db' and 'import executor_bridge' work
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

import db
import executor_bridge

# ---------------------------------------------------------------------------
# UTF-? output enforcement
# ---------------------------------------------------------------------------
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def load_agents() -> Dict[str, Dict[str, Any]]:
    """Read config/agents.json and return {agent_id: {concurrency_cap, enabled, executor}}."""
    config_path = os.path.join(os.path.dirname(_script_dir), 'config', 'agents.json')
    if not os.path.isfile(config_path):
        raise RuntimeError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    if isinstance(raw, list):
        agents_list = raw
    elif isinstance(raw, dict) and 'agents' in raw:
        agents_list = raw['agents']
    else:
        raise RuntimeError("agents.json must be a list or an object with an 'agents' key")

    result = {}
    for agent in agents_list:
        if 'id' not in agent:
            raise RuntimeError("Each agent entry must have an 'id' field")
        agent_id = agent['id']
        concurrency_cap = agent.get('concurrency_cap', 1)
        enabled = agent.get('enabled', True)
        executor = agent.get('executor', {})
        result[agent_id] = {
            'concurrency_cap': concurrency_cap,
            'enabled': enabled,
            'executor': executor,
        }
    return result

# ---------------------------------------------------------------------------
# Task selection
# ---------------------------------------------------------------------------
PRIORITY_RANK = {'high': 0, 'medium': 1, 'low': 2}

def fetch_pending_tasks() -> List[Dict[str, Any]]:
    """Fetch pending tasks sorted by priority then created."""
    tasks = db.list_tasks(status='pending')
    def sort_key(t):
        priority = t.get('priority', 'unknown')
        rank = PRIORITY_RANK.get(priority, 3)
        created = t.get('created', '')
        return (rank, created)
    tasks.sort(key=sort_key)
    return tasks

def count_in_progress(assignee: str) -> int:
    """Return number of in-rogress tasks for an assignee."""
    return len(db.list_tasks(status='in_progress', assignee=assignee))

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
def dispatch_task(task: Dict[str, Any], agents: Dict[str, Dict[str, Any]], real: bool) -> str:
    """Dispatch a single task. Returns status string: 'success', 'failed', 'dryrun'."""
    task_id = task['id']
    assignee = task.get('assignee')
    if not assignee:
        print(f"Warning: Task {task_id} has no assignee, skipping")
        return 'skipped'

    if assignee not in agents:
        print(f"Warning: Task {task_id} assignee '{assignee}' not in agents, skipping")
        return 'skipped'

    agent = agents[assignee]
    if not agent['enabled']:
        print(f"Warning: Agent '{assignee}' is disabled, skipping task {task_id}")
        return 'skipped'

    executor = agent['executor']
    work_dir = executor.get('workDir', '.')
    timeout = executor.get('timeoutSeconds', 60)
    max_output_kb = executor.get('maxOutputKB', 100)

    # Build the command via executor_bridge so Windows .ps1/.cmd resolution and
    # {prompt} substitution are handled consistently (do NOT hand-roll it).
    prompt_text = task.get('description') or task.get('title', '')
    full_command = executor_bridge.build_command_args(executor, prompt_text)

    if not real:
        print(f"[DRY--UN] Would dispatch task {task_id} to {assignee}: {' '.join(full_command)}")
        db.append_event('scheduler_dispatch', source='scheduler_tick',
                        payload={'task_id': task_id, 'dry_run': True})
        db.append_audit('scheduler_dispatch', f'Dry--un dispatch of task {task_id}',
                        task_id=task_id)
        return 'dryrun'

    try:
        result = executor_bridge.execute_cli(
            command=full_command,
            cwd=work_dir,
            timeout=timeout,
            max_output_kb=max_output_kb,
        )
        # execute_cli returns keys: success(bool), output, error, quality
        output = result.get('output', '')
        success = result.get('success', False)
        status = 'completed' if success else 'failed'
        # Write status to SQLite (the single source of truth), NOT the legacy
        # tasks.json that executor_bridge.update_task_status still writes to.
        err = result.get('error') or ''
        db.update_task(
            task_id=task_id,
            status=status,
            output=output,
            notes=f"scheduler_tick real run; success={success}; {err}"[:500],
        )
        db.append_event('scheduler_dispatch', source='scheduler_tick',
                        payload={'task_id': task_id, 'status': status})
        db.append_audit('scheduler_dispatch',
                        f'Dispatched task {task_id} -> {status}',
                        task_id=task_id)
        return status
    except Exception as e:
        print(f"Error dispatching task {task_id}: {e}")
        db.update_task(task_id=task_id, status='failed')
        db.append_event('scheduler_dispatch', source='scheduler_tick',
                        payload={'task_id': task_id, 'error': str(e)})
        db.append_audit('scheduler_dispatch',
                        f'Dispatch failed for task {task_id}: {e}',
                        task_id=task_id)
        return 'failed'

# ---------------------------------------------------------------------------
# Tick logic
# ---------------------------------------------------------------------------
def run_once(real: bool) -> int:
    """Execute one tick. Returns 0 on success, 1 if ALL attempted tasks failed."""
    agents = load_agents()
    pending = fetch_pending_tasks()

    # Audit start
    db.append_event('scheduler_tick_start', source='scheduler_tick')
    db.append_audit('scheduler_tick_start', 'Tick starting')

    attempted = 0
    failed = 0

    for task in pending:
        assignee = task.get('assignee')
        if not assignee:
            print(f"Warning: Task {task['id']} has no assignee, skipping")
            continue
        if assignee not in agents:
            print(f"Warning: Task {task['id']} assignee '{assignee}' not in agents, skipping")
            continue
        agent = agents[assignee]
        if not agent['enabled']:
            print(f"Warning: Agent '{assignee}' is disabled, skipping task {task['id']}")
            continue

        # Backpressure check
        cap = agent['concurrency_cap']
        in_progress = count_in_progress(assignee)
        if in_progress >= cap:
            print(f"Skipping task {task['id']} assignee {assignee}: "
                  f"in_progress {in_progress} >= cap {cap}")
            continue

        result = dispatch_task(task, agents, real)
        if result == 'failed':
            failed += 1
        attempted += 1

    # Audit end
    total = len(pending)
    db.append_event('scheduler_tick_done', source='scheduler_tick',
                    payload={'total': total, 'attempted': attempted, 'failed': failed})
    db.append_audit('scheduler_tick_done',
                    f'Tick completed: {total} pending, {attempted} attempted, {failed} failed')

    # Return 1 only if at least one task was attempted AND every attempted task failed
    if attempted > 0 and failed == attempted:
        return 1
    return 0

def run_loop(interval: int, real: bool) -> None:
    """Loop run_once indefinitely, sleeping interval seconds between ticks."""
    print(f"Starting scheduler loop (interval={interval}s, real={real})")
    try:
        while True:
            rc = run_once(real)
            if rc != 0:
                print("Tick returned non-ero -?all attempted tasks failed")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nScheduler loop interrupted, exiting.")

# ---------------------------------------------------------------------------
# Main / argparse
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description='Scheduler tick -?dispatches pending tasks')
    parser.add_argument('--dry-run', action='store_true',
                        help='Force dry-un mode (default if no --execute-real)')
    parser.add_argument('--once', action='store_true',
                        help='Run a single tick')
    parser.add_argument('--loop', type=int, metavar='N',
                        help='Run in a loop with N seconds between ticks')
    parser.add_argument('--execute-real', action='store_true',
                        help='Actually execute tasks (default is dry-un)')
    args = parser.parse_args()

    # Determine real execution
    # --dry-run overrides --execute-real
    if args.dry_run:
        real = False
    elif args.execute_real:
        real = True
    else:
        real = False

    if args.loop is not None:
        run_loop(args.loop, real)
    elif args.once:
        sys.exit(run_once(real))
    else:
        # No flags or --dry-run -> single dry-un tick
        run_once(real)

if __name__ == '__main__':
    main()
