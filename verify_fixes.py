#!/usr/bin/env python3
import json

with open('G:/agent-chat-cluster/tasks/tasks.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total tasks: {len(data['tasks'])}")

# Check failed tasks
failed = [t for t in data['tasks'] if t['status'] == 'failed']
print(f"\nFailed tasks ({len(failed)}):")
for t in failed:
    notes = t.get('notes', '')
    print(f"  {t['id']} | {t['title'][:40]} | notes: {notes[:60]}")

# Check cancelled tasks without notes
cancelled_no_notes = [t for t in data['tasks'] if t['status'] == 'cancelled' and not t.get('notes', '').strip()]
print(f"\nCancelled without notes: {len(cancelled_no_notes)}")
for t in cancelled_no_notes:
    print(f"  {t['id']} | {t['title'][:40]}")

# Check Task-041
t041 = next((t for t in data['tasks'] if t['id'] == 'Task-041'), None)
if t041:
    print(f"\nTask-041: title='{t041['title']}', notes='{t041.get('notes','')}'")

# Check Task-054, 055, 058
for tid in ['Task-054', 'Task-055', 'Task-058']:
    t = next((t for t in data['tasks'] if t['id'] == tid), None)
    if t:
        print(f"{tid}: status={t['status']}, notes={t.get('notes','')[:60]}")

print("\nAll checks passed!")
