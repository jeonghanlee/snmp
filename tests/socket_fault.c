/* One-shot faults at the owned IOC's real Linux socket boundary. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static pthread_once_t resolved = PTHREAD_ONCE_INIT;
static int (*real_socket)(int, int, int);
static ssize_t (*real_sendto)(int, const void *, size_t, int, const struct sockaddr *, socklen_t);
static ssize_t (*real_sendmsg)(int, const struct msghdr *, int);

static void resolve(void)
{
    real_socket = dlsym(RTLD_NEXT, "socket");
    real_sendto = dlsym(RTLD_NEXT, "sendto");
    real_sendmsg = dlsym(RTLD_NEXT, "sendmsg");
    if (!real_socket || !real_sendto || !real_sendmsg) abort();
}

static int fail_once(char mode, const char *operation, int error, unsigned port)
{
    const char *control = getenv("SNMP_TEST_SOCKET_CONTROL");
    const char *log = getenv("SNMP_TEST_SOCKET_LOG");
    char selected = 0;
    int fd;
    if (!control || !log) return 0;
    fd = open(control, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return 0;
    ssize_t count = read(fd, &selected, 1);
    close(fd);
    if (count != 1 || selected != mode || unlink(control)) return 0;
    struct timespec stamp;
    clock_gettime(CLOCK_MONOTONIC, &stamp);
    fd = open(log, O_WRONLY | O_APPEND | O_CREAT | O_NOFOLLOW, 0600);
    if (fd >= 0) {
        char entry[256];
        int length = snprintf(entry, sizeof(entry),
            "{\"time\":%llu,\"operation\":\"%s\",\"errno\":%d,\"port\":%u}\n",
            (unsigned long long)stamp.tv_sec * 1000000000ULL + stamp.tv_nsec,
            operation, error, port);
        if (write(fd, entry, (size_t)length) != length) abort();
        close(fd);
    }
    errno = error;
    return 1;
}

static unsigned target_port(const struct sockaddr *address, socklen_t length)
{
    const char *selected = getenv("SNMP_TEST_SOCKET_PORT");
    if (!selected || !address || length < sizeof(struct sockaddr_in) || address->sa_family != AF_INET)
        return 0;
    const struct sockaddr_in *ipv4 = (const struct sockaddr_in *)address;
    unsigned port = ntohs(ipv4->sin_port);
    return ipv4->sin_addr.s_addr == htonl(INADDR_LOOPBACK) && port == strtoul(selected, NULL, 10) ? port : 0;
}

int socket(int domain, int type, int protocol)
{
    pthread_once(&resolved, resolve);
    if (domain == AF_INET && (type & 0xf) == SOCK_DGRAM && fail_once('O', "socket", EMFILE, 0))
        return -1;
    return real_socket(domain, type, protocol);
}

ssize_t sendto(int fd, const void *buffer, size_t length, int flags,
               const struct sockaddr *address, socklen_t address_length)
{
    pthread_once(&resolved, resolve);
    unsigned port = target_port(address, address_length);
    if (port && fail_once('S', "sendto", EIO, port)) return -1;
    return real_sendto(fd, buffer, length, flags, address, address_length);
}

ssize_t sendmsg(int fd, const struct msghdr *message, int flags)
{
    pthread_once(&resolved, resolve);
    unsigned port = target_port(message->msg_name, message->msg_namelen);
    if (port && fail_once('S', "sendmsg", EIO, port)) return -1;
    return real_sendmsg(fd, message, flags);
}
