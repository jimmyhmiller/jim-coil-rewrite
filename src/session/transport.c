#include "transport.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <spawn.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
extern char **environ;

static int transfer(int fd, void *data, size_t length, int sending) {
    unsigned char *p = data;
    while (length) {
        ssize_t n = sending ? send(fd, p, length, 0) : recv(fd, p, length, 0);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0)
            return -1;
        p += n;
        length -= (size_t)n;
    }
    return 0;
}
int jim_session_send(int fd, uint32_t type, const void *bytes, size_t length) {
    if (length > 65536) {
        errno = EMSGSIZE;
        return -1;
    }
    uint32_t header[] = {htonl(0x4a494d31), htonl(type), htonl((uint32_t)length)};
    if (transfer(fd, header, sizeof(header), 1) < 0)
        return -1;
    return transfer(fd, (void *)bytes, length, 1);
}
int jim_session_receive(int fd, uint32_t *type, void *bytes, size_t capacity) {
    uint32_t header[3];
    if (transfer(fd, header, sizeof(header), 0) < 0)
        return -1;
    uint32_t length = ntohl(header[2]);
    if (ntohl(header[0]) != 0x4a494d31 || length > capacity || length > 65536) {
        errno = EPROTO;
        return -1;
    }
    *type = ntohl(header[1]);
    if (transfer(fd, bytes, length, 0) < 0)
        return -1;
    return (int)length;
}
int jim_session_connect(const char *path) {
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(path) >= sizeof(address.sun_path)) {
        errno = ENAMETOOLONG;
        return -1;
    }
    strcpy(address.sun_path, path);
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0)
        return -1;
    fcntl(fd, F_SETFD, FD_CLOEXEC);
    int yes = 1;
    setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &yes, sizeof(yes));
    if (connect(fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
        close(fd);
        return -1;
    }
    uid_t uid;
    gid_t gid;
    if (getpeereid(fd, &uid, &gid) < 0 || uid != getuid()) {
        close(fd);
        errno = EACCES;
        return -1;
    }
    return fd;
}
static int attach(int fd) {
    uint16_t size[] = {htons(80), htons(24), 0, 0};
    if (jim_session_send(fd, JIM_ATTACH, size, sizeof(size)) < 0) {
        close(fd);
        return -1;
    }
    return fd;
}
int jim_session_open(const char *executable, const char *path, const char *cwd,
                     const char *resources) {
    int fd = jim_session_connect(path);
    if (fd >= 0)
        return attach(fd);
    if (errno != ENOENT && errno != ECONNREFUSED)
        return -1;
    // posix_spawn is safe in the multithreaded renderer process. The service
    // detaches itself; the short-lived launcher is always reaped here.
    pid_t pid;
    char *argv[] = {(char *)executable, (char *)path, (char *)cwd, (char *)resources, NULL};
    posix_spawnattr_t attributes;
    int error = posix_spawnattr_init(&attributes);
    if (error) {
        errno = error;
        return -1;
    }
    error = posix_spawnattr_setflags(&attributes, POSIX_SPAWN_CLOEXEC_DEFAULT);
    if (!error)
        error = posix_spawn(&pid, executable, NULL, &attributes, argv, environ);
    posix_spawnattr_destroy(&attributes);
    if (error) {
        errno = error;
        return -1;
    }
    while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {
    }
    for (int i = 0; i < 200; i++) {
        fd = jim_session_connect(path);
        if (fd >= 0)
            return attach(fd);
        struct timespec delay = {0, 10000000};
        nanosleep(&delay, NULL);
    }
    return -1;
}
int jim_session_kill(const char *path) {
    int fd = jim_session_connect(path);
    if (fd < 0)
        return errno == ENOENT ? 0 : -1;
    int result = jim_session_send(fd, JIM_KILL, NULL, 0);
    close(fd);
    return result;
}
void jim_session_shutdown(int fd) { shutdown(fd, SHUT_RDWR); }
void jim_session_close(int fd) { close(fd); }
