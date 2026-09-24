/* Observe actual module-to-library calls without replacing their targets.
 * Linux x86-64 rtld-audit ABI; no arguments or return registers are modified.
 */
#define _GNU_SOURCE
#include <link.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static int observed(const char *name)
{
    return !strcmp(name, "snmp_open") || !strcmp(name, "snmp_close") ||
           !strcmp(name, "snmp_sess_open") || !strcmp(name, "snmp_sess_close");
}

static void report(const char *event, const char *name, unsigned long result)
{
    char line[192];
    struct timespec stamp;
    if (clock_gettime(CLOCK_MONOTONIC, &stamp)) _exit(120);
    int size = snprintf(line, sizeof(line), "SNMPNATIVE %ld %llu %s %s %lu\n",
                        (long)getpid(), (unsigned long long)stamp.tv_sec * 1000000000ull + stamp.tv_nsec,
                        event, name, result);
    if (size <= 0 || (size_t)size >= sizeof(line) || write(STDERR_FILENO, line, size) != size)
        _exit(121);
}

unsigned int la_version(unsigned int version)
{
    return version >= LAV_CURRENT ? LAV_CURRENT : 0;
}

unsigned int la_objopen(struct link_map *map, Lmid_t lmid, uintptr_t *cookie)
{
    (void)lmid;
    (void)cookie;
    if (strstr(map->l_name, "/libnetsnmp.so")) return LA_FLG_BINDTO;
    if (!map->l_name[0] || strstr(map->l_name, "/libdevSnmp.so")) return LA_FLG_BINDFROM;
    return 0;
}

uintptr_t la_symbind64(Elf64_Sym *sym, unsigned int index, uintptr_t *from,
                     uintptr_t *to, unsigned int *flags, const char *name)
{
    (void)index;
    (void)from;
    (void)to;
    if (!observed(name)) *flags |= LA_SYMB_NOPLTENTER | LA_SYMB_NOPLTEXIT;
    return sym->st_value;
}

Elf64_Addr la_x86_64_gnu_pltenter(Elf64_Sym *sym, unsigned int index, uintptr_t *from,
                                uintptr_t *to, La_x86_64_regs *regs, unsigned int *flags,
                                const char *name, long int *framesize)
{
    (void)index;
    (void)from;
    (void)to;
    (void)regs;
    (void)flags;
    *framesize = 0;
    report("enter", name, 0);
    return sym->st_value;
}

unsigned int la_x86_64_gnu_pltexit(Elf64_Sym *sym, unsigned int index, uintptr_t *from,
                                 uintptr_t *to, const La_x86_64_regs *regs,
                                 La_x86_64_retval *result, const char *name)
{
    (void)sym;
    (void)index;
    (void)from;
    (void)to;
    (void)regs;
    report("return", name, result->lrv_rax);
    return 0;
}
