#!/usr/bin/env python3
"""Exercise the real service through its public local socket protocol."""
import os
from pathlib import Path
import select
import shlex
import signal
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

    def events(self, directory=None):
        return ((directory or self.directory) / 'events.log').read_text()

    def service_pid(self, path):
        found = subprocess.run(['pgrep', '-f', f'jim-session {path}'],
                               capture_output=True, text=True).stdout.split()
        self.assertTrue(found, 'service not running')
        return int(found[0])

    def wait_gone(self, pid):
        for _ in range(1000):
            if subprocess.run(['kill', '-0', str(pid)], capture_output=True).returncode:
                return
            time.sleep(.01)
        self.fail(f'service {pid} did not exit')

    def test_events_name_who_attached_and_who_killed(self):
        pid = self.service_pid(self.path)
        sock, _ = self.attach()
        with self.connect() as killer:
            send(killer, 4)
            self.assertEqual(killer.recv(1), b'')
        self.wait_gone(pid)
        events = self.events()
        self.assertIn('service-start', events)
        self.assertIn(f'attach peer_pid={os.getpid()}', events)
        self.assertIn(f'kill-requested peer_pid={os.getpid()}', events)
        self.assertIn('ending-shell', events)
        self.assertIn('client-dropped reason=service-stopping', events)
        self.assertIn('service-exit failed=0 stopping=1', events)

    def test_events_name_a_replaced_client(self):
        first, _ = self.attach()
        second, _ = self.attach()
        self.assertIn('client-dropped reason=replaced-by-new-attach', self.events())

    def test_events_name_a_closed_client(self):
        sock, _ = self.attach()
        sock.close()
        self.clients.remove(sock)
        deadline = time.monotonic() + 5
        while 'client-closed' not in self.events() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertIn('client-dropped reason=client-closed', self.events())

    def test_events_record_how_the_shell_exited(self):
        sock, _ = self.attach()
        send(sock, 2, b'exit 7\n')
        deadline = time.monotonic() + 5
        while 'shell-exited-on-its-own' not in self.events() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertRegex(self.events(), r'shell-exited-on-its-own pid=\d+ code=7 signal=0')

    def test_events_name_who_signalled_the_service(self):
        pid = self.service_pid(self.path)
        os.kill(pid, signal.SIGTERM)
        self.wait_gone(pid)
        Path(self.path).unlink(missing_ok=True)
        self.assertIn(f'signal number=15 from_pid={os.getpid()}', self.events())

    def test_a_full_disk_does_not_touch_a_terminal(self):
        """Its temporary directory is on a full volume. Output flows, with nothing lost."""
        with tempfile.TemporaryDirectory(prefix='jim-full-', dir='/tmp') as tmp:
            directory = Path(tmp)
            image = directory / 'tiny.dmg'
            volume = directory / 'volume'
            volume.mkdir()
            subprocess.run(['hdiutil', 'create', '-quiet', '-size', '8m', '-fs', 'HFS+',
                            '-volname', 'jimfull', str(image)], check=True)
            subprocess.run(['hdiutil', 'attach', '-quiet', '-nobrowse', '-mountpoint',
                            str(volume), str(image)], check=True)
            pid = None
            try:
                free = os.statvfs(volume)
                (volume / 'filler').write_bytes(bytes(free.f_bavail * free.f_frsize))
                path = str(directory / 'terminal.sock')
                subprocess.run([str(ROOT / 'build/jim-session'), path, tmp,
                                str(ROOT / 'build/ghostty/share/ghostty'), '/bin/sh', '-i'],
                               check=True, env=dict(os.environ, TMPDIR=f'{volume}/'))
                for _ in range(500):
                    if Path(path).exists():
                        break
                    time.sleep(.01)
                pid = self.service_pid(path)
                sock = socket.socket(socket.AF_UNIX)
                sock.settimeout(30)
                sock.connect(path)
                send(sock, 1, SIZE)
                while receive(sock)[0] != 17:
                    pass
                send(sock, 2, b'seq 1 300000; echo FINISHED-$((6*7))\n')
                output = bytearray()
                while b'FINISHED-42' not in output:
                    kind, data = receive(sock)
                    if kind == 16:
                        output.extend(data)
                self.assertNotIn('FAILED', self.events(directory))
                sock.close()

                # Replayed from the journal: every line, in order.
                sock = socket.socket(socket.AF_UNIX)
                sock.settimeout(30)
                sock.connect(path)
                send(sock, 1, SIZE)
                replay = bytearray()
                while True:
                    kind, data = receive(sock)
                    if kind == 16:
                        replay.extend(data)
                    if kind == 17:
                        break
                sock.close()
                for received in (output, replay):
                    numbers = [line for line in bytes(received).replace(b'\r', b'').split(b'\n')
                               if line.isdigit()]
                    self.assertEqual(numbers, [b'%d' % n for n in range(1, 300001)])
            finally:
                if pid:
                    subprocess.run(['kill', '-9', str(pid)], capture_output=True)
                    self.wait_gone(pid)
                subprocess.run(['hdiutil', 'detach', '-force', '-quiet', str(volume)])

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

    def test_closed_launcher_stdio_does_not_close_shell_pty(self):
        path = str(self.directory / 'closed-stdio.sock')
        subprocess.run(
            [str(ROOT / 'build/jim-session'), path, self.tmp.name,
             str(ROOT / 'build/ghostty/share/ghostty'), '/bin/sh', '-i'],
            check=True,
            preexec_fn=lambda: os.closerange(0, 3),
        )
        for _ in range(200):
            if Path(path).exists():
                break
            time.sleep(.01)
        sock = socket.socket(socket.AF_UNIX)
        sock.settimeout(5)
        sock.connect(path)
        send(sock, 1, SIZE)
        while receive(sock)[0] != 17:
            pass
        send(sock, 2, b'printf "CLOSED_STDIO_%s\\n" yes\n')
        data = bytearray()
        while b'CLOSED_STDIO_yes' not in data:
            kind, part = receive(sock)
            if kind == 16:
                data.extend(part)
        sock.close()
        killer = socket.socket(socket.AF_UNIX)
        killer.connect(path)
        send(killer, 4)
        killer.close()

    def test_core_answers_queries_without_a_renderer(self):
        client, _ = self.attach()
        # Query while detached; the child cannot finish unless the daemon's
        # terminal core supplies the cursor-position response itself.
        code = "import os,tty,time; tty.setraw(0); time.sleep(.3); os.write(1,b'\\x1b[6n'); r=os.read(0,64); open('query-result.part','wb').write(r); os.rename('query-result.part','query-result')"
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

    def test_attaching_does_not_resize_the_terminal(self):
        client, _ = self.attach()
        send(client, 3, struct.pack('!HHHH', 91, 27, 910, 540))
        send(client, 2, b'stty size\n')
        self.until(client, b'27 91')
        client.close()
        # The second attach carries a placeholder size, as every attach does.
        second, _ = self.attach()
        send(second, 2, b'stty size\n')
        self.until(second, b'27 91')

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
        code = "import os,tty; tty.setraw(0); os.write(1,b'\\x1b]11;?\\x07'); r=os.read(0,128); open('color-response.part','wb').write(r); os.rename('color-response.part','color-response')"
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

    def test_history_keeps_the_newest_64_mib(self):
        client, _ = self.attach()
        # A mode and a directory set before the history that gets trimmed.
        code = ("import os; os.chdir(os.environ['PWD']+'/moved'); os.write(1,b'\\x1b[?2004h'); "
                "os.write(1,b'OLDEST_HISTORY'); [os.write(1,b'y'*(1<<20)) for _ in range(90)]; "
                "os.write(1,b'NEWEST_HISTORY'); open('../finished','w').write('yes'); "
                "import time; time.sleep(30)")
        (self.directory / 'moved').mkdir()
        send(client, 2, ('python3 -c ' + shlex.quote(code) + '\n').encode())
        client.close()
        deadline = time.monotonic() + 60
        while not (self.directory / 'finished').exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue((self.directory / 'finished').exists())
        time.sleep(.5)
        # Trimmed history's memory really goes back: 64 MiB, plus the service's own.
        resident = subprocess.run(['ps', '-o', 'rss=', '-p', str(self.service_pid(self.path))],
                                  capture_output=True, text=True).stdout
        self.assertLess(int(resident), 160 * 1024)

        sock = self.connect()
        send(sock, 1, SIZE)
        frames = []
        while True:
            kind, data = receive(sock)
            if kind == 17:
                break
            frames.append((kind, data))
        self.assertEqual(frames[0][0], 3, 'replay must begin with the size history was written at')
        directories = [data for kind, data in frames if kind == 20]
        self.assertTrue(any(b'/moved' in data for data in directories))
        output = [data for kind, data in frames if kind == 16]
        replay = b''.join(output)
        self.assertLessEqual(len(replay), 64 * 1024 * 1024 + 1024 * 1024)
        self.assertGreater(len(replay), 60 * 1024 * 1024)
        self.assertNotIn(b'OLDEST_HISTORY', replay)
        self.assertIn(b'NEWEST_HISTORY', replay)
        # The mode was set in trimmed history, so it arrives after the replay.
        self.assertIn(b'\x1b[?2004h', output[-1])
        sock.close()
        # A second attach sees the same bounded history and stays usable.
        again, second = self.attach()
        self.assertIn(b'NEWEST_HISTORY', second)
        again.close()

    def test_client_that_stops_reading_loses_its_connection_not_the_terminal(self):
        client = self.connect()
        send(client, 1, SIZE)
        while receive(client)[0] != 17:
            pass
        code = "import os; [os.write(1,b'z'*(1<<20)) for _ in range(300)]; open('stalled-done','w').write('y')"
        send(client, 2, ('python3 -c ' + shlex.quote(code) + '\n').encode())
        deadline = time.monotonic() + 120
        while not (self.directory / 'stalled-done').exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue((self.directory / 'stalled-done').exists(),
                        'a client that stops reading must not stop the terminal')
        time.sleep(.5)
        client.settimeout(10)
        self.assertRaises((EOFError, OSError), lambda: [receive(client) for _ in range(100000)])
        second, _ = self.attach()
        send(second, 2, b'printf "AFTER_STALL_%s\\n" yes\n')
        self.until(second, b'AFTER_STALL_yes')


