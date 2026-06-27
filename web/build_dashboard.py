#!/usr/bin/env python3
"""Build dashboard.html - run this script to generate the file."""
import pathlib

OUT = pathlib.Path(r"G:\agent-chat-cluster\web\dashboard.html")

# Read parts from separate files
parts_dir = pathlib.Path(r"G:\agent-chat-cluster\web\parts")
css = (parts_dir / "style.css").read_text(encoding="utf-8")
body = (parts_dir / "body.html").read_text(encoding="utf-8")
js = (parts_dir / "script.js").read_text(encoding="utf-8")

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Chat Cluster \u2014 Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
{css}
</style>
</head>
<body>
{body}
<script>
{js}
</script>
</body>
</html>
"""

OUT.write_text(html, encoding="utf-8")
size = OUT.stat().st_size
print(f"Written {size} bytes to {OUT}")
