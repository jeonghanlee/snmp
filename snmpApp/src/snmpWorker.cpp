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
#include <algorithm>
#include <set>
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
    std::shared_ptr<SnmpNativeSession> session;
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
    Worker() : channel(ipcDescriptor), epoch(0), active(0), lastTransaction(0), trace(false),
               closePending(false), shuttingDown(false) {}
    ~Worker()
    {
        shuttingDown = true;
        for (std::map<uint64_t, std::unique_ptr<Binding> >::iterator i = bindings.begin(); i != bindings.end(); ++i)
            i->second->session->close();
    }
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
                sessions.push_back(activeSession.get());
                if (SnmpNativeSession::service(sessions, 0.05, ipcDescriptor) < 0) return 2;
            } else {
                if (closePending) { activeSession->close(); closePending = false; }
                struct pollfd p = {ipcDescriptor, static_cast<short>(POLLIN | (channel.writing() ? POLLOUT : 0)), 0};
                if (poll(&p, 1, 50) < 0 && errno != EINTR) return 2;
            }
        }
    }
private:
    Channel channel;
    uint64_t epoch, active, lastTransaction;
    bool trace, closePending, shuttingDown;
    std::shared_ptr<SnmpNativeSession> activeSession;
    struct Member { uint64_t binding, deadline; size_t index; bool expired; };
    std::vector<Member> members;
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
        if (self->shuttingDown) return;
        if (transaction != self->active) _exit(3);
        Writer w; w.u32(self->members.size());
        for (size_t i = 0; i < self->members.size(); ++i) {
            const Member &member = self->members[i];
            Binding &b = *self->bindings.at(member.binding);
            SnmpValue value(std::max(1024u, b.config.capacity));
            const std::vector<SnmpValue> &values = b.config.legacy ? r.legacyValues : r.values;
            if (!member.expired && member.index < values.size()) {
                const SnmpValue &source = values[member.index];
                if (source.length <= value.bytes.size() && strlen(source.text.data()) < value.text.size())
                    value = source;
            }
            w.u64(member.binding); w.u32(member.expired ? SnmpNativeResult::Timeout : r.outcome);
            /* A legacy error-index applies only to that OID. Other members
             * retain the traditional missing-value immediate-poll behavior. */
            long error = r.errorStatus;
            if (b.config.legacy && r.errorIndex > 0 && static_cast<size_t>(r.errorIndex) != member.index + 1)
                error = 0;
            unsigned match = b.config.legacy && !member.expired && member.index < r.legacyMatches.size()
                           ? r.legacyMatches[member.index] : SnmpLegacyMissing;
            w.u64(error); w.u64(r.errorIndex); w.u32(r.resends); w.u32(match); w.value(value);
        }
        if (!self->reply(Result, transaction, w)) _exit(3);
        self->closePending = r.outcome != SnmpNativeResult::Response;
        self->active = 0;
        self->members.clear();
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
                for (std::map<uint64_t, std::unique_ptr<Binding> >::iterator i = bindings.begin(); i != bindings.end(); ++i)
                    if (b->config.sameSession(i->second->config)) { b->session = i->second->session; break; }
                if (!b->session) b->session.reset(new SnmpNativeSession(completed, this));
                bindings[f.transaction] = std::move(b);
            }
            return reply(Bound, f.transaction, w);
        }
        if (f.kind != Transaction || !f.transaction || f.transaction <= lastTransaction) return false;
        if (closePending) { activeSession->close(); closePending = false; }
        unsigned total = r.u32();
        if (!total || total > 256) return false;
        std::vector<std::vector<unsigned long> > oids;
        std::set<uint64_t> identities;
        Binding *first = NULL;
        SnmpValue payload(65536);
        std::string legacyText;
        unsigned operation = SnmpGet, capacity = 1024;
        char legacyType = 0;
        members.clear();
        for (unsigned n = 0; n < total; ++n) {
            std::vector<unsigned char> encoded = r.blob(maxFrameBytes - headerBytes);
            Reader command(encoded);
            uint64_t id = command.u64(), profile = command.u64(), originalDeadline = command.u64();
            std::map<uint64_t, std::unique_ptr<Binding> >::iterator found = bindings.find(id);
            if (found == bindings.end() || !identities.insert(id).second) return false;
            Binding &b = *found->second;
            unsigned op = command.u32(), count = command.u32();
            if (profile != b.config.profile || !originalDeadline || op > SnmpSet ||
                (!b.config.legacy && op != b.config.operation) || count != b.numericOid.size() ||
                (op == SnmpSet && total != 1)) return false;
            for (unsigned i = 0; i < count; ++i) if (command.u32() != b.numericOid[i]) return false;
            if (first && (op != operation || !b.config.sameSession(first->config))) return false;
            if (!first) { first = &b; operation = op; }
            if (op == SnmpSet) {
                if (b.config.legacy) {
                    unsigned type = command.u32();
                    if (!type || type > 127) return false;
                    legacyType = type; legacyText = command.string(65535);
                } else if (!command.value(payload, true)) return false;
            }
            if (!command.done()) return false;
            bool expired = originalDeadline <= now();
            size_t index = 0;
            if (!expired) {
                for (; index < oids.size(); ++index) if (oids[index] == b.numericOid) break;
                if (index == oids.size()) oids.push_back(b.numericOid);
            }
            members.push_back(Member{id, originalDeadline, index, expired});
            capacity = std::max(capacity, b.config.capacity);
        }
        if (!r.done()) return false;
        for (size_t i = 0; i < members.size(); ++i)
            if (oids.size() > bindings.at(members[i].binding)->config.maxOids) return false;
        /* Validate the maximum encoded result before opening any native
         * transport. Requests at different capacities share only bounded data. */
        if (headerBytes + 4 + total * (2 * static_cast<size_t>(capacity) + 640) > maxFrameBytes) return false;
        active = lastTransaction = f.transaction;
        activeSession = first->session;
        long wireId = 0;
        bool opened = !oids.empty() && (activeSession->isOpen() || activeSession->open(first->settings));
        oids.clear();
        for (size_t i = 0; i < members.size(); ++i) {
            Member &member = members[i];
            member.expired = member.deadline <= now();
            if (member.expired) continue;
            const std::vector<unsigned long> &oid = bindings.at(member.binding)->numericOid;
            size_t index = 0;
            for (; index < oids.size(); ++index) if (oids[index] == oid) break;
            if (index == oids.size()) oids.push_back(oid);
            member.index = index;
        }
        if (legacyType)
            netsnmp_ds_set_boolean(NETSNMP_DS_LIBRARY_ID, NETSNMP_DS_LIB_DONT_CHECK_RANGE, !first->config.checkRanges);
        if (!opened || oids.empty() || !activeSession->transact(active, oids, capacity, first->config.wireType,
                                     operation == SnmpSet && !first->config.legacy ? &payload : NULL, &wireId,
                                     legacyType, legacyType ? legacyText.c_str() : NULL, true)) {
            SnmpNativeResult failed;
            failed.outcome = SnmpNativeResult::SendFailed;
            failed.errorStatus = failed.errorIndex = 0; failed.resends = 0;
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
