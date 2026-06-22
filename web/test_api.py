import urllib.request, json

proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(proxy_handler)

tests = [
    ('/api/tasks', 'tasks'),
    ('/api/agents', 'agents'),
    ('/api/audit?limit=5', 'entries'),
    ('/api/messages?limit=5', 'entries'),
    ('/api/cost', None),
    ('/api/alerts', None),
]

all_ok = True
for ep, key in tests:
    try:
        r = opener.open(f'http://127.0.0.1:8765{ep}', timeout=5)
        d = json.loads(r.read())
        if key:
            print(f'OK {ep}: {len(d[key])} items')
        else:
            print(f'OK {ep}: {list(d.keys())}')
    except Exception as e:
        print(f'FAIL {ep}: {e}')
        all_ok = False

# Also test HTML
try:
    r = opener.open('http://127.0.0.1:8765/', timeout=5)
    html = r.read().decode()
    if '<title>Agent Chat Cluster' in html:
        print('OK /: HTML served correctly')
    else:
        print(f'FAIL /: unexpected HTML content')
        all_ok = False
except Exception as e:
    print(f'FAIL /: {e}')
    all_ok = False

print()
print('=== ALL TESTS PASSED ===' if all_ok else '=== SOME TESTS FAILED ===')
