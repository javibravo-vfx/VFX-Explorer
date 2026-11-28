"""Storage policy tests: Windows APIs mocked; real files for identity checks."""
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from contextlib import ExitStack
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vfxexplorer import core, storage, storage_cache, media_process


class RoutingTests(unittest.TestCase):
    def setUp(self):
        storage._drive_cache.clear()
        storage._nonlocal_mappings.clear()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(storage, 'IS_WIN', True))
        self.stack.enter_context(patch.object(storage, '_drive_type', side_effect=lambda d: 4 if d in ('T:', 'E:') else 3))
        self.stack.enter_context(patch.object(storage, 'local_names', return_value={'workstation', 'localhost'}))
        self.stack.enter_context(patch.object(storage, '_mapped_unc', side_effect=lambda d: {'T:': r'\\workstation\assets\jobs', 'E:': r'\\nas\library'}.get(d)))
        self.share = self.stack.enter_context(patch.object(storage, '_share_path', return_value='W:\\'))

    def test_fixed_disk_and_subst_like_fixed_disk(self):
        self.assertIsNone(core.net_root(r'C:\photo.exr'))
        self.assertIsNone(core.net_root(r'W:\photo.exr'))
        self.assertIsNone(core.net_root(r'S:\photo.exr'))
        self.assertIsNone(storage.local_candidate(r'C:\photo.exr'))
        self.assertFalse(media_process.isolated(r'C:\photo.exr'))

    def test_smb_local_candidate_keeps_logical_network_identity(self):
        self.assertEqual(storage.local_candidate(r'T:\shot\plate.exr'), r'W:\jobs\shot\plate.exr')
        self.assertEqual(core.net_root(r'T:\shot\plate.exr'), 'T:')
        self.assertEqual(storage.local_candidate(r'\\WORKSTATION\assets\jobs\plate.exr'), r'W:\jobs\plate.exr')
        self.assertEqual(storage.local_candidate(r'\\?\UNC\WORKSTATION\assets\plate.exr'), r'W:\plate.exr')
        self.assertEqual(core.net_root(r'\\?\UNC\WORKSTATION\assets\plate.exr'), r'\\WORKSTATION\assets')

    def test_remote_mapping_does_not_resolve_share_locally(self):
        self.assertIsNone(storage.local_candidate(r'E:\plate.exr'))
        self.share.assert_not_called()
        self.assertTrue(media_process.isolated(r'E:\plate.exr'))
        self.assertNotEqual(storage.queue_key(r'T:\plate.exr'), storage.queue_key(r'E:\plate.exr'))
        self.assertNotEqual(storage.queue_key(r'\\nas1\share\plate.exr'), storage.queue_key(r'\\nas2\share\plate.exr'))
        self.assertEqual(storage.queue_key(r'\\NAS1\share\plate.exr'), storage.queue_key(r'\\nas1\share\foo.exr'))

    def test_unverified_alias_traversal_and_remote_share_target(self):
        self.assertIsNone(storage.local_candidate(r'\\workstation.other\assets\plate.exr'))
        self.assertIsNone(storage.local_candidate(r'T:\..\plate.exr'))
        self.assertIsNone(storage.local_candidate(r'T:\plate.exr:stream'))
        self.share.return_value = 'E:\\'
        self.assertIsNone(storage.local_candidate(r'T:\plate.exr'))

    def test_disconnected_mapping_never_uses_remembered_path_for_decode(self):
        with patch.object(storage, '_mapped_unc', return_value=None):
            self.assertIsNone(storage.local_candidate(r'T:\plate.exr'))
        self.assertTrue(media_process.isolated(r'T:\plate.exr'))

    def test_mapping_change_rechecks_before_direct_route(self):
        self.assertIsNotNone(storage.local_candidate(r'T:\plate.exr'))
        with patch.object(storage, '_mapped_unc', return_value=r'\\nas\assets'):
            self.assertIsNone(storage.local_candidate(r'T:\plate.exr'))

    def test_disconnected_remembered_drive_is_network_sensitive(self):
        with patch.object(storage, '_drive_type', return_value=1), patch.object(storage, '_remembered', return_value=r'\\nas\library'):
            self.assertEqual(core.net_root(r'Z:\photo.exr'), 'Z:')

    def test_remote_cache_base_uses_local_data(self):
        with patch.object(core, 'app_dir', return_value=r'E:\app'), patch.dict(os.environ, {'LOCALAPPDATA': r'C:\Users\test\AppData\Local'}):
            self.assertEqual(storage_cache.cache_home(), os.path.join(r'C:\Users\test\AppData\Local', 'VFX Explorer'))

    def test_gui_never_resolves_smb_native_path(self):
        with patch.object(storage, 'local_candidate', side_effect=AssertionError('blocking lookup')):
            self.assertEqual(storage.native_read_path(r'T:\photo.exr'), r'T:\photo.exr')


class IdentityTests(unittest.TestCase):
    def test_same_file_verified_mismatch_and_missing_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            logical = os.path.join(tmp, 'network.exr')
            actual = os.path.join(tmp, 'local.exr')
            other = os.path.join(tmp, 'different.exr')
            with open(actual, 'wb') as f:
                f.write(b'image')
            os.link(actual, logical)
            with open(other, 'wb') as f:
                f.write(b'image')
            with patch.object(storage, 'IS_WIN', True), patch.object(core, 'net_root', return_value='T:'), patch.object(storage, '_file_id', return_value=None), patch.object(storage, '_fixed_final_path', side_effect=lambda p: p), ThreadPoolExecutor(1) as pool:
                with patch.object(storage, 'local_candidate', return_value=actual):
                    self.assertEqual(pool.submit(storage.native_read_path, logical).result(), actual)
                with patch.object(storage, 'local_candidate', return_value=other):
                    self.assertEqual(pool.submit(storage.native_read_path, logical).result(), logical)
                with patch.object(storage, 'local_candidate', return_value=actual):
                    self.assertEqual(pool.submit(storage.native_read_path, logical + '.missing').result(), logical + '.missing')
                with patch.object(storage, 'local_candidate', return_value=actual), patch.object(storage, '_fixed_final_path', return_value=None):
                    self.assertEqual(pool.submit(storage.native_read_path, logical).result(), logical)


if __name__ == '__main__':
    unittest.main(verbosity=2)
