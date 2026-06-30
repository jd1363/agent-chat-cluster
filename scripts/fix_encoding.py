#!/usr/bin/env python3
"""fix_encoding.py — 强制子进程使用 UTF-8 输出

在脚本入口处调用 setup_utf8_stdout() 即可。
"""
import sys
import io


def setup_utf8_stdout():
    """将 stdout/stderr 包装为 UTF-8，避免 GBK 编码崩溃。"""
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
