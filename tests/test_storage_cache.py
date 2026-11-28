"""NAS simulations: no Qt, no actual SMB hardware required."""
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vfxexplorer import core, storage_cache as cache


class StorageCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.temp.name, 'nas')
        self.local = os.path.join(self.temp.name, 'local')
        os.makedirs(self.root)
        os.makedirs(self.local)
        self.data_patch = patch.object(core, 'data_dir', return_value=self.local)
        self.data_patch.start()
        core.NET_FAKE_ROOTS.add(self.root)
        self.add('plate.1001.exr')
        self.add('plate.1002.exr')
        self.add('photo.jpg')

    def tearDown(self):
        core.NET_FAKE_ROOTS.discard(self.root)
        core.NET_FAKE_OFFLINE.discard(self.root)
        self.data_patch.stop()
        self.temp.cleanup()

    def add(self, name):
        with open(os.path.join(self.root, name), 'wb') as f:
            f.write(b'abc')

    def test_snapshot_no_remote_io(self):
        actual = cache.scan_and_save(self.root)
        with patch.object(os, 'scandir', side_effect=AssertionError('network read')):
            cached = cache.cached_entries(self.root)
        self.assertEqual(actual, cached)
        self.assertTrue(any(e.kind == 'seq' and e.thumb_size == 3 for e in cached))

    def test_suspended_and_recovery(self):
        before = cache.scan_and_save(self.root)
        core.NET_FAKE_OFFLINE.add(self.root)
        with self.assertRaises(OSError):
            cache.scan_and_save(self.root)
        self.assertEqual(cache.cached_entries(self.root), before)
        core.NET_FAKE_OFFLINE.discard(self.root)
        self.add('new.png')
        os.remove(os.path.join(self.root, 'photo.jpg'))
        after = cache.scan_and_save(self.root)
        self.assertEqual(cache.cached_entries(self.root), after)
        self.assertIn('new.png', [e.name for e in after])
        self.assertNotIn('photo.jpg', [e.name for e in after])

    def test_slow_scan_cache_available_and_coalesced(self):
        before = cache.scan_and_save(self.root)
        entered, release = threading.Event(), threading.Event()
        original = core.scan_dir
        calls = []
        def slow(*args, **kwargs):
            calls.append(args)
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test gate timed out')
            return original(*args, **kwargs)
        with patch.object(core, 'scan_dir', side_effect=slow):
            with ThreadPoolExecutor(2) as pool:
                a = pool.submit(cache.scan_and_save, self.root)
                self.assertTrue(entered.wait(2))
                b = pool.submit(cache.scan_and_save, self.root)
                t = time.monotonic()
                self.assertEqual(cache.cached_entries(self.root), before)
                self.assertLess(time.monotonic() - t, 0.5)
                time.sleep(0.05)
                release.set()
                self.assertEqual(a.result(), b.result())
        self.assertEqual(len(calls), 1)

    def test_local_bypasses_sqlite(self):
        with patch.object(cache, '_db', side_effect=AssertionError('local cache accessed')):
            self.assertIsNone(cache.cached_entries(self.local))
            self.assertEqual(cache.scan_and_save(self.local), [])

    def test_empty_success_and_failure_are_distinct(self):
        empty = os.path.join(self.root, 'empty')
        os.mkdir(empty)
        self.assertIsNone(cache.cached_entries(empty))
        self.assertEqual(cache.scan_and_save(empty), [])
        self.assertEqual(cache.cached_entries(empty), [])
        with patch.object(core, 'scan_dir', side_effect=OSError('disconnected')):
            with self.assertRaises(OSError):
                cache.scan_and_save(empty)
        self.assertEqual(cache.cached_entries(empty), [])

    def test_grouping_options_isolated(self):
        self.assertEqual(len(cache.scan_and_save(self.root)), 2)
        self.assertIsNone(cache.cached_entries(self.root, collapse=False))
        self.assertEqual(len(cache.scan_and_save(self.root, collapse=False)), 3)
        self.assertEqual(len(cache.cached_entries(self.root)), 2)

    def test_tree_cache(self):
        self.assertIsNone(cache.cached_dirs(self.root))
        cache.save_dirs(self.root, False, ['models', 'textures'])
        with patch.object(os, 'scandir', side_effect=AssertionError('network read')):
            self.assertEqual(cache.cached_dirs(self.root), ['models', 'textures'])
        self.assertIsNone(cache.cached_dirs(self.root, True))

    def test_reconnect_new_file_only_invalidates_replaced_media(self):
        before = cache.scan_and_save(self.root)
        self.add('new.png')
        with open(os.path.join(self.root, 'photo.jpg'), 'ab') as f:
            f.write(b'changed')
        after = cache.scan_and_save(self.root)
        old = {(e.kind, e.name): e for e in before}
        changed = core.changed_existing_media(after, old, lambda e: (e.size, e.mtime))
        self.assertEqual([e.name for e in changed], ['photo.jpg'])
        self.assertIn('new.png', [e.name for e in after])

    def test_review_marks_reconcile_on_next_real_scan(self):
        before = cache.scan_and_save(self.root)
        self.assertFalse(any(e.review for e in before))
        self.add('photo.jpg.review.json')
        with patch.object(os, 'scandir', side_effect=AssertionError('network read')):
            self.assertFalse(any(e.review for e in cache.cached_entries(self.root)))
        after = cache.scan_and_save(self.root)
        self.assertTrue(next(e.review for e in after if e.name == 'photo.jpg'))
        os.remove(os.path.join(self.root, 'photo.jpg.review.json'))
        self.assertFalse(any(e.review for e in cache.scan_and_save(self.root)))

    def test_library_refs_from_cache(self):
        before = cache.scan_and_save(self.root)
        refs = [(e.key(), e.ref()) for e in before]
        with patch.object(core, 'scan_dir', side_effect=AssertionError('network read')):
            found, missing = core.resolve_refs(refs, cache_only=True)
        self.assertEqual(found, before)
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
