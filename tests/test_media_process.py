"""Real spawn/IPC and timeout lifecycle, without native Qt/OIIO dependencies."""
import multiprocessing as mp
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vfxexplorer import media_process as media


def _no_qt_init():
    pass


class MediaProcessTests(unittest.TestCase):
    def test_lazy_spawn_timeout_recovery_and_shutdown(self):
        with patch.object(media, '_init', _no_qt_init):
            self.assertEqual(media.worker_counts(), {'preview': 0, 'foreground': 0})
            child = media.call('os', 'getpid', (), preview=True, _timeout=10)
            self.assertNotEqual(child, os.getpid())
            self.assertEqual(media.worker_counts(), {'preview': 1, 'foreground': 0})
            self.assertEqual(media.call('os', 'getpid', (), preview=True), child)
            other = media.call('os', 'getpid', (), _timeout=10)
            self.assertNotEqual(child, other)
            with self.assertRaisesRegex(OSError, 'timed out'):
                media.call('time', 'sleep', (30,), _timeout=.25)
            self.assertEqual(media.worker_counts(), {'preview': 1, 'foreground': 0})
            self.assertEqual(media.call('os', 'getpid', (), preview=True), child)
            replacement = media.call('os', 'getpid', (), _timeout=10)
            self.assertNotEqual(replacement, other)
            errors = []
            def blocked():
                try:
                    media.call('time', 'sleep', (30,))
                except OSError as exc:
                    errors.append(str(exc))
            thread = threading.Thread(target=blocked)
            thread.start()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with media._lock:
                    if media._slots['foreground'][0].jobs:
                        break
                time.sleep(.01)
            # Second foreground worker is only spawned for overlapping jobs.
            second = media.call('os', 'getpid', (), _timeout=10)
            self.assertNotEqual(second, replacement)
            self.assertEqual(media.worker_counts(), {'preview': 1, 'foreground': 2})
            media.shutdown()
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertTrue(errors)
            self.assertEqual(media.worker_counts(), {'preview': 0, 'foreground': 0})
            self.assertFalse(mp.active_children())
            with self.assertRaisesRegex(OSError, 'shutting down'):
                media.call('os', 'getpid', ())


if __name__ == '__main__':
    mp.freeze_support()
    unittest.main(verbosity=2)
