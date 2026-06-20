#!/usr/bin/env python3
"""
临时测试：验证 event_log.py 的 eventId 跨天重置逻辑。
使用临时目录 + monkeypatch 模拟日期变化，不污染正式日志。
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

# 将 scripts 目录加入 path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import event_log

# ---------------------------------------------------------------------------
# 辅助：monkeypatch 日期
# ---------------------------------------------------------------------------

class _FrozenDatetime(datetime):
    """一个可冻结 now() 的 datetime 子类。"""
    _frozen = None

    @classmethod
    def now(cls, tz=None):
        if cls._frozen is not None:
            return cls._frozen
        return real_datetime_now(tz)


real_datetime_now = datetime.now


def freeze_date(date_str: str):
    """冻结 datetime.now() 到指定 UTC 日期 00:00:00。"""
    frozen = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    _FrozenDatetime._frozen = frozen


def unfreeze_date():
    _FrozenDatetime._frozen = None


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------

class TestEventIdDailyReset(unittest.TestCase):

    def setUp(self):
        """每个测试使用独立临时目录。"""
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        (tmp / "logs" / "events").mkdir(parents=True, exist_ok=True)
        (tmp / "logs" / "dead_letter").mkdir(parents=True, exist_ok=True)

        # 保存原始路径
        self._orig_events_dir = event_log.EVENTS_DIR
        self._orig_dead = event_log.DEAD_LETTER_DIR
        self._orig_state = event_log.STATE_FILE
        self._orig_lock = event_log.STATE_LOCK_FILE

        # 重定向到临时目录
        event_log.EVENTS_DIR = tmp / "logs" / "events"
        event_log.DEAD_LETTER_DIR = tmp / "logs" / "dead_letter"
        event_log.STATE_FILE = event_log.EVENTS_DIR / ".state"
        event_log.STATE_LOCK_FILE = event_log.EVENTS_DIR / ".state.lock"

    def tearDown(self):
        # 恢复原始路径
        event_log.EVENTS_DIR = self._orig_events_dir
        event_log.DEAD_LETTER_DIR = self._orig_dead
        event_log.STATE_FILE = self._orig_state
        event_log.STATE_LOCK_FILE = self._orig_lock

        self.tmpdir.cleanup()

    # ---- 场景 1：同一天内正常递增 ----
    @patch("event_log.datetime", _FrozenDatetime)
    def test_same_day_increment(self):
        freeze_date("20260620")
        # 初始 state（模拟已有 5 条）
        event_log.save_state({"date": "20260620", "nextEventNumber": 6})
        eid = event_log.allocate_event_id()
        self.assertEqual(eid, "EVT-20260620-000006")
        state = event_log.load_state()
        self.assertEqual(state["date"], "20260620")
        self.assertEqual(state["nextEventNumber"], 7)

        # 继续下一条
        eid2 = event_log.allocate_event_id()
        self.assertEqual(eid2, "EVT-20260620-000007")
        state = event_log.load_state()
        self.assertEqual(state["nextEventNumber"], 8)
        unfreeze_date()

    # ---- 场景 2：跨天重置 ----
    @patch("event_log.datetime", _FrozenDatetime)
    def test_cross_day_reset(self):
        # 第一天：生成 3 条
        freeze_date("20260620")
        event_log.save_state({"date": "20260620", "nextEventNumber": 4})
        eid = event_log.allocate_event_id()
        self.assertEqual(eid, "EVT-20260620-000004")

        # 第二天：应重置为 1
        freeze_date("20260621")
        eid2 = event_log.allocate_event_id()
        self.assertEqual(eid2, "EVT-20260621-000001")
        state = event_log.load_state()
        self.assertEqual(state["date"], "20260621")
        self.assertEqual(state["nextEventNumber"], 2)

        # 第二天继续递增
        eid3 = event_log.allocate_event_id()
        self.assertEqual(eid3, "EVT-20260621-000002")
        state = event_log.load_state()
        self.assertEqual(state["nextEventNumber"], 3)

        # 第三天再次重置
        freeze_date("20260622")
        eid4 = event_log.allocate_event_id()
        self.assertEqual(eid4, "EVT-20260622-000001")
        state = event_log.load_state()
        self.assertEqual(state["date"], "20260622")
        self.assertEqual(state["nextEventNumber"], 2)
        unfreeze_date()

    # ---- 场景 3：旧 state 兼容（无 date 字段）----
    @patch("event_log.datetime", _FrozenDatetime)
    def test_legacy_state_no_date(self):
        freeze_date("20260620")
        # 旧格式 state：只有 nextEventNumber
        event_log.save_state({"nextEventNumber": 6})
        eid = event_log.allocate_event_id()
        self.assertEqual(eid, "EVT-20260620-000006")
        state = event_log.load_state()
        self.assertEqual(state["date"], "20260620")
        self.assertEqual(state["nextEventNumber"], 7)
        unfreeze_date()

    # ---- 场景 4：冷启动（无 state 文件）----
    @patch("event_log.datetime", _FrozenDatetime)
    def test_cold_start_no_state_file(self):
        freeze_date("20260620")
        # 确保 state 文件不存在
        if event_log.STATE_FILE.exists():
            event_log.STATE_FILE.unlink()
        eid = event_log.allocate_event_id()
        self.assertEqual(eid, "EVT-20260620-000001")
        state = event_log.load_state()
        self.assertEqual(state["date"], "20260620")
        self.assertEqual(state["nextEventNumber"], 2)
        unfreeze_date()

    # ---- 场景 5：嵌套锁安全（单进程快速连续分配）----
    @patch("event_log.datetime", _FrozenDatetime)
    def test_rapid_sequential_allocations(self):
        freeze_date("20260620")
        # 模拟同一进程内快速连续分配
        ids = [event_log.allocate_event_id() for _ in range(5)]
        expected = [
            "EVT-20260620-000001",
            "EVT-20260620-000002",
            "EVT-20260620-000003",
            "EVT-20260620-000004",
            "EVT-20260620-000005",
        ]
        self.assertEqual(ids, expected)
        state = event_log.load_state()
        self.assertEqual(state["nextEventNumber"], 6)
        unfreeze_date()


if __name__ == "__main__":
    unittest.main(verbosity=2)
