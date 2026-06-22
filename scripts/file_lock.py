"""
file_lock.py — 跨平台文件锁工具模块

提供基于文件的互斥锁，支持 Windows (msvcrt.locking) 和 Unix (fcntl.flock)。
纯标准库实现，无需第三方依赖。

用法:
    from file_lock import file_lock

    # 排他锁（写操作）
    with file_lock('tasks/tasks.json', mode='exclusive'):
        # read-modify-write 原子操作
        ...

    # 共享锁（读操作）
    with file_lock('tasks/tasks.json', mode='shared'):
        data = json.load(...)
        ...

锁文件路径: 在目标文件同目录下创建 .<filename>.lock
    例如 tasks/tasks.json → tasks/.tasks.json.lock

支持 Python 3.8+。
"""

from __future__ import annotations

import os
import sys
import time
import errno
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Union

# 平台检测
_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import msvcrt
else:
    import fcntl


class FileLockTimeoutError(TimeoutError):
    """文件锁获取超时异常。"""

    pass


def _get_lock_path(target_path: Union[str, Path]) -> Path:
    """获取锁文件路径。

    在目标文件同目录下创建 .<filename>.lock 文件。
    例如: tasks/tasks.json → tasks/.tasks.json.lock

    Args:
        target_path: 目标文件路径

    Returns:
        锁文件路径对象
    """
    target = Path(target_path).resolve()
    lock_name = f".{target.name}.lock"
    return target.parent / lock_name


def _try_lock_windows(fd: int, exclusive: bool) -> bool:
    """Windows 平台尝试获取文件锁。

    使用 msvcrt.locking() 实现排他锁。
    Windows 不支持共享锁（msvcrt 只有排他锁定），
    因此 shared 模式在 Windows 上退化为无锁读取（仅检查文件存在性）。

    Args:
        fd: 文件描述符
        exclusive: 是否为排他锁

    Returns:
        True 如果成功获取锁，False 如果锁被占用
    """
    if not exclusive:
        # Windows msvcrt 不支持共享锁，shared 模式直接返回 True
        # 读取操作在 Windows 上不阻塞其他读取者
        return True

    try:
        # LK_NBLCK = 非阻塞排他锁
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return True
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EDEADLOCK):
            return False
        raise


def _try_lock_unix(fd: int, exclusive: bool) -> bool:
    """Unix 平台尝试获取文件锁。

    使用 fcntl.flock() 实现锁机制。
    支持 LOCK_EX (排他) 和 LOCK_SH (共享)。

    Args:
        fd: 文件描述符
        exclusive: 是否为排他锁

    Returns:
        True 如果成功获取锁，False 如果锁被占用
    """
    op = fcntl.LOCK_EX | fcntl.LOCK_NB if exclusive else fcntl.LOCK_SH | fcntl.LOCK_NB
    try:
        fcntl.flock(fd, op)
        return True
    except OSError as e:
        if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
            return False
        raise


def _unlock_windows(fd: int) -> None:
    """Windows 平台释放锁。"""
    try:
        # 先 seek 回 0，再解锁
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


def _unlock_unix(fd: int) -> None:
    """Unix 平台释放锁。"""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def file_lock(
    target_path: Union[str, Path],
    mode: str = "exclusive",
    timeout: float = 30.0,
    poll_interval: float = 0.1,
) -> Generator[None, None, None]:
    """文件锁上下文管理器。

    提供基于文件的互斥锁，确保并发进程对同一文件的读写安全。

    Args:
        target_path: 要保护的目标文件路径（锁文件将在其同目录下创建）
        mode: 锁模式，'exclusive' (排他锁，用于写操作) 或 'shared' (共享锁，用于读操作)
        timeout: 获取锁的超时时间（秒），超时抛出 FileLockTimeoutError
        poll_interval: 轮询间隔（秒），在重试获取锁之间的等待时间

    Raises:
        FileLockTimeoutError: 当在 timeout 时间内未能获取锁时
        ValueError: 当 mode 不是 'exclusive' 或 'shared' 时

    Example:
        # 排他锁保护 read-modify-write
        with file_lock('tasks/tasks.json', mode='exclusive'):
            data = load_tasks()
            data['nextId'] += 1
            save_tasks(data)

        # 共享锁保护读取
        with file_lock('tasks/tasks.json', mode='shared'):
            data = load_tasks()
    """
    if mode not in ("exclusive", "shared"):
        raise ValueError(f"mode 必须是 'exclusive' 或 'shared'，得到: {mode}")

    exclusive = (mode == "exclusive")
    lock_path = _get_lock_path(target_path)

    # 确保锁文件所在目录存在
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # 创建/打开锁文件
    fd = None
    lock_acquired = False

    try:
        # 以读写方式打开锁文件（不存在则创建）
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)

        start_time = time.monotonic()
        while True:
            if _IS_WINDOWS:
                lock_acquired = _try_lock_windows(fd, exclusive)
            else:
                lock_acquired = _try_lock_unix(fd, exclusive)

            if lock_acquired:
                break

            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                raise FileLockTimeoutError(
                    f"获取文件锁超时 ({timeout}s): {lock_path}\n"
                    f"目标文件: {target_path}\n"
                    f"可能有其他进程正在操作此文件，请稍后重试。"
                )

            time.sleep(poll_interval)

        yield

    finally:
        if fd is not None:
            if lock_acquired:
                if _IS_WINDOWS:
                    _unlock_windows(fd)
                else:
                    _unlock_unix(fd)
            try:
                os.close(fd)
            except OSError:
                pass