DAEMON = Path(os.environ.get(
    'JIM_ORIGINAL_DAEMON',
    Path.home() / 'Documents/Code/jim-editor/Jim.app/Contents/MacOS/jim-daemon'))


def legacy_frame(payload):
    return struct.pack('!I', len(payload)) + payload


def legacy_size(variant, cols, rows):
    return legacy_frame(bytes([variant, cols, rows]))


def legacy_input(data):
    length = bytes([len(data)]) if len(data) < 251 else b'\xfb' + struct.pack('<H', len(data))
    return legacy_frame(bytes([1]) + length + data)


LEGACY_KILL = legacy_frame(bytes([4]))


@unittest.skipUnless(DAEMON.exists(), f'original Jim daemon not built at {DAEMON}')
class AdoptionTest(unittest.TestCase):
    """Adopt a real original Jim daemon, isolated in a private runtime directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='jim-adopt-', dir='/tmp')
        self.directory = Path(self.tmp.name)
        self.runtime = self.directory / 'r'
        self.runtime.mkdir(mode=0o700)
        self.sessions = self.directory / 's'
        self.sessions.mkdir(mode=0o700)
        self.path = str(self.sessions / 'terminal.sock')
        self.upstream = str(self.runtime / '7.sock')
        env = dict(os.environ,
                   TERMINAL_BEVY_RUNTIME_DIR=str(self.runtime),
                   EDITOR_IDEA_TERMINAL_INITIAL_CWD=str(self.directory))
        subprocess.run([str(DAEMON), '7', '/bin/sh', '-i'], check=True, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.wait_for(lambda: Path(self.upstream).exists())
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        if Path(self.path).exists():
            with socket.socket(socket.AF_UNIX) as sock:
                try:
                    sock.connect(self.path)
                    send(sock, 4)
                except OSError:
                    pass
            self.wait_for(lambda: not Path(self.path).exists(), required=False)
        if Path(self.upstream).exists():
            with socket.socket(socket.AF_UNIX) as sock:
                try:
                    sock.connect(self.upstream)
                    sock.sendall(LEGACY_KILL)
                except OSError:
                    pass
            self.wait_for(lambda: not Path(self.upstream).exists(), required=False)
        self.tmp.cleanup()

    def wait_for(self, condition, seconds=10, required=True):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if condition():
                return True
            time.sleep(.01)
        if required:
            self.fail('condition not reached in time')
        return False

    def as_original_jim(self, *messages, cols=132, rows=43):
        """Do what original Jim does: attach at its size, then send messages."""
        sock = socket.socket(socket.AF_UNIX)
        sock.settimeout(5)
        sock.connect(self.upstream)
        self.clients.append(sock)
        sock.sendall(legacy_size(0, cols, rows))
        for message in messages:
            sock.sendall(message)
        return sock

    def shell(self, command, file):
        """Run COMMAND in the shell as original Jim, and wait for FILE, then detach."""
        sock = self.as_original_jim(legacy_input(command))
        self.wait_for(lambda: (self.directory / file).exists()
                      and (self.directory / file).stat().st_size > 0)
        sock.close()
        self.clients.remove(sock)

    def adopt(self):
        result = subprocess.run(
            [str(ROOT / 'build/jim-session'), '--adopt', self.upstream, self.path,
             self.tmp.name, str(ROOT / 'build/ghostty/share/ghostty')])
        self.assertEqual(result.returncode, 0)

        def answering():
            with socket.socket(socket.AF_UNIX) as probe:
                try:
                    probe.connect(self.path)
                    return True
                except OSError:
                    return False
        self.wait_for(answering)

    def attach(self):
        sock = socket.socket(socket.AF_UNIX)
        sock.settimeout(10)
        sock.connect(self.path)
        self.clients.append(sock)
        send(sock, 1, SIZE)
        frames = []
        while True:
            kind, data = receive(sock)
            if kind == 17:
                return sock, frames
            frames.append((kind, data))

    def replay_of(self, frames):
        return b''.join(data for kind, data in frames if kind == 16)

    def until_file(self, name):
        path = self.directory / name
        self.wait_for(lambda: path.exists() and path.stat().st_size > 0)
        return path.read_text().strip()

    def alive(self, pid):
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False

    def test_same_shell_keeps_its_history_and_takes_input(self):
        self.shell(b'printf "%s" $$ > pid; printf "HISTORY_%s\\n" yes\n', 'pid')
        pid = (self.directory / 'pid').read_text()
        self.adopt()
        client, frames = self.attach()
        self.assertIn(b'HISTORY_yes', self.replay_of(frames))
        send(client, 2, b'printf "%s" $$ > pid-after\n')
        self.assertEqual(self.until_file('pid-after'), pid)

    def test_adoption_leaves_the_terminal_size_alone(self):
        self.shell(b'stty size > before\n', 'before')
        self.assertEqual(self.until_file('before'), '43 132')
        self.adopt()
        client, frames = self.attach()
        self.assertEqual(frames[0][0], 3)
        self.assertEqual(struct.unpack('!HH', frames[0][1][:4]), (132, 43),
                         'history must replay at the width it was written')
        send(client, 2, b'stty size > during\n')
        self.assertEqual(self.until_file('during'), '43 132')

    def test_resize_reaches_the_shell(self):
        self.adopt()
        client, _ = self.attach()
        send(client, 3, struct.pack('!HHHH', 91, 27, 910, 540))
        time.sleep(.3)
        send(client, 2, b'stty size > resized\n')
        self.assertEqual(self.until_file('resized'), '27 91')

    def test_queries_are_answered_with_no_renderer_attached(self):
        self.adopt()
        client, _ = self.attach()
        code = ("import os,tty,time; tty.setraw(0); time.sleep(.3); os.write(1,b'\\x1b[6n'); "
                "r=os.read(0,64); open('query-result.part','wb').write(r); os.rename('query-result.part','query-result')")
        send(client, 2, ('python3 -c ' + shlex.quote(code) + '\n').encode())
        time.sleep(.1)
        client.close()
        file = self.directory / 'query-result'
        self.wait_for(lambda: file.exists())
        self.assertRegex(file.read_bytes(), rb'\x1b\[\d+;\d+R')

    def test_queries_in_history_are_not_answered_again(self):
        # The query is in the daemon's history; adoption replays it into the core
        # while this program is still listening for anything sent to the shell.
        code = ("import os,tty,select; tty.setraw(0); os.write(1,b'\\x1b[6n'); open('asked','w').write('y'); "
                "r=select.select([0],[],[],2.5)[0]; d=os.read(0,64) if r else b''; "
                "open('heard.part','wb').write(b'[' + d + b']'); os.rename('heard.part','heard')")
        self.shell(('python3 -c ' + shlex.quote(code) + '\n').encode(), 'asked')
        self.adopt()
        self.wait_for(lambda: (self.directory / 'heard').exists())
        self.assertEqual((self.directory / 'heard').read_bytes(), b'[]')

    def test_directory_of_the_foreground_process_is_reported(self):
        (self.directory / 'moved').mkdir()
        self.adopt()
        client, _ = self.attach()
        send(client, 2, b'cd moved\n')
        deadline = time.monotonic() + 5
        seen = False
        while not seen and time.monotonic() < deadline:
            kind, data = receive(client)
            seen = kind == 20 and b'/moved' in data
        self.assertTrue(seen)

    def test_closing_the_app_leaves_shell_and_service_running(self):
        self.shell(b'printf "%s" $$ > pid\n', 'pid')
        self.adopt()
        client, _ = self.attach()
        client.close()
        time.sleep(.3)
        second, _ = self.attach()
        send(second, 2, b'printf "%s" $$ > pid-after\n')
        self.assertEqual(self.until_file('pid-after'), (self.directory / 'pid').read_text())

    def test_explicit_close_ends_the_shell_and_its_daemon(self):
        self.shell(b'printf "%s" $$ > pid\n', 'pid')
        pid = (self.directory / 'pid').read_text()
        self.adopt()
        with socket.socket(socket.AF_UNIX) as sock:
            sock.connect(self.path)
            send(sock, 4)
        self.wait_for(lambda: not Path(self.path).exists())
        self.wait_for(lambda: not Path(self.upstream).exists())
        self.wait_for(lambda: not self.alive(pid))

    def test_original_jim_taking_the_terminal_back_stops_the_service_not_the_shell(self):
        self.shell(b'printf "%s" $$ > pid\n', 'pid')
        pid = (self.directory / 'pid').read_text()
        self.adopt()
        client, _ = self.attach()
        jim = self.as_original_jim()
        deadline = time.monotonic() + 5
        kind = None
        while kind != 19 and time.monotonic() < deadline:
            kind, _ = receive(client)
        self.assertEqual(kind, 19)
        self.wait_for(lambda: not Path(self.path).exists())
        self.assertTrue(self.alive(pid))
        # It does not reconnect: original Jim keeps the terminal, undisturbed.
        jim.sendall(legacy_input(b'printf "%s" $$ > pid-jim\n'))
        self.assertEqual(self.until_file('pid-jim'), pid)

    def test_service_that_dies_can_adopt_again(self):
        self.shell(b'printf "%s" $$ > pid; printf "HISTORY_%s\\n" yes\n', 'pid')
        pid = (self.directory / 'pid').read_text()
        self.adopt()
        service = subprocess.run(['lsof', '-t', self.path], capture_output=True, text=True).stdout.split()
        self.assertTrue(service)
        os.kill(int(service[0]), signal.SIGKILL)
        self.assertTrue(self.alive(pid))
        time.sleep(.2)
        self.adopt()
        client, frames = self.attach()
        self.assertIn(b'HISTORY_yes', self.replay_of(frames))
        send(client, 2, b'printf "%s" $$ > pid-after\n')
        self.assertEqual(self.until_file('pid-after'), pid)

    def test_exited_shell_remains_readable_until_explicit_close(self):
        self.adopt()
        client, _ = self.attach()
        send(client, 2, b'printf "FINAL_%s\\n" yes; exit 7\n')
        deadline = time.monotonic() + 5
        code = None
        while code is None and time.monotonic() < deadline:
            kind, data = receive(client)
            if kind == 18:
                code = struct.unpack('!I', data)[0]
        self.assertEqual(code, 7)
        client.close()
        second, frames = self.attach()
        self.assertIn(b'FINAL_yes', self.replay_of(frames))
        self.assertIn(18, [kind for kind, _ in frames])

    def test_shell_that_exited_before_adoption_reports_history_then_exit(self):
        # The daemon lingers for a shell that exits while nobody is attached.
        sock = self.as_original_jim(legacy_input(b'(sleep .3; printf "FINAL_%s\\n" yes; kill -9 $$) &\n'))
        time.sleep(.1)
        sock.close()
        self.clients.remove(sock)
        time.sleep(.7)
        self.adopt()
        _, frames = self.attach()
        kinds = [kind for kind, _ in frames]
        self.assertIn(b'FINAL_yes', self.replay_of(frames))
        self.assertIn(18, kinds)
        self.assertGreater(kinds.index(18), kinds.index(16), 'exit follows the history')

    def test_daemon_that_is_gone_is_reported_to_the_launcher(self):
        result = subprocess.run(
            [str(ROOT / 'build/jim-session'), '--adopt', str(self.runtime / '99.sock'), self.path,
             self.tmp.name, str(ROOT / 'build/ghostty/share/ghostty')])
        self.assertEqual(result.returncode, 3)
        self.assertFalse(Path(self.path).exists())

    def test_daemon_out_of_reach_is_not_reported_gone(self):
        # Only a daemon that is really gone may cost a pane its link to it.
        locked = self.directory / 'locked'
        locked.mkdir()
        locked.chmod(0)
        try:
            result = subprocess.run(
                [str(ROOT / 'build/jim-session'), '--adopt', str(locked / '7.sock'), self.path,
                 self.tmp.name, str(ROOT / 'build/ghostty/share/ghostty')])
        finally:
            locked.chmod(0o700)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(Path(self.path).exists())


if __name__ == '__main__':
    unittest.main()
