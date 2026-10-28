import os, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import explorer


class SampleLab(unittest.TestCase):
    """The practice area in the guide must really contain what the guide says it does."""

    @classmethod
    def setUpClass(cls):
        subprocess.run(['bash', str(ROOT / 'sample-lab' / 'setup.sh')], check=True, capture_output=True)
        cls.lab = str(ROOT / 'sample-lab' / 'lab')

    def entry(self, folder, name):
        return next(e for e in explorer.list_dir(os.path.join(self.lab, folder), True)['entries'] if e['name'] == name)

    def test_world_writable_and_suid_files_are_flagged(self):
        self.assertTrue(any('Anyone' in f for f in self.entry('shared', 'notes.txt')['flags']))
        self.assertTrue(any('SUID' in f for f in self.entry('tools', 'suid-demo')['flags']))
        self.assertEqual(self.entry('', '.ssh')['mode'], 'drwx------')
        self.assertEqual(self.entry('.ssh', 'authorized_keys')['mode'], '-rw-------')

    def test_exercise_answers(self):
        failed = explorer.search(self.lab, 'Failed password', 'content')['results']
        self.assertTrue(failed and all(r['path'].endswith('logs/auth.log') for r in failed))
        found = explorer.search(self.lab, 'suid', 'name')['results']
        self.assertEqual([os.path.basename(r['path']) for r in found], ['suid-demo'])
        log = (Path(self.lab) / 'logs' / 'auth.log').read_text()
        self.assertEqual(log.count('Failed password for'), 5)
        self.assertEqual(log.count('Accepted password for backup from 203.0.113.9'), 1)


if __name__ == '__main__':
    unittest.main()
