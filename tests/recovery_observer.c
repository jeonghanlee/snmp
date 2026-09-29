#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <unistd.h>

/* Observe real filesystem opens and received UDP bytes without altering them. */
static void file_event(const char *path)
{
    int saved = errno;
    char line[4096];
    int count = snprintf(line, sizeof(line), "SNMPFILE pid=%ld path=%s\n", (long)getpid(), path);
    if (count > 0 && count < (int)sizeof(line)) syscall(SYS_write, 2, line, count);
    errno = saved;
}

int open(const char *path, int flags, ...)
{
    static int (*next)(const char *, int, ...) = NULL;
    if (!next) next = dlsym(RTLD_NEXT, "open");
    mode_t mode = 0;
    if ((flags & O_CREAT) || (flags & O_TMPFILE) == O_TMPFILE) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, int);
        va_end(args);
    }
    file_event(path);
    return next(path, flags, mode);
}

int open64(const char *path, int flags, ...)
{
    static int (*next)(const char *, int, ...) = NULL;
    if (!next) next = dlsym(RTLD_NEXT, "open64");
    mode_t mode = 0;
    if ((flags & O_CREAT) || (flags & O_TMPFILE) == O_TMPFILE) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, int);
        va_end(args);
    }
    file_event(path);
    return next(path, flags, mode);
}

FILE *fopen(const char *path, const char *mode)
{
    static FILE *(*next)(const char *, const char *) = NULL;
    if (!next) next = dlsym(RTLD_NEXT, "fopen");
    file_event(path);
    return next(path, mode);
}

FILE *fopen64(const char *path, const char *mode)
{
    static FILE *(*next)(const char *, const char *) = NULL;
    if (!next) next = dlsym(RTLD_NEXT, "fopen64");
    file_event(path);
    return next(path, mode);
}

int __open64_2(const char *path, int flags)
{
    static int (*next)(const char *, int) = NULL;
    if (!next) next = dlsym(RTLD_NEXT, "__open64_2");
    file_event(path);
    return next(path, flags);
}

static void receive_event(int fd, const void *buffer, ssize_t received)
{
    int saved = errno;
    if (received > 0 && received <= 2048) {
        char line[4608];
        int offset = snprintf(line, sizeof(line), "SNMPRECEIVE pid=%ld fd=%d bytes=%ld hex=",
                              (long)getpid(), fd, (long)received);
        const unsigned char *bytes = buffer;
        for (ssize_t i = 0; i < received; ++i) offset += snprintf(line + offset, 3, "%02x", bytes[i]);
        line[offset++] = '\n';
        syscall(SYS_write, 2, line, offset);
    }
    errno = saved;
}

ssize_t recvfrom(int fd, void *buffer, size_t size, int flags, struct sockaddr *address, socklen_t *length)
{
    static ssize_t (*next)(int, void *, size_t, int, struct sockaddr *, socklen_t *) = NULL;
    if (!next) next = dlsym(RTLD_NEXT, "recvfrom");
    ssize_t received = next(fd, buffer, size, flags, address, length);
    if (received > 0 && (size_t)received <= size) receive_event(fd, buffer, received);
    return received;
}

ssize_t recvmsg(int fd, struct msghdr *message, int flags)
{
    static ssize_t (*next)(int, struct msghdr *, int) = NULL;
    if (!next) next = dlsym(RTLD_NEXT, "recvmsg");
    ssize_t received = next(fd, message, flags);
    int saved = errno;
    if (received > 0 && received <= 2048) {
        unsigned char packet[2048];
        size_t copied = 0;
        for (size_t i = 0; i < message->msg_iovlen && copied < (size_t)received; ++i) {
            size_t part = message->msg_iov[i].iov_len;
            if (part > (size_t)received - copied) part = (size_t)received - copied;
            memcpy(packet + copied, message->msg_iov[i].iov_base, part);
            copied += part;
        }
        if (copied == (size_t)received) receive_event(fd, packet, received);
    }
    errno = saved;
    return received;
}
