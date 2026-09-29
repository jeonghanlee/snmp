#include "snmpSupervisor.h"
#include "snmpNative.h"
#include "snmpWorkerBuild.h"
#include <net-snmp/net-snmp-config.h>
#include <net-snmp/net-snmp-includes.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <map>
#include <memory>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <unistd.h>

namespace {
using namespace snmpIpc;
const int ipcDescriptor = 3;

struct Binding {
    SnmpWorkerBinding config;
    netsnmp_session settings;
    std::vector<unsigned long> auth, priv, numericOid;
    std::unique_ptr<SnmpNativeSession> session;
    ~Binding()
    {
        explicit_bzero(settings.securityAuthKey, sizeof(settings.securityAuthKey));
        explicit_bzero(settings.securityPrivKey, sizeof(settings.securityPrivKey));
    }
    bool prepare()
    {
        snmp_sess_init(&settings);
        settings.version = config.version == 3 ? SNMP_VERSION_3 :
                           config.version == 2 ? SNMP_VERSION_2c : SNMP_VERSION_1;
        settings.peername = const_cast<char *>(config.address.c_str());
        settings.community = (u_char *)config.community.data();
        settings.community_len = config.community.size();
        settings.timeout = config.timeoutUs;
        settings.retries = config.retries;
        if (config.version == 3) {
            settings.securityLevel = config.securityLevel;
            settings.securityName = const_cast<char *>(config.securityName.c_str());
            settings.securityNameLen = config.securityName.size();
            settings.contextName = const_cast<char *>(config.contextName.c_str());
            settings.contextNameLen = config.contextName.size();
            if (config.securityLevel >= 2) {
                if (!snmpNativeAuthProtocol(config.authType.c_str(), auth)) return false;
                settings.securityAuthProto = &auth[0]; settings.securityAuthProtoLen = auth.size();
                settings.securityAuthKeyLen = sizeof(settings.securityAuthKey);
                if (!snmpNativeDeriveKey(&auth[0], auth.size(), config.authPassphrase,
                                         settings.securityAuthKey, &settings.securityAuthKeyLen)) return false;
            }
            if (config.securityLevel == 3) {
                if (!snmpNativePrivProtocol(config.privType.c_str(), priv)) return false;
                settings.securityPrivProto = &priv[0]; settings.securityPrivProtoLen = priv.size();
                settings.securityPrivKeyLen = sizeof(settings.securityPrivKey);
                if (!snmpNativeDeriveKey(&auth[0], auth.size(), config.privPassphrase,
                                         settings.securityPrivKey, &settings.securityPrivKeyLen)) return false;
            }
            if (!config.securityEngineID.empty()) {
                settings.securityEngineID = &config.securityEngineID[0];
                settings.securityEngineIDLen = config.securityEngineID.size();
            }
            if (!config.contextEngineID.empty()) {
                settings.contextEngineID = &config.contextEngineID[0];
                settings.contextEngineIDLen = config.contextEngineID.size();
            }
        }
        oid resolved[MAX_OID_LEN]; size_t length = MAX_OID_LEN;
        if (!read_objid(config.oidName.c_str(), resolved, &length)) return false;
        numericOid.assign(resolved, resolved + length);
        return config.operation != SnmpSet || snmpNativeWireAsnType(config.wireType);
    }
};

class Worker {
public:
    Worker() : channel(ipcDescriptor), epoch(0), active(0), activeBinding(0), lastTransaction(0), trace(false) {}
    int run()
    {
        for (;;) {
            if (!channel.flush()) return 2;
            Frame f;
            int received = channel.receive(f);
            if (received < 0) return 2;
            if (received > 0) {
                if (!process(f)) return 2;
                clear(f.payload);
            }
            if (active) {
                std::vector<SnmpNativeSession *> sessions;
                sessions.push_back(bindings.at(activeBinding)->session.get());
                if (SnmpNativeSession::service(sessions, 0.05, ipcDescriptor) < 0) return 2;
            } else {
                struct pollfd p = {ipcDescriptor, static_cast<short>(POLLIN | (channel.writing() ? POLLOUT : 0)), 0};
                if (poll(&p, 1, 50) < 0 && errno != EINTR) return 2;
            }
        }
    }
private:
    Channel channel;
    uint64_t epoch, active, activeBinding, lastTransaction;
    bool trace;
    std::string address;
    std::map<uint64_t, std::unique_ptr<Binding> > bindings;
    bool reply(Kind kind, uint64_t identity, const Writer &w)
    {
        Frame f = {kind, epoch, identity, w.bytes};
        return channel.queue(f);
    }
    static void completed(void *context, SnmpIdentity transaction, const SnmpNativeResult &r)
    {
        Worker *self = static_cast<Worker *>(context);
        if (transaction != self->active || r.values.size() != 1) _exit(3);
        Writer w;
        w.u64(self->activeBinding); w.u32(r.outcome); w.u64(r.errorStatus); w.u64(r.errorIndex);
        w.u32(r.resends); w.value(r.values[0]);
        if (!self->reply(Result, transaction, w)) _exit(3);
        self->active = self->activeBinding = 0;
    }
    bool process(const Frame &f)
    {
        Reader r(f.payload);
        if (!epoch) {
            if (f.kind != Bootstrap || f.transaction || r.string(128) != SNMP_WORKER_BUILD) return false;
            address = r.string(255);
            unsigned traceFlag = r.u32();
            if (!r.done() || address.empty() || traceFlag > 1) return false;
            trace = traceFlag;
            epoch = f.epoch;
            Writer w; w.string(SNMP_WORKER_BUILD);
            return reply(Ready, 0, w);
        }
        if (f.epoch != epoch) return false;
        if (f.kind == Stop) {
            if (!r.done() || f.transaction) return false;
            _exit(0);
        }
        if (active || channel.writing()) return false;
        if (f.kind == Bind) {
            if (!f.transaction || bindings.count(f.transaction)) return false;
            std::unique_ptr<Binding> b(new Binding);
            bool ok = b->config.decode(r) && r.done() && b->config.address == address;
            uint64_t required = 0;
            ok = ok && snmpNativeResolveBudget(b->config.timeoutUs, b->config.retries) &&
                 watchdog(b->config.timeoutUs, b->config.retries, required) && b->prepare();
            Writer w; w.u32(ok);
            if (ok) {
                w.u64(b->config.timeoutUs); w.u32(b->config.retries);
                w.u64(required); w.u32(b->numericOid.size());
                for (size_t i = 0; i < b->numericOid.size(); ++i) w.u32(b->numericOid[i]);
                b->session.reset(new SnmpNativeSession(completed, this));
                bindings[f.transaction] = std::move(b);
            }
            return reply(Bound, f.transaction, w);
        }
        if (f.kind != Transaction || !f.transaction || f.transaction <= lastTransaction) return false;
        uint64_t id = r.u64(), profile = r.u64(), originalDeadline = r.u64();
        std::map<uint64_t, std::unique_ptr<Binding> >::iterator found = bindings.find(id);
        if (found == bindings.end()) return false;
        Binding &b = *found->second;
        unsigned op = r.u32(), count = r.u32();
        if (profile != b.config.profile || !originalDeadline || op != b.config.operation ||
            count != b.numericOid.size()) return false;
        for (unsigned i = 0; i < count; ++i) if (r.u32() != b.numericOid[i]) return false;
        SnmpValue payload(b.config.capacity);
        if (op == SnmpSet && !r.value(payload, true)) return false;
        if (!r.done()) return false;
        active = lastTransaction = f.transaction; activeBinding = id;
        std::vector<std::vector<unsigned long> > oids(1, b.numericOid);
        long wireId = 0;
        if (originalDeadline <= now() ||
            (!b.session->isOpen() && !b.session->open(b.settings)) ||
            !b.session->transact(active, oids, std::max(1024u, b.config.capacity), b.config.wireType,
                                 op == SnmpSet ? &payload : NULL, &wireId)) {
            SnmpNativeResult failed;
            failed.outcome = SnmpNativeResult::SendFailed;
            failed.errorStatus = failed.errorIndex = 0; failed.resends = 0;
            failed.values.assign(1, SnmpValue(std::max(1024u, b.config.capacity)));
            completed(this, active, failed);
        }
        if (trace) fprintf(stderr, "SNMPWIRE %llu epoch=%llu tx=%llu wire=%ld\n",
                           (unsigned long long)now(), (unsigned long long)epoch,
                           (unsigned long long)f.transaction, wireId);
        return true;
    }
};

bool initialize(long parent)
{
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent) return false;
    if (prctl(PR_SET_DUMPABLE, 0)) return false;
    struct rlimit core = {0, 0};
    if (setrlimit(RLIMIT_CORE, &core)) return false;
    DIR *directory = opendir("/proc/self/fd");
    if (!directory) return false;
    for (struct dirent *entry; (entry = readdir(directory));) {
        char *end; long fd = strtol(entry->d_name, &end, 10);
        if (!*end && fd > ipcDescriptor && fd != dirfd(directory)) close(fd);
    }
    closedir(directory);
    if (fcntl(ipcDescriptor, F_SETFD, FD_CLOEXEC) || fcntl(ipcDescriptor, F_SETFL, O_NONBLOCK)) return false;
    netsnmp_ds_set_boolean(NETSNMP_DS_LIBRARY_ID, NETSNMP_DS_LIB_DONT_READ_CONFIGS, 1);
    netsnmp_ds_set_boolean(NETSNMP_DS_LIBRARY_ID, NETSNMP_DS_LIB_DONT_PERSIST_STATE, 1);
    netsnmp_ds_set_boolean(NETSNMP_DS_LIBRARY_ID, NETSNMP_DS_LIB_DISABLE_PERSISTENT_LOAD, 1);
    netsnmp_ds_set_boolean(NETSNMP_DS_LIBRARY_ID, NETSNMP_DS_LIB_DISABLE_PERSISTENT_SAVE, 1);
    init_snmp("snmpWorker");
    return true;
}
}

int main(int argc, char **argv)
{
    if (argc != 3 || strcmp(argv[1], "--parent")) return 2;
    char *end; errno = 0; long parent = strtol(argv[2], &end, 10);
    if (errno || *end || parent <= 1 || !initialize(parent)) return 2;
    try { Worker worker; return worker.run(); }
    catch (...) { return 3; }
}
