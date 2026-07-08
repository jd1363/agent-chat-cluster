#!/usr/bin/env python3
"""
Agent Chat Cluster - Web Dashboard Server
Complete rewrite: REST GET/POST + SSE real-time push, stdlib only.

Usage:
    python web/server.py [--port 8765] [--host 127.0.0.1]
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen
from urllib.error import URLError

# --- Project paths ---
WEB_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_DIR.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
POLICIES_FILE = PROJECT_ROOT / "config" / "policies.json"
STATE_FILE = PROJECT_ROOT / "state" / "system_state.json"
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"
MESSAGES_DIR = PROJECT_ROOT / "logs" / "messages"
COST_DIR = PROJECT_ROOT / "logs" / "cost"
EVENTS_DIR = PROJECT_ROOT / "logs" / "events"
RUNS_DIR = PROJECT_ROOT / "logs" / "runs"

# Import SQLite data layer
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    from db import (
        list_tasks as db_list_tasks,
        get_task_stats as db_get_task_stats,
        search_tasks as db_search_tasks,
        list_audit as db_list_audit,
        get_cost_summary as db_get_cost_summary,
        list_events as db_list_events,
        list_messages as db_list_messages,
    )
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

# --- Subprocess env for POST handlers ---
SUB_ENV = {
    **os.environ,
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
}

_RUNNING_PIDS = {}  # task_id → subprocess.Popen


# ===================================================================
#  Data helpers
# ===================================================================

def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def read_jsonl_dir(dirpath, limit=50):
    result = []
    pattern = os.path.join(dirpath, "*.jsonl")
    files = sorted(glob.glob(pattern))
    for fp in reversed(files):
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        result.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            continue
        if len(result) >= limit:
            break
    return result[:limit]


# ===================================================================
#  GET API data functions
# ===================================================================

def get_tasks():
    if DB_AVAILABLE:
        tasks = db_list_tasks(limit=500)
        # Map snake_case to camelCase for frontend compat
        mapped = []
        for t in tasks:
            mapped.append({
                "id": t["id"],
                "title": t["title"],
                "description": t.get("description", ""),
                "status": t["status"],
                "priority": t["priority"],
                "assignee": t.get("assignee"),
                "createdAt": t.get("created_at", ""),
                "updatedAt": t.get("updated_at", ""),
                "output": t.get("output"),
                "notes": t.get("notes", ""),
            })
        stats = db_get_task_stats()
        return {"tasks": mapped, "stats": stats}
    # Fallback: JSON file
    data = read_json(TASKS_FILE, {"tasks": []})
    tasks = data.get("tasks", [])
    stats = {}
    for t in tasks:
        s = t.get("status", "unknown")
        stats[s] = stats.get(s, 0) + 1
    return {"tasks": tasks, "stats": stats}


def get_agents():
    data = read_json(AGENTS_FILE, {"agents": []})
    agents = data.get("agents", [])
    # Enrich each agent with displayName and executor info
    for a in agents:
        if "displayName" not in a or not a.get("displayName"):
            a["displayName"] = a.get("id", "unknown")
        executor = a.get("executor") or a.get("backend")
        if executor:
            a["executorCommand"] = executor.get("command", "N/A")
            a["executorType"] = executor.get("type", "N/A")
        else:
            a["executorCommand"] = "N/A"
            a["executorType"] = "N/A"
    return {"agents": agents}


def get_audit(limit=50):
    if DB_AVAILABLE:
        entries = db_list_audit(limit=limit)
        # Map snake_case to camelCase
        for e in entries:
            e["eventType"] = e.pop("event_type", "")
            e["taskId"] = e.pop("task_id", None)
        return {"entries": entries}
    # Fallback: JSONL
    entries = read_jsonl_dir(AUDIT_DIR, limit)
    entries.reverse()
    return {"entries": entries[:limit]}


def get_messages(limit=30):
    if DB_AVAILABLE:
        entries = db_list_messages(limit=limit)
        # Map snake_case to camelCase
        for e in entries:
            e["from"] = e.pop("from_user", "")
            e["to"] = e.pop("to_user", "")
            e["type"] = e.pop("msg_type", None)
        return {"entries": entries}
    # Fallback: JSONL
    entries = read_jsonl_dir(MESSAGES_DIR, limit)
    entries.reverse()
    return {"entries": entries[:limit]}


def get_cost():
    if DB_AVAILABLE:
        return db_get_cost_summary()
    # Fallback: JSONL
    entries = read_jsonl_dir(COST_DIR, 10000)
    total_cost = 0.0
    total_tokens = 0
    by_agent = {}
    for e in entries:
        cost = e.get("estimatedCost", 0)
        tokens = e.get("totalTokens", 0)
        agent = e.get("agentId", "unknown")
        total_cost += cost
        total_tokens += tokens
        if agent not in by_agent:
            by_agent[agent] = {"cost": 0, "tokens": 0}
        by_agent[agent]["cost"] += cost
        by_agent[agent]["tokens"] += tokens
    return {
        "totalCost": round(total_cost, 4),
        "totalTokens": total_tokens,
        "byAgent": by_agent,
        "entries": entries[-20:],
    }


def get_events(limit=50):
    if DB_AVAILABLE:
        entries = db_list_events(limit=limit)
        # Map snake_case to camelCase
        for e in entries:
            e["eventType"] = e.pop("event_type", "")
            e["correlationId"] = e.pop("correlation_id", None)
            e["causationId"] = e.pop("causation_id", None)
            e["eventId"] = e.pop("event_id", "")
        return {"entries": entries}
    # Fallback: JSONL
    entries = read_jsonl_dir(EVENTS_DIR, limit)
    entries.reverse()
    return {"entries": entries[:limit]}


def get_policies():
    data = read_json(POLICIES_FILE, {})
    return data.get("policies", {})


def get_state():
    return read_json(STATE_FILE, {})


def get_alerts():
    tasks_data = get_tasks()
    agents_data = get_agents()
    msg_data = get_messages(500)

    alerts = []
    failed_count = tasks_data["stats"].get("failed", 0)
    pending_count = tasks_data["stats"].get("pending", 0)
    disabled_agents = [a for a in agents_data["agents"] if not a.get("enabled", False)]
    unacked = [m for m in msg_data["entries"] if m.get("status") != "acked"]

    if failed_count > 0:
        alerts.append({"level": "red", "text": f"{failed_count} \u4e2a\u5931\u8d25\u4efb\u52a1"})
    if len(unacked) > 0:
        alerts.append({"level": "yellow", "text": f"{len(unacked)} \u6761\u672a ACK \u6d88\u606f"})
    if len(disabled_agents) > 0:
        alerts.append({"level": "yellow", "text": f"{len(disabled_agents)} \u4e2a Agent \u5df2\u7981\u7528"})
    if pending_count > 0:
        alerts.append({"level": "yellow", "text": f"{pending_count} \u4e2a\u5f85\u5904\u7406\u4efb\u52a1"})

    level = "green"
    if any(a["level"] == "red" for a in alerts):
        level = "red"
    elif any(a["level"] == "yellow" for a in alerts):
        level = "yellow"

    return {
        "level": level,
        "alerts": alerts,
        "counts": {
            "failed": failed_count,
            "pending": pending_count,
            "unacked": len(unacked),
            "disabledAgents": len(disabled_agents),
        },
    }


def get_air_quality(params):
    """
    Query real-time air quality via Open-Meteo Air Quality API (no API key required).
    Params: lat, lon (optional; defaults to Beijing).
    """
    try:
        lat = float(params.get("lat", ["39.9042"])[0])
        lon = float(params.get("lon", ["116.4074"])[0])
    except (TypeError, ValueError):
        return {"error": "Invalid lat/lon parameters"}

    url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality?"
        f"latitude={lat}&longitude={lon}"
        f"&current=us_aqi,pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone"
        f"&timezone=auto"
    )

    try:
        with urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, json.JSONDecodeError, TimeoutError) as e:
        return {"error": f"Failed to fetch air quality data: {e}"}

    current = data.get("current", {})
    result = {
        "location": {
            "latitude": lat,
            "longitude": lon,
            "timezone": data.get("timezone", "auto"),
        },
        "current": {
            "us_aqi": current.get("us_aqi"),
            "pm10": current.get("pm10"),
            "pm2_5": current.get("pm2_5"),
            "carbon_monoxide": current.get("carbon_monoxide"),
            "nitrogen_dioxide": current.get("nitrogen_dioxide"),
            "sulphur_dioxide": current.get("sulphur_dioxide"),
            "ozone": current.get("ozone"),
            "time": current.get("time"),
        },
    }
    return result


def serve_html():
    html_path = WEB_DIR / "dashboard.html"
    with open(html_path, encoding="utf-8") as f:
        return f.read()


# ===================================================================
#  POST API helpers
# ===================================================================

def run_script(script_name, args_list):
    script_path = SCRIPTS_DIR / script_name
    if not script_path.is_file():
        return False, f"Script not found: {script_name}"
    cmd = [sys.executable, str(script_path)] + args_list
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=SUB_ENV,
            timeout=30,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            return False, err
        return True, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "Script timed out (30s)"
    except Exception as e:
        return False, str(e)


def find_task_by_id(task_id):
    data = read_json(TASKS_FILE, {"tasks": []})
    for t in data.get("tasks", []):
        if t.get("id") == task_id:
            return t
    return None


# ===================================================================
#  SSE helpers
# ===================================================================

def get_latest_audit_file():
    pattern = os.path.join(AUDIT_DIR, "*.jsonl")
    files = sorted(glob.glob(pattern))
    return Path(files[-1]) if files else None


def find_task_log_files(task_id):
    files = {}
    if not RUNS_DIR.is_dir():
        return files
    for f in RUNS_DIR.iterdir():
        if f.name.startswith(task_id) and f.is_file():
            files[f.name] = 0
    return files


def read_file_from(path, offset=0, max_bytes=65536):
    try:
        size = path.stat().st_size
        if size <= offset:
            return "", offset
        with open(path, encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            content = f.read(max_bytes)
        return content, size
    except (FileNotFoundError, OSError):
        return "", offset


# ===================================================================
#  HTTP Handler
# ===================================================================

class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._set_cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            content_length = 0
        if content_length == 0:
            self._json({"ok": False, "error": "empty body"})
            return None
        raw = self.rfile.read(content_length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json({"ok": False, "error": f"invalid JSON: {e}"})
            return None

    def _start_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._set_cors()
        self.end_headers()

    def _sse_write(self, event_type, data):
        payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    # --- GET ---

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path in ("/", "/dashboard.html"):
            html = serve_html()
            self._send_html(html)
            return

        if path == "/api/tasks":
            self._json(get_tasks())
        elif path == "/api/agents":
            self._json(get_agents())
        elif path == "/api/audit":
            limit = int(params.get("limit", ["50"])[0])
            self._json(get_audit(limit))
        elif path == "/api/messages":
            limit = int(params.get("limit", ["30"])[0])
            self._json(get_messages(limit))
        elif path == "/api/cost":
            self._json(get_cost())
        elif path == "/api/events":
            limit = int(params.get("limit", ["50"])[0])
            self._json(get_events(limit))
        elif path == "/api/policies":
            self._json(get_policies())
        elif path == "/api/state":
            self._json(get_state())
        elif path == "/api/alerts":
            self._json(get_alerts())
        elif path == "/api/air_quality":
            self._json(get_air_quality(params))
        elif path == "/api/stream/events":
            self._sse_events()
        elif path.startswith("/api/stream/tasks/") and path.endswith("/logs"):
            task_id = path.split("/")[4]
            self._sse_task_logs(task_id)
        else:
            self._json({"error": "not found"}, status=404)

    # --- POST ---

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        body_data = self._read_json_body()
        if body_data is None:
            return

        if path == "/api/tasks/create":
            self._post_create_task(body_data)
        elif path == "/api/tasks/dispatch":
            self._post_dispatch_task(body_data)
        elif path == "/api/tasks/complete":
            self._post_complete_task(body_data)
        elif path == "/api/tasks/cancel":
            self._post_cancel_task(body_data)
        elif path == "/api/tasks/execute":
            self._post_execute_task(body_data)
        elif path == "/api/tasks/kill":
            self._post_kill(body_data)
        elif path == "/api/tasks/rerun":
            self._post_rerun(body_data)
        elif path == "/api/tasks/batch":
            self._post_batch(body_data)
        elif path == "/api/messages/send":
            self._post_send_message(body_data)
        else:
            self._json({"ok": False, "error": "unknown endpoint"}, status=404)

    # --- POST handlers ---

    def _post_create_task(self, body):
        title = body.get("title", "").strip()
        description = body.get("description", "").strip()
        priority = body.get("priority", "medium")
        if not title:
            self._json({"ok": False, "error": "title is required"})
            return
        args = ["--title", title, "--priority", priority]
        if description:
            args += ["--description", description]
        ok, output = run_script("create_task.py", args)
        if ok:
            tasks_data = get_tasks()
            new_task = None
            for t in reversed(tasks_data["tasks"]):
                if t.get("title") == title:
                    new_task = t
                    break
            self._json({"ok": True, "task": new_task or {"title": title, "priority": priority}})
        else:
            self._json({"ok": False, "error": output})

    def _post_dispatch_task(self, body):
        task_id = body.get("id", "").strip()
        assignee = body.get("assignee", "agent-exec-01").strip()
        if not task_id:
            self._json({"ok": False, "error": "id is required"})
            return
        ok, output = run_script("dispatch_task.py", ["--id", task_id, "--assignee", assignee])
        if ok:
            task = find_task_by_id(task_id)
            self._json({"ok": True, "task": task})
        else:
            self._json({"ok": False, "error": output})

    def _post_complete_task(self, body):
        task_id = body.get("id", "").strip()
        status = body.get("status", "done")
        summary = body.get("summary", "").strip()
        if not task_id:
            self._json({"ok": False, "error": "id is required"})
            return
        args = ["--id", task_id, "--status", status, "--summary", summary]
        ok, output = run_script("complete_task.py", args)
        if ok:
            task = find_task_by_id(task_id)
            self._json({"ok": True, "task": task})
        else:
            self._json({"ok": False, "error": output})

    def _post_cancel_task(self, body):
        task_id = body.get("id", "").strip()
        notes = body.get("notes", "")
        if not task_id:
            self._json({"ok": False, "error": "id is required"})
            return
        args = ["--id", task_id, "--status", "cancelled"]
        if notes:
            args += ["--notes", notes]
        ok, output = run_script("update_task.py", args)
        if ok:
            task = find_task_by_id(task_id)
            self._json({"ok": True, "task": task})
        else:
            self._json({"ok": False, "error": output})

    def _post_execute_task(self, body):
        task_id = body.get("id", "").strip()
        assignee = body.get("assignee", "agent-exec-01").strip()
        project = body.get("project", "").strip()
        timeout = body.get("timeout", 120)
        dry_run = body.get("dry_run", False)
        if not task_id:
            self._json({"ok": False, "error": "id is required"})
            return
        # dispatch_task --execute-real: dispatch + generate prompt + run CLI
        script_path = SCRIPTS_DIR / "dispatch_task.py"
        cmd = [sys.executable, str(script_path), "--id", task_id, "--assignee", assignee, "--execute-real"]
        if project:
            cmd += ["--project", project]
        if dry_run:
            cmd += ["--dry-run"]
        if timeout and isinstance(timeout, (int, float)) and timeout > 0:
            cmd += ["--timeout", str(int(timeout))]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=SUB_ENV,
            )
            _RUNNING_PIDS[task_id] = proc
            self._json({"ok": True, "message": f"Task {task_id} execution started (PID {proc.pid})", "pid": proc.pid})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _post_kill(self, body):
        task_id = body.get("id", "").strip()
        if not task_id:
            self._json({"ok": False, "error": "id is required"})
            return
        proc = _RUNNING_PIDS.get(task_id)
        killed_proc = False
        if proc:
            try:
                proc.kill()
                killed_proc = True
            except Exception:
                pass
            del _RUNNING_PIDS[task_id]
        # Update task status to cancelled
        ok, output = run_script("update_task.py", ["--id", task_id, "--status", "cancelled", "--notes", "killed by dashboard"])
        if ok or killed_proc:
            self._json({"ok": True, "message": f"Task {task_id} killed"})
        else:
            self._json({"ok": False, "error": output})

    def _post_rerun(self, body):
        task_id = body.get("id", "").strip()
        assignee = body.get("assignee", "agent-exec-01").strip()
        if not task_id:
            self._json({"ok": False, "error": "id is required"})
            return
        # Reset task to pending
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        ok, output = run_script("update_task.py", ["--id", task_id, "--status", "pending", "--notes", f"rerun at {ts}"])
        if not ok:
            self._json({"ok": False, "error": output})
            return
        # Start execution like _post_execute_task
        script_path = SCRIPTS_DIR / "dispatch_task.py"
        cmd = [sys.executable, str(script_path), "--id", task_id, "--assignee", assignee, "--execute-real"]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=SUB_ENV,
            )
            _RUNNING_PIDS[task_id] = proc
            self._json({"ok": True, "pid": proc.pid, "message": f"Task {task_id} rerun started (PID {proc.pid})"})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _post_batch(self, body):
        action = body.get("action", "").strip()
        assignee = body.get("assignee", "agent-exec-01").strip()
        if not action:
            self._json({"ok": False, "error": "action is required"})
            return
        tasks_data = get_tasks()
        tasks = tasks_data.get("tasks", [])
        count = 0
        if action == "execute_pending":
            pending = [t for t in tasks if t.get("status") == "pending"]
            for t in pending:
                tid = t["id"]
                script_path = SCRIPTS_DIR / "dispatch_task.py"
                cmd = [sys.executable, str(script_path), "--id", tid, "--assignee", assignee, "--execute-real"]
                try:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=str(PROJECT_ROOT),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env=SUB_ENV,
                    )
                    _RUNNING_PIDS[tid] = proc
                    count += 1
                except Exception:
                    pass
            self._json({"ok": True, "count": count})
        elif action == "cancel_running":
            running = [t for t in tasks if t.get("status") in ("in_progress", "running")]
            for t in running:
                tid = t["id"]
                proc = _RUNNING_PIDS.get(tid)
                if proc:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    del _RUNNING_PIDS[tid]
                run_script("update_task.py", ["--id", tid, "--status", "cancelled", "--notes", "batch cancelled by dashboard"])
                count += 1
            self._json({"ok": True, "count": count})
        else:
            self._json({"ok": False, "error": f"unknown action: {action}"})

    def _post_send_message(self, body):
        to = body.get("to", "").strip()
        message = body.get("message", "").strip()
        if not to:
            self._json({"ok": False, "error": "to is required"})
            return
        if not message:
            self._json({"ok": False, "error": "message is required"})
            return
        ok, output = run_script("send_message.py", ["--to", to, "--message", message, "--json"])
        if ok:
            try:
                result = json.loads(output)
                self._json({"ok": True, "message": result.get("message", result)})
            except json.JSONDecodeError:
                self._json({"ok": True})
        else:
            self._json({"ok": False, "error": output})

    # --- SSE: Global events stream ---

    def _sse_events(self):
        self._start_sse()

        last_tasks_mtime = 0
        last_audit_size = 0
        last_agent_check = 0

        try:
            while True:
                now = time.time()

                # Check tasks file mtime
                try:
                    mtime = os.path.getmtime(TASKS_FILE)
                    if mtime != last_tasks_mtime:
                        last_tasks_mtime = mtime
                        self._sse_write("tasks", get_tasks())
                except OSError:
                    pass

                # Check audit log file size
                try:
                    audit_file = get_latest_audit_file()
                    if audit_file:
                        size = audit_file.stat().st_size
                        if size != last_audit_size:
                            if last_audit_size > 0:
                                entries = read_jsonl_dir(AUDIT_DIR, 10)
                                entries.reverse()
                                for entry in entries:
                                    self._sse_write("audit", entry)
                            last_audit_size = size
                except (OSError, FileNotFoundError):
                    pass

                # Agent snapshot every 5s
                if now - last_agent_check > 5:
                    last_agent_check = now
                    self._sse_write("agents", get_agents())

                time.sleep(2)

        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                self.wfile.flush()
            except Exception:
                pass

    # --- SSE: Per-task log stream ---

    def _sse_task_logs(self, task_id):
        self._start_sse()

        # Find existing log files for this task
        tracked_files = find_task_log_files(task_id)

        # Send initial content for each file
        for fname in list(tracked_files.keys()):
            fpath = RUNS_DIR / fname
            content, new_offset = read_file_from(fpath, 0)
            tracked_files[fname] = new_offset
            if content:
                for line in content.splitlines():
                    if line.strip():
                        self._sse_write("log", {"file": fname, "line": line})

        # Send initial task status
        task = find_task_by_id(task_id)
        if task:
            self._sse_write("status", task)

        # Check if task is already in a terminal state
        terminal_statuses = {"done", "failed", "cancelled"}
        if task and task.get("status") in terminal_statuses:
            self._sse_write("end", {"task": task_id, "status": task["status"]})
            return

        # Poll loop
        try:
            while True:
                # Check for new files
                current_files = find_task_log_files(task_id)
                for fname in current_files:
                    if fname not in tracked_files:
                        fpath = RUNS_DIR / fname
                        content, new_offset = read_file_from(fpath, 0)
                        tracked_files[fname] = new_offset
                        if content:
                            for line in content.splitlines():
                                if line.strip():
                                    self._sse_write("log", {"file": fname, "line": line})

                # Check for new content in tracked files
                for fname in list(tracked_files.keys()):
                    fpath = RUNS_DIR / fname
                    content, new_offset = read_file_from(fpath, tracked_files[fname])
                    if content:
                        tracked_files[fname] = new_offset
                        for line in content.splitlines():
                            if line.strip():
                                self._sse_write("log", {"file": fname, "line": line})

                # Check task status
                task = find_task_by_id(task_id)
                if task:
                    self._sse_write("status", task)
                    if task.get("status") in terminal_statuses:
                        self._sse_write("end", {"task": task_id, "status": task["status"]})
                        return

                time.sleep(1)

        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                self.wfile.flush()
            except Exception:
                pass

    # --- Suppress default logging ---

    def log_message(self, format, *args):
        pass


# ===================================================================
#  Main
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Agent Chat Cluster Dashboard Server")
    parser.add_argument("--port", type=int, default=8765, help="Port (default 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default 127.0.0.1)")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard running at http://{args.host}:{args.port}")
    print(f"Project root: {PROJECT_ROOT}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
