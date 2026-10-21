import difflib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('repair', Path(__file__).resolve().parents[1] / 'scripts/repair_runtime.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = self.root / 'patches'
        self.patches.mkdir()
        self.dist = SimpleNamespace(version='0.6.4', locate_file=lambda _: self.root)
        self.manifest = {'version': '0.6.4', 'id': 'test', 'files': []}
        for i in range(2):
            original, fixed = f'value = {i}\n', f'value = {i + 10}\n'
            target = self.root / 'babeldoc' / f'file{i}.py'
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(original.encode())
            patchfile = f'{i}.patch'
            (self.patches / patchfile).write_text(''.join(difflib.unified_diff(original.splitlines(True), fixed.splitlines(True), 'a', 'b')))
            self.manifest['files'].append({'path': f'babeldoc/file{i}.py', 'patch': patchfile,
                                          'original_sha256': repair.sha(original.encode()),
                                          'patched_sha256': repair.sha(fixed.encode())})
        self.save_manifest()

    def tearDown(self):
        self.tmp.cleanup()

    def save_manifest(self):
        (self.patches / 'manifest.json').write_text(json.dumps(self.manifest))

    def run_repair(self, action):
        return repair.repair(self.dist, action, self.patches)

    def hashes(self):
        return [repair.sha((self.root / f['path']).read_bytes()) for f in self.manifest['files']]

    def test_apply_check_idempotence_and_rollback(self):
        original = self.hashes()
        self.assertFalse(self.run_repair('check')['applied'])
        self.assertTrue(self.run_repair('apply')['applied'])
        self.assertEqual(self.hashes(), [f['patched_sha256'] for f in self.manifest['files']])
        self.assertTrue(self.run_repair('apply')['applied'])
        self.assertTrue(self.run_repair('check')['applied'])
        self.assertFalse(self.run_repair('rollback')['applied'])
        self.assertEqual(self.hashes(), original)

    def test_all_files_preflighted_before_write(self):
        (self.root / 'babeldoc/file1.py').write_text('local change\n')
        before = self.hashes()
        with self.assertRaisesRegex(ValueError, 'Unknown engine file'):
            self.run_repair('apply')
        self.assertEqual(self.hashes(), before)

    def test_wrong_version_rejected(self):
        self.dist.version = '0.6.5'
        with self.assertRaisesRegex(ValueError, 'Expected BabelDOC'):
            self.run_repair('apply')

    def test_modified_patch_rejected(self):
        p = self.patches / '0.patch'
        p.write_text(p.read_text().replace('+value = 10', '+value = 99'))
        before = self.hashes()
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.run_repair('apply')
        self.assertEqual(self.hashes(), before)

    def test_missing_verified_backup_rejected(self):
        self.run_repair('apply')
        (self.root / '.babeldoc-pdf-translate-compat/test/babeldoc/file0.py').unlink()
        with self.assertRaisesRegex(ValueError, 'rollback copy missing'):
            self.run_repair('rollback')

    def test_failure_during_second_write_restores_first(self):
        before = self.hashes()
        writer = repair.atomic_write
        def fail_second(path, data, mode=0o644):
            if path == self.root / 'babeldoc/file1.py':
                raise OSError('simulated disk error')
            writer(path, data, mode)
        with patch.object(repair, 'atomic_write', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'disk error'):
                self.run_repair('apply')
        self.assertEqual(self.hashes(), before)

    def test_path_escape_rejected(self):
        self.manifest['files'][0]['path'] = '../outside.py'
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'Unsafe patch path'):
            self.run_repair('apply')

    def test_incorrect_patch_context_rejected(self):
        with self.assertRaisesRegex(ValueError, 'context mismatch'):
            repair.apply_diff(b'value = 0\n', '--- a\n+++ b\n@@ -1 +1 @@\n-value = 9\n+value = 10\n')

    def test_migration_requires_verified_previous_backup(self):
        self.run_repair('apply')
        self.manifest['previous_id'] = 'test'
        self.manifest['id'] = 'test2'
        self.save_manifest()
        self.assertTrue(self.run_repair('apply')['applied'])
        self.assertTrue((self.root / '.babeldoc-pdf-translate-compat/test2/babeldoc/file0.py').exists())
        self.assertFalse(self.run_repair('rollback')['applied'])


if __name__ == '__main__':
    unittest.main()
