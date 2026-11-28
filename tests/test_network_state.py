"""Regression tests for nonblocking share state, including TTL expiry."""
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vfxexplorer import core


class NetworkStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        core.NET_FAKE_ROOTS.add(self.root)
        self.release = threading.Event()
        self.entered = threading.Event()

    def tearDown(self):
        self.release.set()
        with core._NET_LOCK:
            state = core._NET.get(self.root)
        if state:
            state['ev'].wait(2)
        with core._NET_LOCK:
            core._NET.pop(self.root, None)
        core.NET_FAKE_ROOTS.discard(self.root)
        self.tmp.cleanup()

    def expire(self):
        with core._NET_LOCK:
            core._NET[self.root]['t'] = time.monotonic() - 31

    def slow(self, answer):
        def check(_):
            self.entered.set()
            self.release.wait(2)
            return answer
        return check

    def test_online_remains_online_at_ttl_expiry(self):
        core.note_network_success(self.root)
        self.expire()
        with patch.object(core.os.path, 'isdir', side_effect=self.slow(True)) as check:
            with patch.dict(sys.modules, {'PySide6.QtWidgets': object()}):
                self.assertTrue(core.reachable(self.root))
                self.assertTrue(self.entered.wait(1))
                self.assertEqual(core.network_status(self.root), (True, True))
                for _ in range(20):
                    self.assertTrue(core.reachable(self.root, 0))
                self.assertEqual(check.call_count, 1)
                self.release.set()
                self.assertTrue(core._NET[self.root]['ev'].wait(1))
        self.assertEqual(core.network_status(self.root), (True, False))

    def test_unknown_timeout_does_not_mark_offline(self):
        with patch.object(core.os.path, 'isdir', side_effect=self.slow(False)):
            self.assertFalse(core.reachable(self.root, .01))
            self.assertEqual(core.network_status(self.root), (None, True))
            self.assertNotIn(self.root, core.net_offline_roots())
            self.release.set()
            self.assertTrue(core._NET[self.root]['ev'].wait(1))
        self.assertEqual(core.network_status(self.root), (False, False))
        self.assertIn(self.root, core.net_offline_roots())

    def test_offline_recovers_without_extra_probe(self):
        with patch.object(core.os.path, 'isdir', return_value=False):
            self.assertFalse(core.reachable(self.root, 1))
        with patch.object(core.os.path, 'isdir', side_effect=AssertionError('unexpected IO')):
            core.note_network_success(self.root)
            self.assertTrue(core.reachable(self.root, 0))
            self.assertNotIn(self.root, core.net_offline_roots())

    def test_late_probe_cannot_override_real_success(self):
        with patch.object(core.os.path, 'isdir', side_effect=self.slow(False)):
            core.note_network_failure(self.root)
            self.assertTrue(self.entered.wait(1))
            core.note_network_success(self.root)
            self.release.set()
            self.assertTrue(core._NET[self.root]['ev'].wait(1))
        self.assertEqual(core.network_status(self.root), (True, False))

    def test_status_reads_never_probe_and_local_bypasses(self):
        with patch.object(core.os.path, 'isdir', side_effect=AssertionError('unexpected IO')) as check:
            self.assertEqual(core.network_status(self.root), (None, False))
            self.assertTrue(core.reachable(os.path.dirname(self.root)))
            self.assertEqual(core.net_offline_roots(), [])
            check.assert_not_called()

    def test_missing_subfolder_does_not_mark_share_offline(self):
        core.note_network_success(self.root)
        with patch.object(core.os.path, 'isdir', return_value=True):
            core.note_network_failure(os.path.join(self.root, 'missing'))
            self.assertTrue(core._NET[self.root]['ev'].wait(1))
        self.assertEqual(core.network_status(self.root), (True, False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
