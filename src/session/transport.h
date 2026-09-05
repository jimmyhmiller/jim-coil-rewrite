#ifndef JIM_SESSION_TRANSPORT_H
#define JIM_SESSION_TRANSPORT_H
#include <stddef.h>
#include <stdint.h>
// Every frame: JIM1, big-endian type, big-endian payload length.
// Maximum payload is 64 KiB. The journal uses the identical framing.
enum {
    JIM_ATTACH = 1,
    JIM_INPUT = 2,
    JIM_RESIZE = 3,
    JIM_KILL = 4,
    JIM_COLORS = 5,
    JIM_OUTPUT = 16,
    JIM_READY = 17,
    JIM_EXITED = 18,
    JIM_ERROR = 19,
    JIM_DIRECTORY = 20
};
int jim_session_send(int fd, uint32_t type, const void *bytes, size_t length);
int jim_session_receive(int fd, uint32_t *type, void *bytes, size_t capacity);
int jim_session_connect(const char *path);
int jim_session_open(const char *executable, const char *path, const char *cwd,
                     const char *resources);
int jim_session_kill(const char *path);
void jim_session_shutdown(int fd);
void jim_session_close(int fd);
#endif
