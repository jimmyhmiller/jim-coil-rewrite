#!/usr/bin/env python3
"""Exercise the real service through its public local socket protocol."""
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEADER = struct.Struct('!III')
SIZE = struct.pack('!HHHH', 80, 24, 800, 480)


def send(sock, kind, data=b''):
    sock.sendall(HEADER.pack(0x4a494d31, kind, len(data)) + data)


def exact(sock, count):
    data = bytearray()
    while len(data) < count:
        part = sock.recv(count - len(data))
        if not part:
            raise EOFError('session disconnected')
        data.extend(part)
    return bytes(data)


def receive(sock):
    magic, kind, length = HEADER.unpack(exact(sock, 12))
    assert magic == 0x4a494d31 and length <= 65536
    return kind, exact(sock, length)


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='jim-session-', dir='/tmp')
        self.directory = Path(self.tmp.name)
        self.path = str(self.directory / 'terminal.sock')
        subprocess.run([str(ROOT / 'build/jim-session'), self.path, self.tmp.name,
                        str(ROOT / 'build/ghostty/share/ghostty'), '/bin/sh', '-i'], check=True)
        self.clients = []
        for _ in range(200):
            if Path(self.path).exists():
                break
            time.sleep(.01)

    def connect(self):
        sock = socket.socket(socket.AF_UNIX)
        sock.settimeout(5)
        sock.connect(self.path)
        self.clients.append(sock)
        return sock

    def attach(self):
        sock = self.connect()
        send(sock, 1, SIZE)
        replay = bytearray()
        while True:
            kind, data = receive(sock)
            if kind == 16:
                replay.extend(data)
            if kind == 17:
                return sock, bytes(replay)

    def until(self, sock, marker):
        data = bytearray()
        deadline = time.monotonic() + 5
        while marker not in data and time.monotonic() < deadline:
            kind, part = receive(sock)
            if kind == 16:
                data.extend(part)
        self.assertIn(marker, data)
        return bytes(data)

    def tearDown(self):
        for client in self.clients:
            client.close()
        if Path(self.path).exists():
            with self.connect() as sock:
                send(sock, 4)
            for _ in range(200):
                if not Path(self.path).exists():
                    break
                time.sleep(.01)
            self.assertFalse(Path(self.path).exists(), 'explicit close must stop the daemon')
        self.tmp.cleanup()

    def test_shell_and_work_continue_after_detach(self):
        client, _ = self.attach()
        send(client, 2, b'printf "%s" $$ > shell-pid; (sleep .3; printf completed > detached-result) &\n')
        deadline = time.monotonic() + 5
        pidfile = self.directory / 'shell-pid'
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        pid = pidfile.read_text()
        client.close()
        result = self.directory / 'detached-result'
        while not result.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(result.read_text(), 'completed')
        second, replay = self.attach()
        send(second, 2, b'printf "%s" $$ > reattached-pid; printf "RECONNECTED_%s\\n" yes\n')
        self.until(second, b'RECONNECTED_yes')
        self.assertEqual((self.directory / 'reattached-pid').read_text(), pid)
        self.assertIn(b'shell-pid', replay)

    def test_core_answers_queries_without_a_renderer(self):
        client, _ = self.attach()
        # Query while detached; the child cannot finish unless the daemon's
        # terminal core supplies the cursor-position response itself.
        code = "import os,tty,time; tty.setraw(0); time.sleep(.3); os.write(1,b'\\x1b[6n'); r=os.read(0,64); open('query-result','wb').write(r)"
        import shlex
        send(client, 2, ('python3 -c ' + shlex.quote(code) + '\n').encode())
        time.sleep(.1)
        client.close()
        file = self.directory / 'query-result'
        deadline = time.monotonic() + 5
        while not file.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertRegex(file.read_bytes(), rb'\x1b\[\d+;\d+R')

    def test_invalid_frame_cannot_kill_session(self):
        bad = self.connect()
        bad.sendall(HEADER.pack(0x4a494d31, 1, 0xffffffff))
        self.assertEqual(bad.recv(1), b'')
        client, _ = self.attach()
        send(client, 2, b'printf "HEALTH_%s\\n" yes\n')
        self.until(client, b'HEALTH_yes')

    def test_reconnect_preserves_exact_output_and_resize_order(self):
        client, _ = self.attach()
        send(client, 3, struct.pack('!HHHH', 91, 27, 910, 540))
        send(client, 2, b'printf "\\033[?1049h\\033[31mALT_%s\\033[0m\\033[?1049l\\n" yes\n')
        self.until(client, b'ALT_yes')
        client.close()
        second, replay = self.attach()
        self.assertIn(b'\x1b[?1049h\x1b[31mALT_yes\x1b[0m\x1b[?1049l', replay)
        send(second, 2, b'printf "AFTER_%s\\n" yes\n')
        self.until(second, b'AFTER_yes')

    def test_shell_has_ghostty_terminfo(self):
        client, _ = self.attach()
        send(client, 2, b'printf "%s" "$TERMINFO" > terminfo; printf "%s" "$TERM" > term; printf "ENV_%s\\n" yes\n')
        self.until(client, b'ENV_yes')
        self.assertEqual((self.directory / 'term').read_text(), 'xterm-ghostty')
        database = Path((self.directory / 'terminfo').read_text())
        self.assertTrue(database.is_dir())
        self.assertTrue(list(database.rglob('xterm-ghostty')))

    def test_exited_shell_remains_readable_until_explicit_close(self):
        client, _ = self.attach()
        send(client, 2, b'printf "FINAL_%s\\n" yes; exit 7\n')
        while True:
            kind, data = receive(client)
            if kind == 18:
                break
        client.close()
        second = self.connect()
        send(second, 1, SIZE)
        output = bytearray()
        exited = False
        while True:
            kind, data = receive(second)
            if kind == 16:
                output.extend(data)
            if kind == 18:
                exited = True
            if kind == 17:
                break
        self.assertTrue(exited)
        self.assertIn(b'FINAL_yes', output)

    def test_configured_colors_drive_terminal_queries(self):
        client, _ = self.attach()
        colors = bytes([220, 230, 240, 17, 21, 28, 110, 190, 230]) + bytes(768)
        send(client, 5, colors)
        import shlex
        code = "import os,tty; tty.setraw(0); os.write(1,b'\\x1b]11;?\\x07'); r=os.read(0,128); open('color-response','wb').write(r)"
        send(client, 2, ('python3 -c ' + shlex.quote(code) + '\n').encode())
        file = self.directory / 'color-response'
        deadline = time.monotonic() + 5
        while not file.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertIn(b'rgb:1111/1515/1c1c', file.read_bytes())

    def test_detached_output_larger_than_transport_buffers_is_lossless(self):
        client, _ = self.attach()
        import shlex
        code = "import os,time; time.sleep(.1); os.write(1,b'BEGIN_JOURNAL'+b'x'*(8*1024*1024)+b'END_JOURNAL'); open('finished','w').write('yes')"
        send(client, 2, ('python3 -c ' + shlex.quote(code) + '\n').encode())
        client.close()
        deadline = time.monotonic() + 10
        while not (self.directory / 'finished').exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue((self.directory / 'finished').exists())
        _, replay = self.attach()
        self.assertIn(b'BEGIN_JOURNAL' + b'x' * (8 * 1024 * 1024) + b'END_JOURNAL', replay)


if __name__ == '__main__':
    unittest.main()
