// Jim's private per-terminal service. Owns the PTY and a Ghostty terminal core.
// The renderer is a disposable client. The lossless event journal preserves
// parser state (including partial sequences), both screens, and resize ordering.
// It is an anonymous disk file, not an ever-growing in-memory replay buffer.
#include "transport.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <ghostty/vt.h>
#include <libproc.h>
#include <limits.h>
#include <poll.h>
#include <pwd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <util.h>

#define CAP (65536 + 12)
#define INPUT_CAP (4 * 1024 * 1024)
typedef struct {
    int pty, client, journal;
    pid_t child;
    off_t end, cursor, replay_end;
    unsigned char tx[CAP], rx[CAP], input[INPUT_CAP];
    size_t tx_len, tx_at, rx_len, input_len, input_at;
    bool ready, exited, failed, stopping;
    GhosttyTerminal terminal;
    GhosttyColorScheme color_scheme;
    char cwd[PATH_MAX];
} Session;
static Session session;
static void nonblock(int fd) {
    int flags = fcntl(fd, F_GETFL);
    if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
        perror("fcntl");
        exit(1);
    }
}
static void disconnect_client(Session *s) {
    if (s->client >= 0)
        close(s->client);
    s->client = -1;
    s->rx_len = 0;
    s->tx_at = s->tx_len = 0;
    s->ready = false;
}
static void header(unsigned char *out, uint32_t type, size_t len) {
    uint32_t h[] = {htonl(0x4a494d31), htonl(type), htonl((uint32_t)len)};
    memcpy(out, h, 12);
}
static bool append(Session *s, uint32_t type, const void *bytes, size_t length) {
    unsigned char frame[CAP];
    header(frame, type, length);
    memcpy(frame + 12, bytes, length);
    size_t total = length + 12, at = 0;
    while (at < total) {
        ssize_t n = pwrite(s->journal, frame + at, total - at, s->end + (off_t)at);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0) {
            s->failed = true;
            return false;
        }
        at += (size_t)n;
    }
    s->end += (off_t)total;
    return true;
}
static void queue_input(Session *s, const void *bytes, size_t length) {
    if (s->exited)
        return;
    if (s->input_at) {
        memmove(s->input, s->input + s->input_at, s->input_len - s->input_at);
        s->input_len -= s->input_at;
        s->input_at = 0;
    }
    if (length > INPUT_CAP - s->input_len) {
        s->failed = true;
        return;
    }
    memcpy(s->input + s->input_len, bytes, length);
    s->input_len += length;
}
static void reply(GhosttyTerminal terminal, void *userdata, const uint8_t *data, size_t length) {
    (void)terminal;
    queue_input(userdata, data, length);
}
static bool attributes(GhosttyTerminal terminal, void *userdata, GhosttyDeviceAttributes *out) {
    (void)terminal;
    (void)userdata;
    memset(out, 0, sizeof(*out));
    out->primary.conformance_level = 62;
    out->primary.features[0] = 22;
    out->primary.features[1] = 52;
    out->primary.num_features = 2;
    out->secondary.device_type = 1;
    out->secondary.firmware_version = 10;
    return true;
}
static GhosttyColorScheme scheme(GhosttyTerminal terminal, void *userdata) {
    (void)terminal;
    return ((Session *)userdata)->color_scheme;
}
static void configure_colors(Session *s, const unsigned char *bytes, size_t length) {
    if (length != 777)
        return;
    GhosttyColorRgb colors[259];
    for (size_t i = 0; i < 259; i++)
        colors[i] = (GhosttyColorRgb){bytes[i * 3], bytes[i * 3 + 1], bytes[i * 3 + 2]};
    ghostty_terminal_set(s->terminal, GHOSTTY_TERMINAL_OPT_COLOR_FOREGROUND, colors);
    ghostty_terminal_set(s->terminal, GHOSTTY_TERMINAL_OPT_COLOR_BACKGROUND, colors + 1);
    ghostty_terminal_set(s->terminal, GHOSTTY_TERMINAL_OPT_COLOR_CURSOR, colors + 2);
    ghostty_terminal_set(s->terminal, GHOSTTY_TERMINAL_OPT_COLOR_PALETTE, colors + 3);
    s->color_scheme = (colors[1].r * 299 + colors[1].g * 587 + colors[1].b * 114 < 128000)
                          ? GHOSTTY_COLOR_SCHEME_DARK
                          : GHOSTTY_COLOR_SCHEME_LIGHT;
}
static void resize_session(Session *s, const unsigned char *bytes, size_t length) {
    if (length != 8)
        return;
    uint16_t v[4];
    memcpy(v, bytes, 8);
    for (int i = 0; i < 4; i++)
        v[i] = ntohs(v[i]);
    if (v[0] < 1 || v[1] < 1 || v[0] > 1000 || v[1] > 1000)
        return;
    struct winsize ws = {.ws_col = v[0], .ws_row = v[1], .ws_xpixel = v[2], .ws_ypixel = v[3]};
    if (!append(s, JIM_RESIZE, bytes, length))
        return;
    if (ghostty_terminal_resize(s->terminal, v[0], v[1], v[2] / v[0], v[3] / v[1]) !=
        GHOSTTY_SUCCESS) {
        s->failed = true;
        return;
    }
    if (!s->exited && ioctl(s->pty, TIOCSWINSZ, &ws) < 0)
        s->failed = true;
}
static void update_directory(Session *s) {
    if (s->exited)
        return;
    struct proc_vnodepathinfo info;
    pid_t foreground = tcgetpgrp(s->pty);
    if (foreground <= 0 || proc_pidinfo(foreground, PROC_PIDVNODEPATHINFO, 0, &info,
                                        sizeof(info)) != (int)sizeof(info))
        return;
    const char *cwd = info.pvi_cdir.vip_path;
    if (!cwd[0] || strcmp(cwd, s->cwd) == 0)
        return;
    strlcpy(s->cwd, cwd, sizeof(s->cwd));
    unsigned char osc[PATH_MAX * 3 + 64];
    size_t at = (size_t)snprintf((char *)osc, sizeof(osc), "file://localhost");
    const char hex[] = "0123456789ABCDEF";
    for (const unsigned char *p = (const unsigned char *)cwd; *p; p++) {
        unsigned char c = *p;
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
            c == '/' || c == '-' || c == '_' || c == '.' || c == '~')
            osc[at++] = c;
        else {
            osc[at++] = '%';
            osc[at++] = hex[c >> 4];
            osc[at++] = hex[c & 15];
        }
    }
    append(s, JIM_DIRECTORY, osc, at);
}
static void prepare_output(Session *s) {
    if (s->client < 0 || s->tx_at < s->tx_len)
        return;
    s->tx_at = s->tx_len = 0;
    if (!s->ready && s->cursor == s->replay_end) {
        header(s->tx, JIM_READY, 1);
        s->tx[12] = 1; // Renderer may send configured default colors.
        s->tx_len = 13;
        s->ready = true;
        return;
    }
    if (s->cursor >= s->end)
        return;
    if (pread(s->journal, s->tx, 12, s->cursor) != 12) {
        s->failed = true;
        return;
    }
    uint32_t length;
    memcpy(&length, s->tx + 8, 4);
    length = ntohl(length);
    if (length > 65536 ||
        pread(s->journal, s->tx + 12, length, s->cursor + 12) != (ssize_t)length) {
        s->failed = true;
        return;
    }
    s->tx_len = length + 12;
    s->cursor += (off_t)s->tx_len;
}
static void terminate_child(Session *s) {
    if (s->exited)
        return;
    pid_t foreground = tcgetpgrp(s->pty);
    if (foreground > 0)
        kill(-foreground, SIGHUP);
    kill(s->child, SIGHUP);
    for (int i = 0; i < 50; i++) {
        pid_t result = waitpid(s->child, NULL, WNOHANG);
        if (result == s->child || (result < 0 && errno == ECHILD)) {
            s->exited = true;
            return;
        }
        struct timespec delay = {0, 10000000};
        nanosleep(&delay, NULL);
    }
    if (foreground > 0)
        kill(-foreground, SIGKILL);
    kill(-s->child, SIGKILL);
    kill(s->child, SIGKILL);
    while (waitpid(s->child, NULL, 0) < 0 && errno == EINTR) {
    }
    s->exited = true;
}
static void accept_client(Session *s, int listener) {
    int fd = accept(listener, NULL, NULL);
    if (fd < 0)
        return;
    int flags = fcntl(fd, F_GETFL);
    if (flags < 0 || fcntl(fd, F_SETFL, flags & ~O_NONBLOCK) < 0) {
        close(fd);
        return;
    }
    uid_t uid;
    gid_t gid;
    if (getpeereid(fd, &uid, &gid) < 0 || uid != getuid()) {
        close(fd);
        return;
    }
    // An untrusted/incomplete first frame cannot stall the service indefinitely.
    struct timeval timeout = {.tv_sec = 0, .tv_usec = 100000};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    int yes = 1;
    setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &yes, sizeof(yes));
    unsigned char data[65536];
    uint32_t type = 0;
    int length = jim_session_receive(fd, &type, data, sizeof(data));
    if (length == 0 && type == JIM_KILL) {
        close(fd);
        s->stopping = true;
        return;
    }
    if (type != JIM_ATTACH || length != 8) {
        close(fd);
        return;
    }
    disconnect_client(s);
    s->client = fd;
    s->cursor = 0;
    s->replay_end = s->end;
    timeout.tv_usec = 0;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    nonblock(fd);
    resize_session(s, data, 8);
}
static void receive_input(Session *s) {
    ssize_t n = recv(s->client, s->rx + s->rx_len, CAP - s->rx_len, 0);
    if (n < 0 && (errno == EAGAIN || errno == EINTR))
        return;
    if (n <= 0) {
        disconnect_client(s);
        return;
    }
    s->rx_len += (size_t)n;
    while (s->rx_len >= 12) {
        uint32_t h[3];
        memcpy(h, s->rx, 12);
        uint32_t type = ntohl(h[1]), len = ntohl(h[2]);
        if (ntohl(h[0]) != 0x4a494d31 || len > 65536) {
            disconnect_client(s);
            return;
        }
        if (s->rx_len < len + 12)
            break;
        if (type == JIM_INPUT)
            queue_input(s, s->rx + 12, len);
        else if (type == JIM_COLORS)
            configure_colors(s, s->rx + 12, len);
        else if (type == JIM_RESIZE)
            resize_session(s, s->rx + 12, len);
        else {
            disconnect_client(s);
            return;
        }
        memmove(s->rx, s->rx + 12 + len, s->rx_len - 12 - len);
        s->rx_len -= 12 + len;
    }
}
static int private_directory(const char *path) {
    char directory[PATH_MAX];
    if (strlen(path) >= sizeof(directory))
        return -1;
    strcpy(directory, path);
    char *last = strrchr(directory, '/');
    if (!last)
        return -1;
    *last = 0;
    struct stat st;
    if (lstat(directory, &st) < 0)
        return -1;
    if (!S_ISDIR(st.st_mode) || st.st_uid != getuid() || (st.st_mode & 077) != 0) {
        errno = EACCES;
        return -1;
    }
    return 0;
}
int main(int argc, char **argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: jim-session SOCKET CWD GHOSTTY_RESOURCES [PROGRAM ARGS...]\n");
        return 2;
    }
    if (private_directory(argv[1]) < 0) {
        perror("private session directory");
        return 1;
    }
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(argv[1]) >= sizeof(address.sun_path))
        return 1;
    strcpy(address.sun_path, argv[1]);
    char lock_path[PATH_MAX];
    snprintf(lock_path, sizeof(lock_path), "%s.lock", argv[1]);
    int lock = open(lock_path, O_CREAT | O_RDWR | O_NOFOLLOW, 0600);
    if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB) < 0)
        return 1;
    pid_t detached = fork();
    if (detached < 0)
        return 1;
    if (detached > 0)
        return 0;
    if (setsid() < 0)
        _exit(1);
    detached = fork();
    if (detached < 0)
        _exit(1);
    if (detached > 0)
        _exit(0);
    int null = open("/dev/null", O_RDWR);
    for (int i = 0; i < 3; i++)
        dup2(null, i);
    if (null > 2)
        close(null);
    signal(SIGPIPE, SIG_IGN);
    umask(077);
    int listener = socket(AF_UNIX, SOCK_STREAM, 0);
    if (listener < 0)
        return 1;
    unlink(argv[1]);
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) < 0 || listen(listener, 8) < 0)
        return 1;
    fcntl(listener, F_SETFD, FD_CLOEXEC);
    fcntl(lock, F_SETFD, FD_CLOEXEC);
    nonblock(listener);
    FILE *journal = tmpfile();
    if (!journal)
        return 1;
    Session *s = &session;
    s->client = -1;
    s->color_scheme = GHOSTTY_COLOR_SCHEME_DARK;
    s->journal = fileno(journal);
    fcntl(s->journal, F_SETFD, FD_CLOEXEC);
    if (ghostty_terminal_new(
            NULL, &s->terminal,
            (GhosttyTerminalOptions){.cols = 80, .rows = 24, .max_scrollback = 10000}) !=
        GHOSTTY_SUCCESS)
        return 1;
    ghostty_terminal_set(s->terminal, GHOSTTY_TERMINAL_OPT_USERDATA, s);
    ghostty_terminal_set(s->terminal, GHOSTTY_TERMINAL_OPT_WRITE_PTY, reply);
    ghostty_terminal_set(s->terminal, GHOSTTY_TERMINAL_OPT_DEVICE_ATTRIBUTES, attributes);
    ghostty_terminal_set(s->terminal, GHOSTTY_TERMINAL_OPT_COLOR_SCHEME, scheme);
    struct winsize ws = {.ws_col = 80, .ws_row = 24};
    s->child = forkpty(&s->pty, NULL, NULL, &ws);
    if (s->child < 0)
        return 1;
    if (s->child == 0) {
        close(listener);
        close(lock);
        close(s->journal);
        signal(SIGPIPE, SIG_DFL);
        if (chdir(argv[2]) < 0) {
            perror("project directory");
            _exit(1);
        }
        setenv("TERM", "xterm-ghostty", 1);
        setenv("TERM_PROGRAM", "ghostty", 1);
        setenv("COLORTERM", "truecolor", 1);
        char terminfo[PATH_MAX];
        if (snprintf(terminfo, sizeof(terminfo), "%s/../terminfo", argv[3]) >=
            (int)sizeof(terminfo))
            _exit(1);
        setenv("TERMINFO", terminfo, 1);
        setenv("GHOSTTY_RESOURCES_DIR", argv[3], 1);
        if (argc > 4) {
            execvp(argv[4], argv + 4);
            _exit(127);
        }
        struct passwd *pw = getpwuid(getuid());
        const char *shell = pw && pw->pw_shell[0] ? pw->pw_shell : "/bin/zsh";
        execl(shell, shell, "-l", (char *)NULL);
        _exit(127);
    }
    nonblock(s->pty);
    uint16_t initial[] = {htons(80), htons(24), 0, 0};
    append(s, JIM_RESIZE, initial, 8);
    while (!s->failed && !s->stopping) {
        update_directory(s);
        prepare_output(s);
        struct pollfd fds[] = {
            {listener, POLLIN, 0},
            {s->pty, s->exited ? 0 : (POLLIN | (s->input_at < s->input_len ? POLLOUT : 0)), 0},
            {s->client,
             (s->input_len - s->input_at < INPUT_CAP - 2 * 65536 ? POLLIN : 0) |
                 (s->tx_at < s->tx_len ? POLLOUT : 0),
             0}};
        if (poll(fds, 3, 200) < 0) {
            if (errno == EINTR)
                continue;
            break;
        }
        if (fds[0].revents & POLLIN)
            accept_client(s, listener);
        if (!s->exited && fds[1].revents & (POLLIN | POLLHUP)) {
            unsigned char data[32768];
            ssize_t n = read(s->pty, data, sizeof(data));
            if (n > 0) {
                if (!append(s, JIM_OUTPUT, data, (size_t)n))
                    break;
                ghostty_terminal_vt_write(s->terminal, data, (size_t)n);
            } else if (n == 0 || (n < 0 && errno == EIO)) {
                int status = 0;
                pid_t result = waitpid(s->child, &status, WNOHANG);
                if (result == s->child) {
                    s->exited = true;
                    uint32_t code = htonl(WIFEXITED(status) ? (uint32_t)WEXITSTATUS(status)
                                                            : 128 + (uint32_t)WTERMSIG(status));
                    append(s, JIM_EXITED, &code, 4);
                    close(s->pty);
                    s->pty = -1;
                }
            }
        }
        if (!s->exited && fds[1].revents & POLLOUT) {
            ssize_t n = write(s->pty, s->input + s->input_at, s->input_len - s->input_at);
            if (n > 0)
                s->input_at += (size_t)n;
            if (s->input_at == s->input_len)
                s->input_at = s->input_len = 0;
        }
        // accept may have replaced the client since poll: never apply the old
        // client's readiness flags to the new descriptor.
        if (s->client >= 0 && fds[2].fd == s->client) {
            if (fds[2].revents & (POLLIN | POLLHUP | POLLERR))
                receive_input(s);
            if (s->client >= 0 && fds[2].revents & POLLOUT) {
                ssize_t n = send(s->client, s->tx + s->tx_at, s->tx_len - s->tx_at, 0);
                if (n > 0)
                    s->tx_at += (size_t)n;
                else if (n < 0 && errno != EAGAIN && errno != EINTR)
                    disconnect_client(s);
            }
        }
    }
    if (s->failed && s->client >= 0)
        jim_session_send(s->client, JIM_ERROR, "Terminal service stopped: journal or I/O failure",
                         47);
    terminate_child(s);
    disconnect_client(s);
    if (s->pty >= 0)
        close(s->pty);
    ghostty_terminal_free(s->terminal);
    fclose(journal);
    close(listener);
    unlink(argv[1]);
    close(lock);
    return s->failed ? 1 : 0;
}
