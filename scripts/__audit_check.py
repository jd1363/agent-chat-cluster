import json
with open('G:/agent-chat-cluster/tasks/tasks.json', encoding='utf-8') as f:
    data = json.load(f)
for t in data['tasks']:
    s = t.get('status')
    a = t.get('assignee')
    n = t.get('notes', '')
    tid = t.get('id', '')
    # in_progress without assignee
    if s == 'in_progress' and not a:
        print(f'IN_PROGRESS_NO_ASSIGNEE: {tid}')
    # cancelled without reason in notes
    if s == 'cancelled' and not n.strip():
        print(f'CANCELLED_NO_REASON: {tid} - {t.get("title","")}')
    # done with failed output
    if s == 'done' and t.get('output') and 'EXECUTION FAILED' in (t.get('output') or ''):
        print(f'DONE_BUT_FAILED_OUTPUT: {tid}')
    # failed without notes
    if s == 'failed' and not n.strip():
        print(f'FAILED_NO_NOTES: {tid}')
    # cancelled but has output
    if s == 'cancelled' and t.get('output'):
        print(f'CANCELLED_WITH_OUTPUT: {tid} - output_len={len(t["output"])}')
    # done but output contains timeout
    if s == 'done' and t.get('output') and 'timeout' in (t.get('output') or '').lower():
        print(f'DONE_BUT_TIMEOUT_IN_OUTPUT: {tid}')
print(f'Total tasks: {len(data["tasks"])}')
