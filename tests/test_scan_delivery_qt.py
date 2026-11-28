"""Real Qt event-loop regression; runs in Windows CI with the app dependencies."""
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace, MethodType

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QApplication
from vfxexplorer.asyncdir import RemoteScan, AsyncLister
from vfxexplorer import asyncdir, core, storage_cache

app = QApplication.instance() or QApplication([])


def until(fn, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if fn():
            return True
        time.sleep(.003)
    return False


class DeliveryTests(unittest.TestCase):
    def test_cache_arrives_while_remote_read_blocked_and_latest_wins(self):
        owner = QObject()
        r = RemoteScan(owner)
        release = threading.Event()
        got = []
        def block():
            release.wait(5)
            return ['old']
        def record(kind, value):
            got.append((kind, value, QThread.currentThread() == app.thread()))
        try:
            r.request('A', lambda: ['cached'], block, lambda v: record('cache', v),
                      lambda v, e: record('old', v))
            self.assertTrue(until(lambda: bool(got)))
            self.assertEqual(got, [('cache', ['cached'], True)])
            r.request('B', None, lambda: ['new'], None, lambda v, e: record('new', v))
            self.assertTrue(until(lambda: len(got) == 2))
            self.assertEqual(got[-1], ('new', ['new'], True))
        finally:
            release.set()
            r.cancel()
        app.processEvents()
        self.assertEqual(len(got), 2)

    def test_fast_failure_waits_for_local_cache(self):
        owner = QObject()
        r = RemoteScan(owner)
        release = threading.Event()
        failed = threading.Event()
        got = []
        def cache():
            release.wait(5)
            return ['saved']
        def fail():
            failed.set()
            raise OSError('offline')
        try:
            r.request('A', cache, fail, lambda v: got.append(('cache', v)),
                      lambda v, e: got.append(('error', e)))
            self.assertTrue(failed.wait(2))
            until(lambda: False, .1)
            self.assertFalse(got)
            release.set()
            self.assertTrue(until(lambda: len(got) == 2))
            self.assertEqual(got, [('cache', ['saved']), ('error', 'offline')])
        finally:
            release.set()
            r.cancel()

    def test_tree_cache_and_failure_are_distinct(self):
        owner = QObject()
        l = AsyncLister(owner, separate_cache=True)
        got = []
        l.cached.connect(lambda p, v: got.append(('cache', v)))
        l.done.connect(lambda p, v: got.append(('live', v)))
        with patch.object(core, 'net_root', return_value='NAS'), \
             patch.object(core, 'note_network_failure'), \
             patch.object(storage_cache, 'cached_dirs', return_value=['saved']), \
             patch.object(asyncdir, 'list_subdirs', return_value=None):
            l.request('NAS/folder')
            self.assertTrue(until(lambda: len(got) == 2))
        self.assertEqual(got, [('cache', ['saved']), ('live', None)])
        self.assertFalse(l.busy)

    def test_tree_cancel_discards_late_results(self):
        owner = QObject()
        l = AsyncLister(owner, separate_cache=True)
        got = []
        l.done.connect(lambda p, v: got.append(v))
        release = threading.Event()
        entered = threading.Event()
        def block(*_):
            entered.set()
            release.wait(5)
            return None
        with patch.object(core, 'net_root', return_value='NAS'), \
             patch.object(core, 'note_network_failure'), \
             patch.object(storage_cache, 'cached_dirs', return_value=None), \
             patch.object(asyncdir, 'list_subdirs', side_effect=block):
            try:
                l.request('NAS/folder')
                self.assertTrue(entered.wait(2))
                l.cancel_all()
                self.assertFalse(l.busy)
            finally:
                release.set()
            until(lambda: False, .1)
        until(lambda: False, .1)
        self.assertEqual(got, [])

    def test_library_cache_never_resets_retry_attempts(self):
        from vfxexplorer import library_ui
        from vfxexplorer.tree_retry import TreeRetries
        path = os.path.normpath(os.path.join('NAS', 'folder'))
        it = Mock()
        sidebar = SimpleNamespace(_retry_state=TreeRetries(), _find=lambda p: it,
                                  _branch_open=lambda i: True, _remove_loading=Mock(),
                                  _lister=Mock(), tree=SimpleNamespace(itemAt=lambda *a: None, _trace_path=''),
                                  _anchored=lambda anchor, fn: fn(), _fill=Mock())
        for name in ('_listed', '_listed_cached', '_retry_later', '_retry'):
            setattr(sidebar, name, MethodType(getattr(library_ui.LibrarySidebar, name), sidebar))
        timers = []
        def timer(delay, context, callback):
            timers.append((delay, callback))
        with patch.object(library_ui, 'QTimer', SimpleNamespace(singleShot=timer)):
            for _ in range(8):
                sidebar._listed_cached(path, ['saved'])
                sidebar._listed(path, None)
                timers[-1][1]()
            sidebar._listed_cached(path, ['saved'])
            sidebar._listed(path, None)  # exhausted
            self.assertEqual([d for d, _ in timers], [2000, 4000, 8000, 16000, 30000, 30000, 30000, 30000])
            self.assertEqual(sidebar._lister.request.call_count, 8)
            sidebar._listed(path, ['real'])
            self.assertFalse(sidebar._retry_state.attempts)
            sidebar._listed(path, None)
            self.assertEqual(timers[-1][0], 2000)
            sidebar._listed(path, ['real'])  # invalidate outstanding retry
            timers[-1][1]()
            self.assertEqual(sidebar._lister.request.call_count, 8)


if __name__ == '__main__':
    unittest.main()
