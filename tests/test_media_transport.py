"""Actual spawned processes and NumPy IPC; Qt/OIIO replaced only for this test."""
import multiprocessing as mp
import os
import sys
import time
import threading
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from vfxexplorer import media_process as media, core


def _no_qt_init():
    pass


def hdr_linear(path, settings, maxdim):
    if settings.get('delay'):
        time.sleep(settings['delay'])
    if settings.get('missing'):
        return None
    rgb = np.arange(32 * 64 * 3, dtype=np.float32).reshape(32, 64, 3) / 127
    alpha = np.arange(32 * 64 * 2, dtype=np.float32).reshape(32, 64, 2)[..., 1] / 4096
    return rgb, None if settings.get('no_alpha') else alpha


class TransportTests(unittest.TestCase):
    def test_shared_float_data_fallback_cleanup_and_independent_roots(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(media, '_init', _no_qt_init):
            a, b = os.path.join(tmp, 'nas-a'), os.path.join(tmp, 'nas-b')
            core.NET_FAKE_ROOTS.update((a, b))
            try:
                expected = hdr_linear(a, {}, 64)
                before = media.shared_transfers()
                result = media.call('__main__', 'hdr_linear', (a, {}, 64), _timeout=15)
                for x, y in zip(expected, result):
                    np.testing.assert_array_equal(x, y)
                self.assertEqual(media.shared_transfers(), before + 1)
                self.assertEqual(media._shm_reserved, 0)
                rgb, alpha = media.call('__main__', 'hdr_linear', (a, {'no_alpha': True}, 64), _timeout=15)
                np.testing.assert_array_equal(rgb, expected[0]); self.assertIsNone(alpha)
                self.assertIsNone(media.call('__main__', 'hdr_linear', (a, {'missing': True}, 64), _timeout=15))
                with patch.object(media, '_reserve_buffer', return_value=None):
                    fallback = media.call('__main__', 'hdr_linear', (a, {}, 64), _timeout=15)
                for x, y in zip(expected, fallback):
                    np.testing.assert_array_equal(x, y)
                p1 = media.call('os', 'getpid', (), storage=a, _timeout=15)
                p2 = media.call('os', 'getpid', (), storage=b, _timeout=15)
                self.assertNotEqual(p1, p2)
                errors = []
                def slow():
                    try:
                        media.call('__main__', 'hdr_linear', (a, {'delay': 30}, 64), _timeout=1.5)
                    except OSError as exc:
                        errors.append(str(exc))
                thread = threading.Thread(target=slow); thread.start()
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    with media._lock:
                        if media._slots[('foreground', a.casefold())][0].jobs:
                            break
                    time.sleep(.01)
                self.assertEqual(media.call('os', 'getpid', (), storage=b, _timeout=10), p2)
                self.assertTrue(thread.is_alive(), 'other NAS waited for blocked root')
                thread.join(10)
                self.assertEqual(errors, ['Network decoder timed out'])
                self.assertEqual(media._shm_reserved, 0)
                self.assertEqual(media.call('os', 'getpid', (), storage=b, _timeout=10), p2)
                self.assertNotEqual(media.call('os', 'getpid', (), storage=a, _timeout=10), p1)
            finally:
                core.NET_FAKE_ROOTS.difference_update((a, b))
                media.shutdown()
            self.assertFalse(mp.active_children())
            self.assertEqual(media._shm_reserved, 0)


if __name__ == '__main__':
    mp.freeze_support()
    unittest.main(verbosity=2)
