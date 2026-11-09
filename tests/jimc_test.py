#!/usr/bin/env python3
"""What `jimc` asks for, and what it does with the answer, against a stand-in for the app."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
JIMC = ROOT / 'build/jimc'


class FakeApp:
    """Answers one connection at a time, keeping every request it was sent."""

    def __init__(self, path, reply=b'{"ok":true}\n'):
        self.reply = reply
        self.requests = []
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind(path)
        self.listener.listen()
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while True:
            try:
                connection, _ = self.listener.accept()
            except OSError:
                return
            with connection:
                data = b''
                while not data.endswith(b'\n'):
                    part = connection.recv(65536)
                    if not part:
                        break
                    data += part
                self.requests.append(data)
                connection.sendall(self.reply)

    def close(self):
        self.listener.close()


class JimcTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='jimc-', dir='/tmp')
        self.path = str(Path(self.tmp.name) / 'socket')
        self.app = FakeApp(self.path)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.app.close)

    def run_jimc(self, *args, cwd=None):
        return subprocess.run([str(JIMC), *args], capture_output=True, text=True, timeout=10,
                              cwd=cwd or self.tmp.name,
                              env={**os.environ, 'JIM_COIL_SOCKET': self.path})

    def asks(self, args, expected, cwd=None):
        """`jimc ARGS` sends exactly the request EXPECTED, as one line."""
        self.app.requests.clear()
        result = self.run_jimc(*args, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.app.requests), 1)
        line = self.app.requests[0]
        self.assertTrue(line.endswith(b'\n'))
        self.assertEqual(line.count(b'\n'), 1)
        self.assertEqual(json.loads(line), expected)

    def refuses(self, args, expected):
        """`jimc ARGS` is a usage error that says EXPECTED, and asks the app nothing."""
        self.app.requests.clear()
        result = self.run_jimc(*args)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn(expected, result.stderr)
        self.assertEqual(self.app.requests, [])

    def test_every_command_spells_its_request(self):
        here = os.path.realpath(self.tmp.name)
        cases = [
            (['status'], {'action': 'status'}),
            (['project', 'list'], {'action': 'list_projects'}),
            (['project', 'new', 'Two words'], {'action': 'new_project', 'name': 'Two words'}),
            (['project', 'new', 'A', '--dir', '/x', '--background'],
             {'action': 'new_project', 'name': 'A', 'directory': '/x', 'background': True}),
            (['project', 'activate', '12'], {'action': 'activate_project', 'project': '12'}),
            (['project', 'set-dir', '/x', '--project', 'A'],
             {'action': 'set_project_directory', 'project': 'A', 'directory': '/x'}),
            (['project', 'delete', 'A', '--yes'], {'action': 'delete_project', 'project': 'A'}),
            (['pane', 'list', '--project', 'A'], {'action': 'list_panes', 'project': 'A'}),
            (['pane', 'focus', '3'], {'action': 'focus_pane', 'pane': 3}),
            (['pane', 'close', '3', '--project', 'A'],
             {'action': 'close_pane', 'project': 'A', 'pane': 3}),
            (['pane', 'move', '3', '-10', '20'],
             {'action': 'move_pane', 'pane': 3, 'x': -10, 'y': 20}),
            (['pane', 'move', '3', '1', '2', '640', '480'],
             {'action': 'move_pane', 'pane': 3, 'x': 1, 'y': 2, 'w': 640, 'h': 480}),
            (['pane', 'pin', '3'], {'action': 'pin_pane', 'pane': 3}),
            (['pane', 'unpin', '3', '--project', 'A'],
             {'action': 'unpin_pane', 'project': 'A', 'pane': 3}),
            (['pane', 'move-to', '3', 'Work'],
             {'action': 'move_pane_to_project', 'pane': 3, 'to': 'Work'}),
            (['pane', 'move-to', '3', '7', '--project', 'A'],
             {'action': 'move_pane_to_project', 'project': 'A', 'pane': 3, 'to': '7'}),
            (['term', 'new', '--dir', '/x', '--at', '1,2,300,400'],
             {'action': 'new_terminal', 'directory': '/x', 'x': 1, 'y': 2, 'w': 300, 'h': 400}),
            (['term', 'send', '3', 'ls "a"\n', '--enter'],
             {'action': 'send_text', 'pane': 3, 'text': 'ls "a"\n', 'enter': True}),
            (['term', 'send', '3', '--', '--not-a-flag'],
             {'action': 'send_text', 'pane': 3, 'text': '--not-a-flag'}),
            (['term', 'read', '3'], {'action': 'read_terminal', 'pane': 3}),
            (['term', 'scroll', '3', '-5'], {'action': 'scroll_terminal', 'pane': 3, 'lines': -5}),
            (['widget', 'list'], {'action': 'list_widgets'}),
            (['widget', 'open', 'markdown', 'README.md', '--at', '5,6'],
             {'action': 'open_widget', 'spec': 'markdown README.md', 'x': 5, 'y': 6}),
            (['canvas', 'fit'], {'action': 'fit_canvas'}),
            (['action', 'list'], {'action': 'list_actions'}),
            (['action', 'run', '32', '--answer', 'working'],
             {'action': 'run_action', 'id': 32, 'answer': 'working'}),
            (['action', 'run', 'Diff: Open diff wall'],
             {'action': 'run_action', 'name': 'Diff: Open diff wall'}),
            (['msg', 'topic', 'body'], {'action': 'message', 'topic': 'topic', 'body': 'body'}),
            (['msg', 'topic'], {'action': 'message', 'topic': 'topic'}),
            (['raw', '{"action":"status","extra":1}'], {'action': 'status', 'extra': 1}),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.asks(args, expected)

    def test_paths_are_the_callers_not_the_apps(self):
        here = os.path.realpath(self.tmp.name)
        (Path(here) / 'sub').mkdir()
        self.asks(['project', 'set-dir'],
                  {'action': 'set_project_directory', 'directory': here})
        self.asks(['project', 'set-dir', 'sub'],
                  {'action': 'set_project_directory', 'directory': here + '/sub'})
        self.asks(['term', 'new', '--dir', 'sub'],
                  {'action': 'new_terminal', 'directory': here + '/sub'})

    def test_a_diff_wall_opens_on_this_directory_unless_told_otherwise(self):
        here = os.path.realpath(self.tmp.name)
        self.asks(['diff-wall'], {'action': 'diff_wall', 'directory': here})
        self.asks(['diff-wall', 'range', 'main', 'exclude=a b', '--background'],
                  {'action': 'diff_wall', 'spec': 'range main exclude=a b', 'background': True,
                   'directory': here})
        self.asks(['diff-wall', 'repo=/x', 'staged'],
                  {'action': 'diff_wall', 'spec': 'repo=/x staged'})
        spaced = Path(here) / 'with space'
        spaced.mkdir()
        self.asks(['diff-wall'], {'action': 'diff_wall', 'directory': str(spaced)}, cwd=spaced)

    def test_a_bad_command_line_never_reaches_the_app(self):
        for args, expected in [
            (['nonsense'], 'no such command: nonsense'),
            (['project'], 'project takes'),
            (['project', 'nonsense'], 'project takes'),
            (['project', 'new'], 'one NAME'),
            (['project', 'delete', 'A'], 'pass --yes'),
            (['project', 'list', '--nonsense'], 'no flag --nonsense'),
            (['pane', 'focus'], 'pane ID'),
            (['pane', 'close', 'x'], 'pane ID'),
            (['pane', 'move', '3', '1'], 'ID X Y'),
            (['pane', 'move', '3', '1', 'y'], 'ID X Y'),
            (['pane', 'pin'], 'pane ID'),
            (['pane', 'move-to', '3'], 'ID and one PROJECT'),
            (['pane', 'move-to', 'x', 'Work'], 'pane ID'),
            (['pane', 'list', '--project'], 'needs a value'),
            (['term', 'send', '3'], 'one TEXT'),
            (['term', 'scroll', '3'], 'number of LINES'),
            (['term', 'scroll', '3', 'up'], 'number of LINES'),
            (['term', 'new', '--at', '1'], '--at takes'),
            (['term', 'new', '--at', '1,2,3,4,5'], '--at takes'),
            (['term', 'new', '--at', '1,y'], '--at takes'),
            (['widget', 'open'], 'needs a NAME'),
            (['action', 'run'], 'TITLE or ID'),
            (['msg'], 'msg takes'),
            (['status', 'extra'], 'no arguments'),
            (['raw'], 'one JSON'),
        ]:
            with self.subTest(args=args):
                self.refuses(args, expected)

    def test_help_goes_to_stdout_and_asks_nothing(self):
        for args in [[], ['help'], ['--help'], ['-h']]:
            result = self.run_jimc(*args)
            self.assertEqual(result.returncode, 0)
            self.assertIn('usage: jimc', result.stdout)
        self.assertEqual(self.app.requests, [])

    def test_the_reply_is_printed_and_decides_the_exit_code(self):
        self.app.reply = b'{"ok":true,"id":3}\n'
        result = self.run_jimc('status')
        self.assertEqual((result.returncode, result.stdout), (0, '{"ok":true,"id":3}\n'))
        self.app.reply = b'{"ok":false,"error":"No"}\n'
        result = self.run_jimc('status')
        self.assertEqual((result.returncode, result.stdout), (1, '{"ok":false,"error":"No"}\n'))
        self.app.reply = b'not json\n'
        self.assertEqual(self.run_jimc('status').returncode, 1)

    def test_says_so_when_the_app_is_not_running(self):
        self.app.close()
        os.unlink(self.path)
        result = self.run_jimc('status')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout),
                         {'ok': False, 'error': 'Jim Coil is not running'})


if __name__ == '__main__':
    unittest.main()
