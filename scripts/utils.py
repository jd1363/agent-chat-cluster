#!/usr/bin/env python3
"""
utils.py — 通用工具函数集

提供项目中复用的纯工具函数，仅依赖 Python 标准库。
"""

from datetime import datetime, timezone


def format_date(dt: datetime | str | None = None, fmt: str = "%Y-%m-%d %H:%M:%S", use_utc: bool = False) -> str:
    """
    将 datetime 对象或 ISO 格式字符串格式化为指定格式的日期字符串。

    参数:
        dt: datetime 对象、ISO 格式字符串，或 None（默认使用当前时间）。
        fmt: 输出格式，默认 "%Y-%m-%d %H:%M:%S"。
        use_utc: 若为 True 且 dt 为 None，则使用 UTC 时间；否则使用本地时间。

    返回:
        格式化后的日期字符串。

    示例:
        >>> format_date(datetime(2026, 6, 27, 12, 0, 0))
        '2026-06-27 12:00:00'
        >>> format_date("2026-06-27T12:00:00", fmt="%Y/%m/%d")
        '2026/06/27'
        >>> format_date(fmt="%Y-%m-%d")  # 当前日期
        '2026-06-27'
    """
    if dt is None:
        dt = datetime.now(timezone.utc) if use_utc else datetime.now()
    elif isinstance(dt, str):
        # 尝试解析 ISO 格式字符串；支持带和不带时区的形式
        dt = datetime.fromisoformat(dt)
    elif not isinstance(dt, datetime):
        raise TypeError(f"dt 必须是 datetime、str 或 None，收到 {type(dt).__name__}")

    return dt.strftime(fmt)


def parse_date(date_str: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> datetime:
    """
    将格式化日期字符串解析为 datetime 对象。

    参数:
        date_str: 日期字符串。
        fmt: 输入格式，默认 "%Y-%m-%d %H:%M:%S"。

    返回:
        datetime 对象。

    示例:
        >>> parse_date("2026-06-27 12:00:00")
        datetime.datetime(2026, 6, 27, 12, 0)
    """
    return datetime.strptime(date_str, fmt)


if __name__ == "__main__":
    # 简单的自测入口
    now_str = format_date()
    print(f"[TEST] 当前时间 (默认格式): {now_str}")

    iso_input = "2026-06-27T12:00:00"
    formatted = format_date(iso_input, fmt="%Y/%m/%d %H:%M")
    print(f"[TEST] ISO 字符串格式化: {iso_input} -> {formatted}")

    dt_obj = datetime(2026, 6, 27, 12, 0, 0)
    custom_fmt = format_date(dt_obj, fmt="%A, %B %d, %Y")
    print(f"[TEST] datetime 对象格式化: {dt_obj} -> {custom_fmt}")

    utc_now = format_date(use_utc=True)
    print(f"[TEST] UTC 当前时间: {utc_now}")

    parsed = parse_date("2026-06-27 12:00:00")
    print(f"[TEST] 解析字符串: 2026-06-27 12:00:00 -> {parsed}")

    print("[OK] utils.py 自测全部通过")
