#!/usr/bin/env python3
"""Real native-window reopen, notebook persistence, JIT and session checks."""
from pathlib import Path
import json
import os
import shlex
import signal
import socket
import struct
import subprocess
import tempfile
import unittest
import uuid
from session_test import send, receive, SIZE

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / 'build/atelier-plugin-worker'

class AtelierTest(unittest.TestCase):
    def test_jit_compilation_and_crash_boundary(self):
        with tempfile.TemporaryDirectory(prefix='atelier-plugin-', dir=ROOT / 'build') as tmp:
            source = Path(tmp) / 'specimen.coil'
            cases = [
                ('; Leading comments and complete source snapshots work.\n(defn specimen [] (-> i64) 17)', 0, 'ATELIER/1 17'),
                ('(defn specimen [] (-> i64) missing-name)', 1, None),
                ('(extern abort :cc c [] (-> void))\n(defn specimen [] (-> i64) (abort) 7)', -signal.SIGABRT, None),
            ]
            for code, status, marker in cases:
                source.write_text(code)
                result = subprocess.run([str(WORKER), str(source)], cwd=ROOT,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, status, result.stderr)
                if marker:
                    self.assertIn(marker, result.stdout)

    def test_native_window_quit_reopen_preserves_shell_and_notebook(self):
        suite = 'dev.jim.atelier.test.' + uuid.uuid4().hex
        session_id = None
        try:
            with tempfile.TemporaryDirectory(prefix='atelier-window-', dir=ROOT / 'build') as tmp:
                env = dict(os.environ, JIM_ATELIER_PREFERENCES=suite)
                source = Path(tmp) / 'specimen.coil'
                env['JIM_ATELIER_PLUGIN'] = str(source)
                reports = []
                for generation, code in enumerate([
                    '(defn specimen [] (-> i64) 17)',
                    '(defn specimen [] (-> i64) missing-name)',
                    '(extern abort :cc c [] (-> void))\n(defn specimen [] (-> i64) (abort) 7)',
                ]):
                    source.write_text(code)
                    report = Path(tmp) / f'report-{generation}.json'
                    pid = Path(tmp) / f'pid-{generation}'
                    env['JIM_ATELIER_TEST_REPORT'] = str(report)
                    env['JIM_ATELIER_TEST_PID'] = str(pid)
                    env['JIM_ATELIER_TEST_COMMAND'] = 'printf "%s" $$ > ' + shlex.quote(str(pid))
                    result = subprocess.run([str(ROOT / 'build/atelier-integration')], cwd=ROOT,
                                            env=env, capture_output=True, text=True, timeout=45)
                    (ROOT / f'build/atelier-integration-{generation}.log').write_text(result.stdout + result.stderr)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    data = json.loads(report.read_text())
                    session_id = data['session']
                    with socket.socket(socket.AF_UNIX) as client:
                        client.settimeout(5)
                        client.connect(str(Path.home() / '.jim-coil/sessions' / (session_id + '.sock')))
                        send(client, 1, SIZE)
                        replay = bytearray()
                        while True:
                            kind, payload = receive(client)
                            if kind == 16:
                                replay.extend(payload)
                            if kind == 17:
                                break
                        (ROOT / f'build/atelier-replay-{generation}.log').write_bytes(replay)
                    self.assertEqual(data['plugin-phase'], 2 if generation == 0 else 3, result.stdout + result.stderr)
                    self.assertEqual(data['plugin-value'], 17)
                    self.assertTrue(pid.exists(), 'shell command did not complete; see build/atelier-integration-' + str(generation) + '.log')
                    self.assertTrue(pid.read_text().isdigit())
                    reports.append(data)
                self.assertEqual(reports[0]['session'], reports[1]['session'])
                self.assertEqual(reports[0]['session'], reports[2]['session'])
                self.assertEqual((Path(tmp) / 'pid-0').read_text(), (Path(tmp) / 'pid-1').read_text())
                self.assertEqual(reports[1]['notes'], reports[0]['notes'] + 1)
                self.assertEqual(reports[2]['notes'], reports[0]['notes'] + 2)
        finally:
            if not session_id:
                saved = subprocess.run(['defaults', 'read', suite, 'session-id'], capture_output=True, text=True)
                if saved.returncode == 0:
                    session_id = str(uuid.UUID(saved.stdout.strip())).upper()
            if session_id:
                path = Path.home() / '.jim-coil/sessions' / (session_id + '.sock')
                if path.exists():
                    with socket.socket(socket.AF_UNIX) as client:
                        client.connect(str(path))
                        client.sendall(struct.pack('!III', 0x4a494d31, 4, 0))
            # This namespace belongs exclusively to this test invocation.
            subprocess.run(['defaults', 'delete', suite], capture_output=True)

if __name__ == '__main__':
    unittest.main()
