#include "snmpSupervisor.h"
#include "snmpRequest.h"
#include "snmpWorkerBuild.h"
#include <algorithm>
#include <atomic>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <map>
#include <memory>
#include <mutex>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>

extern char **environ;
namespace {
using namespace snmpIpc;
const unsigned defaultMaximum = 32;
const uint64_t secondNS = 1000000000;

struct Entry {
    uint64_t id;
    SnmpWorkerBinding config;
    std::vector<unsigned long> oid;
    devSnmp_request *request;
};
struct Child {
    enum State { Dead, BootstrapWait, BindWait, Idle, Busy } state;
    std::string address;
    Channel channel;
    pid_t pid;
    uint64_t epoch, limitMSec, due, retryAt, transaction;
    unsigned backoff;
    size_t setupIndex;
    Entry *active;
    std::vector<std::unique_ptr<Entry> > entries;
    Child(const std::string &a) : state(Dead), address(a), pid(0), epoch(0), limitMSec(0), due(0),
        retryAt(0), transaction(0), backoff(1), setupIndex(0), active(NULL) {}
};
struct Supervisor {
    std::string executable;
    unsigned maximum;
    uint64_t overrideMSec, nextEpoch, nextBinding, nextTransaction;
    bool locked;
    std::atomic<bool> stopping;
    std::mutex mutex;
    std::thread thread;
    std::vector<std::unique_ptr<Child> > children;
    Supervisor() : maximum(defaultMaximum), overrideMSec(0), nextEpoch(0), nextBinding(0),
                   nextTransaction(0), locked(false), stopping(false) {}
};
/* Exit may retain callback storage deliberately; process-lifetime state must
 * not run static destructors against that storage after EPICS teardown. */
Supervisor &owner() { static Supervisor *s = new Supervisor; return *s; }

void failActive(Child &c, bool timeout)
{
    if (c.active && c.active->request) {
        SnmpValue failure(c.active->config.capacity);
        c.active->request->finish(c.transaction, failure, timeout);
    }
    c.active = NULL; c.transaction = 0;
}
void retire(Child &c, const char *reason, bool timeout = false)
{
    fprintf(stderr, "devSnmp worker epoch=%llu retired: %s\n", (unsigned long long)c.epoch, reason);
    if (c.channel.fd >= 0) close(c.channel.fd);
    c.channel.reset(-1);
    if (c.pid > 0) kill(c.pid, SIGKILL);
    failActive(c, timeout);
    c.state = Child::Dead;
    c.retryAt = now() + c.backoff * secondNS;
    c.backoff = std::min(30u, c.backoff * 2);
}
bool reap(Child &c)
{
    if (c.pid <= 0) return true;
    int status;
    pid_t result = waitpid(c.pid, &status, WNOHANG);
    if (result == c.pid || (result < 0 && errno == ECHILD)) { c.pid = 0; return true; }
    return false;
}
bool spawn(Child &c)
{
    Supervisor &s = owner();
    if (!reap(c) || s.nextEpoch == UINT64_MAX) return false;
    int sockets[2];
    if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0, sockets)) return false;
    int source = fcntl(sockets[1], F_DUPFD_CLOEXEC, 4);
    close(sockets[1]);
    if (source < 0) { close(sockets[0]); return false; }
    posix_spawn_file_actions_t actions;
    int status = posix_spawn_file_actions_init(&actions);
    if (status) { close(source); close(sockets[0]); return false; }
    status = posix_spawn_file_actions_adddup2(&actions, source, 3);
    if (!status) status = posix_spawn_file_actions_addclose(&actions, source);
    if (!status && sockets[0] != 3) status = posix_spawn_file_actions_addclose(&actions, sockets[0]);
    char parent[32]; snprintf(parent, sizeof(parent), "%ld", (long)getpid());
    char *argv[] = {const_cast<char *>(s.executable.c_str()), const_cast<char *>("--parent"), parent, NULL};
    if (!status) status = posix_spawn(&c.pid, s.executable.c_str(), &actions, NULL, argv, environ);
    posix_spawn_file_actions_destroy(&actions);
    close(source);
    if (status) { close(sockets[0]); c.pid = 0; return false; }
    c.channel.reset(sockets[0]); c.epoch = ++s.nextEpoch; c.setupIndex = 0;
    Writer w; w.string(SNMP_WORKER_BUILD); w.string(c.address); w.u32(snmpRequestTrace != 0);
    Frame f = {Bootstrap, c.epoch, 0, w.bytes};
    c.channel.queue(f); c.state = Child::BootstrapWait;
    return deadline(startupMSec, c.due);
}
bool bindNext(Child &c)
{
    if (c.setupIndex == c.entries.size()) { c.state = Child::Idle; return true; }
    Entry &e = *c.entries[c.setupIndex];
    Writer w; e.config.encode(w);
    Frame f = {Bind, c.epoch, e.id, w.bytes};
    bool ok = c.channel.queue(f);
    clear(w.bytes); clear(f.payload);
    c.state = Child::BindWait;
    return ok && deadline(startupMSec, c.due);
}
bool receive(Child &c, const Frame &f)
{
    if (f.epoch != c.epoch) return false;
    Reader r(f.payload);
    if (c.state == Child::BootstrapWait) {
        if (f.kind != Ready || f.transaction || r.string(128) != SNMP_WORKER_BUILD || !r.done()) return false;
        return bindNext(c);
    }
    if (c.state == Child::BindWait) {
        Entry &e = *c.entries[c.setupIndex];
        if (f.kind != Bound || f.transaction != e.id || r.u32() != 1) return false;
        uint64_t timeout = r.u64(); unsigned retries = r.u32();
        uint64_t required = r.u64(); unsigned count = r.u32();
        uint64_t expected;
        if (timeout > LONG_MAX || retries >= INT_MAX ||
            (e.config.timeoutUs != -1 && timeout != static_cast<uint64_t>(e.config.timeoutUs)) ||
            (e.config.retries != -1 && retries != static_cast<unsigned>(e.config.retries)) ||
            !watchdog(static_cast<long>(timeout), static_cast<int>(retries), expected) || expected != required ||
            !count || count > 128) return false;
        Supervisor &s = owner();
        uint64_t due;
        if ((s.overrideMSec && s.overrideMSec < required) ||
            !deadline(s.overrideMSec ? s.overrideMSec : required, due)) return false;
        c.limitMSec = s.overrideMSec ? s.overrideMSec : std::max(c.limitMSec, required);
        std::vector<unsigned long> oid;
        for (unsigned i = 0; i < count; ++i) oid.push_back(r.u32());
        if (!r.done() || (!e.oid.empty() && oid != e.oid)) return false;
        e.oid.swap(oid);
        ++c.setupIndex;
        return bindNext(c);
    }
    if (c.state != Child::Busy || f.kind != Result || f.transaction != c.transaction || !c.active) return false;
    Entry &e = *c.active;
    uint64_t binding = r.u64(); unsigned outcome = r.u32();
    uint64_t errorStatus = r.u64(), errorIndex = r.u64();
    r.u32();
    SnmpValue value(std::max(1024u, e.config.capacity));
    if (binding != e.id || outcome > 5 || !r.value(value) || !r.done() || errorStatus > INT_MAX ||
        errorIndex > INT_MAX) return false;
    if (outcome != 0 || errorStatus) value.valid = false;
    if (e.config.operation == SnmpSet) {
        unsigned expected = e.config.wireType == SnmpWireInteger ? 2 :
                            e.config.wireType == SnmpWireFloat ? 0x78 : 4;
        if (value.wireType != expected) value.valid = false;
    }
    e.request->finish(c.transaction, value, outcome == 1);
    c.active = NULL; c.transaction = 0; c.state = Child::Idle;
    c.backoff = 1;
    return true;
}
void dispatch(Child &c)
{
    Supervisor &s = owner();
    Entry *next = NULL;
    for (size_t i = 0; i < c.entries.size(); ++i) {
        Entry *e = c.entries[i].get();
        if (e->request && e->request->pending() &&
            (!next || e->request->acceptedAt() < next->request->acceptedAt())) next = e;
    }
    if (!next || s.nextTransaction == UINT64_MAX) return;
    SnmpValue payload(next->config.capacity);
    uint64_t originalDeadline;
    uint64_t transaction = ++s.nextTransaction;
    if (!next->request->claimWorker(transaction, payload, originalDeadline)) return;
    c.active = next; c.transaction = transaction;
    if (!deadline(c.limitMSec, c.due)) { failActive(c, false); return; }
    Writer w;
    w.u64(next->id); w.u64(next->config.profile); w.u64(originalDeadline);
    w.u32(next->config.operation); w.u32(next->oid.size());
    for (size_t i = 0; i < next->oid.size(); ++i) w.u32(next->oid[i]);
    if (next->config.operation == SnmpSet) w.value(payload);
    Frame f = {Transaction, c.epoch, transaction, w.bytes};
    if (!c.channel.queue(f)) { retire(c, "output ownership"); return; }
    c.state = Child::Busy;
    /* From this point even a failed first write leaves a SET outcome unknown.
     * There is no transaction requeue on retirement or restart. */
    next->request->dispatched(transaction, 0);
}
void service(Child &c, bool dispatchAllowed)
{
    uint64_t current = now();
    if (c.state == Child::Dead) {
        if (dispatchAllowed && current >= c.retryAt && reap(c) && !spawn(c)) retire(c, "spawn failed");
        return;
    }
    if ((c.state == Child::Busy || c.state == Child::BootstrapWait || c.state == Child::BindWait) && current >= c.due) {
        retire(c, "absolute deadline", c.state == Child::Busy); return;
    }
    if (!c.channel.flush()) { retire(c, "write failed"); return; }
    Frame f;
    int result = c.channel.receive(f);
    if (result < 0 || (result > 0 && !receive(c, f))) { retire(c, "invalid frame or EOF"); return; }
    if (dispatchAllowed && c.state == Child::Idle) dispatch(c);
}
void run()
{
    Supervisor &s = owner();
    while (!s.stopping) {
        std::vector<struct pollfd> descriptors;
        {
            std::lock_guard<std::mutex> guard(s.mutex);
            for (size_t i = 0; i < s.children.size(); ++i) {
                Child &c = *s.children[i];
                try { service(c, true); }
                catch (...) { retire(c, "local resource failure"); }
                if (c.channel.fd >= 0) {
                    struct pollfd p = {c.channel.fd, static_cast<short>(POLLIN | (c.channel.writing() ? POLLOUT : 0)), 0};
                    descriptors.push_back(p);
                }
            }
        }
        poll(descriptors.empty() ? NULL : &descriptors[0], descriptors.size(), 2);
    }
}
}

