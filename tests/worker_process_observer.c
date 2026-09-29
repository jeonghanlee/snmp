/* Observe the helper's own process boundaries without altering its behavior. */
#define _GNU_SOURCE
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

__attribute__((constructor)) static void observe_process(void)
{
    char executable[4096];
    ssize_t length = readlink("/proc/self/exe", executable, sizeof(executable) - 1);
    if (length < 0) _exit(122);
    executable[length] = 0;
    const char *name = strrchr(executable, '/');
    if (!name || strcmp(name + 1, "snmpWorker")) return;
    dprintf(STDERR_FILENO, "SNMPPROCESS pid=%ld exe=%s\n", (long)getpid(), executable);
    DIR *directory = opendir("/proc/self/fd");
    if (!directory) _exit(122);
    struct dirent *entry;
    while ((entry = readdir(directory))) {
        char *end;
        long descriptor = strtol(entry->d_name, &end, 10);
        if (*end || descriptor < 0 || descriptor == dirfd(directory)) continue;
        char path[64], target[4096];
        snprintf(path, sizeof(path), "/proc/self/fd/%ld", descriptor);
        length = readlink(path, target, sizeof(target) - 1);
        if (length < 0) _exit(122);
        target[length] = 0;
        dprintf(STDERR_FILENO, "SNMPPROCESS pid=%ld fd=%ld target=%s\n",
                (long)getpid(), descriptor, target);
    }
    closedir(directory);
}
