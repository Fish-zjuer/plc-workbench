import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from plc_agent.codesys_check import check


class CodesysCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / 'CODESYS/Common/CODESYS.exe'
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b'fixture')
        template = self.exe.parent.parent / 'Templates/Standard.project'
        template.parent.mkdir()
        template.write_bytes(b'fixture project')

    def test_exit_zero_without_compiler_evidence_is_not_success(self):
        with patch('plc_agent.codesys_check.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'')):
            result = check(self.exe, 'fixture profile', self.root / 'output')
        self.assertEqual(result['status'], 'setup_incomplete')

    def test_valid_code_pass_without_rejecting_invalid_code_is_not_success(self):
        def respond(*args, **kwargs):
            job = json.loads(Path(kwargs['env']['PLC_CODESYS_JOB']).read_text(encoding='utf-8'))
            Path(job['output']).write_text(json.dumps({'status': 'pass', 'stage': 'compiled'}), encoding='utf-8')
            return subprocess.CompletedProcess([], 0, b'')
        with patch('plc_agent.codesys_check.subprocess.run', side_effect=respond):
            result = check(self.exe, 'fixture profile', self.root / 'output')
        self.assertEqual(result['status'], 'setup_incomplete')

    def test_profile_cannot_inject_raw_command_line_options(self):
        with patch('plc_agent.codesys_check.subprocess.run') as run:
            with self.assertRaises(ValueError):
                check(self.exe, 'profile" --runscript="other.py', self.root / 'output')
            run.assert_not_called()