bool snmpSupervisorEnabled() { return !owner().executable.empty(); }
void snmpSupervisorLock() { owner().locked = true; }
bool snmpSupervisorConfigure(const char *path, int maximum, std::string &error)
{
    Supervisor &s = owner();
    if (s.locked || !s.executable.empty() || !path || path[0] != '/' || maximum <= 0) {
        error = "worker setup requires one absolute helper path and positive limit before initialization";
        return false;
    }
    s.executable = path; s.maximum = maximum;
    return true;
}
bool snmpSupervisorOverride(int milliseconds, std::string &error)
{
    Supervisor &s = owner();
    uint64_t due;
    if (s.locked || milliseconds <= 0 || !deadline(milliseconds, due)) {
        error = "worker progress override must be positive and precede profile or record initialization";
        return false;
    }
    s.overrideMSec = milliseconds;
    return true;
}
uint64_t snmpSupervisorBind(const SnmpWorkerBinding &binding, std::vector<unsigned long> &oid, std::string &error)
{
    Supervisor &s = owner();
    s.locked = true;
    if (!snmpSupervisorEnabled() || s.thread.joinable() || s.stopping) {
        error = "worker binding is unavailable"; return 0;
    }
    uint64_t required = 0, due;
    bool inherited = binding.timeoutUs == -1 || binding.retries == -1;
    if ((!inherited && !watchdog(binding.timeoutUs, binding.retries, required)) ||
        binding.timeoutUs < -1 || binding.timeoutUs == 0 || binding.retries < -1 || binding.retries >= INT_MAX ||
        (s.overrideMSec && s.overrideMSec < required) ||
        ((!inherited || s.overrideMSec) && !deadline(s.overrideMSec ? s.overrideMSec : required, due))) {
        error = "worker progress budget is invalid or explicit override is undersized"; return 0;
    }
    Child *child = NULL;
    for (size_t i = 0; i < s.children.size(); ++i)
        if (s.children[i]->address == binding.address) child = s.children[i].get();
    if (!child) {
        if (s.children.size() >= s.maximum) { error = "worker process limit reached"; return 0; }
        s.children.push_back(std::unique_ptr<Child>(new Child(binding.address)));
        child = s.children.back().get();
    }
    Child &c = *child;
    if (s.nextBinding == UINT64_MAX) { error = "worker binding identity exhausted"; return 0; }
    c.limitMSec = s.overrideMSec ? s.overrideMSec : std::max(c.limitMSec, required);
    std::unique_ptr<Entry> e(new Entry);
    e->id = ++s.nextBinding; e->config = binding; e->request = NULL;
    uint64_t identity = e->id;
    c.entries.push_back(std::move(e));
    bool ok = c.state == Child::Idle ? bindNext(c) : c.state == Child::Dead && spawn(c);
    uint64_t setupDeadline;
    deadline(startupMSec, setupDeadline);
    while (ok && c.state != Child::Idle && c.state != Child::Dead && now() < setupDeadline) {
        service(c, false);
        struct pollfd p = {c.channel.fd, static_cast<short>(POLLIN | (c.channel.writing() ? POLLOUT : 0)), 0};
        poll(&p, 1, 2);
    }
    if (!ok || c.state != Child::Idle) {
        retire(c, "binding failed");
        c.entries.pop_back();
        error = "worker local binding failed (helper, identity, OID or security configuration)";
        return 0;
    }
    oid = c.entries.back()->oid;
    printf("devSnmp worker bound id=%llu pid=%ld epoch=%llu progressMSec=%llu\n",
           (unsigned long long)identity, (long)c.pid, (unsigned long long)c.epoch, (unsigned long long)c.limitMSec);
    fflush(stdout);
    return identity;
}
void snmpSupervisorAttach(uint64_t binding, devSnmp_request *request)
{
    Supervisor &s = owner();
    for (size_t i = 0; i < s.children.size(); ++i)
        for (size_t j = 0; j < s.children[i]->entries.size(); ++j)
            if (s.children[i]->entries[j]->id == binding) s.children[i]->entries[j]->request = request;
}
bool snmpSupervisorStart()
{
    Supervisor &s = owner();
    if (s.stopping || s.thread.joinable()) return false;
    s.locked = true;
    try { s.thread = std::thread(run); return true; }
    catch (...) { return false; }
}
bool snmpSupervisorStop()
{
    Supervisor &s = owner();
    s.stopping = true;
    if (s.thread.joinable()) s.thread.join();
    for (size_t i = 0; i < s.children.size(); ++i) {
        Child &c = *s.children[i];
        if (c.channel.fd >= 0 && !c.channel.writing()) {
            Frame f = {Stop, c.epoch, 0, {}};
            c.channel.queue(f);
        }
    }
    const unsigned limits[] = {2000, 500, 500};
    const int signals[] = {0, SIGTERM, SIGKILL};
    for (unsigned stage = 0; stage < 3; ++stage) {
        if (signals[stage]) for (size_t i = 0; i < s.children.size(); ++i)
            if (s.children[i]->pid > 0) kill(s.children[i]->pid, signals[stage]);
        uint64_t due; deadline(limits[stage], due);
        while (now() < due) {
            bool all = true;
            for (size_t i = 0; i < s.children.size(); ++i) {
                Child &c = *s.children[i];
                if (c.channel.fd >= 0) c.channel.flush();
                if (!reap(c)) all = false;
            }
            if (all) break;
            poll(NULL, 0, 2);
        }
    }
    bool ok = true;
    for (size_t i = 0; i < s.children.size(); ++i) {
        Child &c = *s.children[i];
        if (c.channel.fd >= 0) close(c.channel.fd);
        c.channel.reset(-1);
        if (!reap(c)) ok = false;
    }
    return ok;
}
void snmpSupervisorReport()
{
    Supervisor &s = owner();
    std::lock_guard<std::mutex> guard(s.mutex);
    for (size_t i = 0; i < s.children.size(); ++i) {
        Child &c = *s.children[i];
        printf("worker pid=%ld epoch=%llu state=%u bindings=%zu progressMSec=%llu\n",
               (long)c.pid, (unsigned long long)c.epoch, c.state, c.entries.size(), (unsigned long long)c.limitMSec);
    }
}
