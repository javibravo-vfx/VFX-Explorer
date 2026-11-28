"""Bounded scan scheduling and retry bookkeeping; no GUI dependencies."""
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vfxexplorer.scan_queue import ScanQueue, QueueFull
from vfxexplorer.tree_retry import TreeRetries


class QueueTests(unittest.TestCase):
    def test_burst_latest_and_isolation(self):
        q = ScanQueue(workers=2, pending=8)
        release = threading.Event()
        started = [threading.Event(), threading.Event()]
        calls = []
        def block(i):
            started[i].set()
            if not release.wait(5):
                raise TimeoutError('test release missing')
            return i
        a = [q.submit('NAS A', lambda i=i: block(i)) for i in range(2)]
        try:
            self.assertTrue(all(e.wait(2) for e in started))
            old = None
            for i in range(100):
                if old is not None:
                    self.assertTrue(old.cancel())
                old = q.submit('NAS A', lambda i=i: calls.append(i) or i, latest=True)
            self.assertEqual(q.submit('NAS B', lambda: 42).result(1), 42)
            self.assertFalse(old.done())
            self.assertEqual(calls, [])
        finally:
            release.set()
        self.assertEqual(old.result(2), 99)
        self.assertEqual(calls, [99])
        self.assertEqual([f.result(2) for f in a], [0, 1])

    def test_pending_limit_and_errors(self):
        q = ScanQueue(workers=1, pending=2)
        release = threading.Event()
        a = q.submit('A', lambda: release.wait(5))
        b = q.submit('A', lambda: 1)
        c = q.submit('A', lambda: 2)
        try:
            with self.assertRaises(QueueFull):
                q.submit('A', lambda: 3).result(1)
            self.assertTrue(b.cancel())
            d = q.submit('A', lambda: 4)
        finally:
            release.set()
        self.assertTrue(a.result(2))
        self.assertEqual(c.result(2), 2)
        self.assertEqual(d.result(2), 4)
        def fail():
            raise OSError('NAS unavailable')
        with self.assertRaises(OSError):
            q.submit('A', fail).result(2)
        self.assertEqual(q.submit('A', lambda: 5).result(2), 5)

    def test_latest_priority_over_older_pending(self):
        q = ScanQueue(workers=1)
        release = threading.Event()
        order = []
        a = q.submit('A', lambda: release.wait(5))
        b = q.submit('A', lambda: order.append('old'))
        c = q.submit('A', lambda: order.append('latest'), latest=True)
        release.set()
        for f in (a, b, c):
            f.result(2)
        self.assertEqual(order, ['latest', 'old'])


class RetryTests(unittest.TestCase):
    def test_backoff_and_limit(self):
        r = TreeRetries()
        delays = []
        for _ in range(8):
            ticket, delay = r.schedule('folder')
            delays.append(delay)
            self.assertIsNone(r.schedule('folder'))  # duplicate failure while scheduled
            self.assertTrue(r.consume('folder', ticket))
            self.assertNotIn('folder', r.pending)
        self.assertEqual(delays, [2000, 4000, 8000, 16000, 30000, 30000, 30000, 30000])
        self.assertIsNone(r.schedule('folder'))
        r.reset('folder')  # authoritative success or explicit reopen
        self.assertEqual(r.schedule('folder')[1], 2000)

    def test_obsolete_tickets(self):
        r = TreeRetries()
        old, _ = r.schedule('folder')
        r.clear()  # reload
        new, _ = r.schedule('folder')
        self.assertFalse(r.consume('folder', old))
        self.assertTrue(r.consume('folder', new))
        ticket, _ = r.schedule('folder')
        r.reset('folder')  # success/collapse
        self.assertFalse(r.consume('folder', ticket))
        self.assertFalse(r.pending)


if __name__ == '__main__':
    unittest.main()
