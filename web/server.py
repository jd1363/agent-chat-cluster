#!/usr/bin/env python3
"""Agent Chat Cluster - Web Dashboard Server (stdlib only)"""

import http.server
import json
import os
import sys
import glob
import argparse
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def read_jsonl_dir(dirpath, limit=50):
    """Read JSONL files from a directory, return last N entries (newest last)."""
    result = []
    pattern = os.path.join(dirpath, '*.jsonl')
    files = sorted(glob.glob(pattern))
    for fp in reversed(files):
        try:
            with open(fp, encoding='utf-8') as f:
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


def get_tasks():
    data = read_json(os.path.join(PROJECT_ROOT, 'tasks', 'tasks.json'), {'tasks': []})
    tasks = data.get('tasks', [])
    stats = {}
    for t in tasks:
        s = t.get('status', 'unknown')
        stats[s] = stats.get(s, 0) + 1
    return {'tasks': tasks, 'stats': stats}


def get_agents():
    data = read_json(os.path.join(PROJECT_ROOT, 'config', 'agents.json'), {'agents': []})
    return {'agents': data.get('agents', [])}


def get_audit(limit=50):
    entries = read_jsonl_dir(os.path.join(PROJECT_ROOT, 'logs', 'audit'), limit)
    entries.reverse()
    return {'entries': entries[:limit]}


def get_messages(limit=30):
    entries = read_jsonl_dir(os.path.join(PROJECT_ROOT, 'logs', 'messages'), limit)
    entries.reverse()
    return {'entries': entries[:limit]}


def get_cost():
    entries = read_jsonl_dir(os.path.join(PROJECT_ROOT, 'logs', 'cost'), 10000)
    total_cost = 0.0
    total_tokens = 0
    by_agent = {}
    for e in entries:
        cost = e.get('estimatedCost', 0)
        tokens = e.get('totalTokens', 0)
        agent = e.get('agentId', 'unknown')
        total_cost += cost
        total_tokens += tokens
        if agent not in by_agent:
            by_agent[agent] = {'cost': 0, 'tokens': 0}
        by_agent[agent]['cost'] += cost
        by_agent[agent]['tokens'] += tokens
    return {
        'totalCost': round(total_cost, 4),
        'totalTokens': total_tokens,
        'byAgent': by_agent,
        'entries': entries[-20:]
    }


def get_alerts():
    tasks_data = get_tasks()
    agents_data = get_agents()
    msg_data = get_messages(500)

    alerts = []
    failed_count = tasks_data['stats'].get('failed', 0)
    pending_count = tasks_data['stats'].get('pending', 0)
    disabled_agents = [a for a in agents_data['agents'] if not a.get('enabled', False)]
    unacked = [m for m in msg_data['entries'] if m.get('status') != 'acked']

    if failed_count > 0:
        alerts.append({'level': 'red', 'text': f'{failed_count} 个失败任务'})
    if len(unacked) > 0:
        alerts.append({'level': 'yellow', 'text': f'{len(unacked)} 条未 ACK 消息'})
    if len(disabled_agents) > 0:
        alerts.append({'level': 'yellow', 'text': f'{len(disabled_agents)} 个 Agent 已禁用'})
    if pending_count > 0:
        alerts.append({'level': 'yellow', 'text': f'{pending_count} 个待处理任务'})

    level = 'green'
    if any(a['level'] == 'red' for a in alerts):
        level = 'red'
    elif any(a['level'] == 'yellow' for a in alerts):
        level = 'yellow'

    return {
        'level': level,
        'alerts': alerts,
        'counts': {
            'failed': failed_count,
            'pending': pending_count,
            'unacked': len(unacked),
            'disabledAgents': len(disabled_agents)
        }
    }


def serve_html():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard.html')
    with open(html_path, encoding='utf-8') as f:
        return f.read()


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/' or path == '/dashboard.html':
            html = serve_html()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        elif path == '/api/tasks':
            self._json(get_tasks())
        elif path == '/api/agents':
            self._json(get_agents())
        elif path == '/api/audit':
            limit = int(params.get('limit', ['50'])[0])
            self._json(get_audit(limit))
        elif path == '/api/messages':
            limit = int(params.get('limit', ['30'])[0])
            self._json(get_messages(limit))
        elif path == '/api/cost':
            self._json(get_cost())
        elif path == '/api/alerts':
            self._json(get_alerts())
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'not found'}).encode('utf-8'))

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description='Agent Chat Cluster Dashboard Server')
    parser.add_argument('--port', type=int, default=8765, help='Port (default 8765)')
    parser.add_argument('--host', default='127.0.0.1', help='Host (default 127.0.0.1)')
    args = parser.parse_args()

    server = http.server.HTTPServer((args.host, args.port), DashboardHandler)
    print(f'Dashboard running at http://{args.host}:{args.port}')
    print(f'Project root: {PROJECT_ROOT}')
    print('Press Ctrl+C to stop')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
        server.shutdown()


if __name__ == '__main__':
    main()
