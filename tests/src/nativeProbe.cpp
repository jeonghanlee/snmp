#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <map>
#include <string>
#include <vector>

#include <epicsThread.h>
#include <epicsTime.h>
#include <iocsh.h>
#include <epicsExport.h>

#include <net-snmp/net-snmp-config.h>
#include <net-snmp/net-snmp-includes.h>

#include "snmpNative.h"

/* Drives the real module adapter against real agents from the IOC shell and
 * reports every adapter event as one SNMPNATIVE JSON line. The session
 * description is prepared here as a transport would; open, send, service,
 * close and completion ownership belong to the adapter under test. The
 * Net-SNMP library is initialized by the record transport, which the test
 * IOC starts through devSnmpSetParam before these commands run. */

namespace {

const unsigned valueCapacity = 128;
const double serviceSliceSeconds = 0.05;
const double probeLimitMs = 180000.0;
SnmpIdentity nextTransaction = 1;

double nowMs()
{
    return epicsMonotonicGet() / 1e6;
}

struct Probe {
    std::string label;
    double startedMs;
    std::map<SnmpIdentity, unsigned> completions;
    SnmpNativeSession *session;
    std::vector<std::vector<unsigned long> > oids;
    bool reissue;
    unsigned reissued;
    unsigned accepted;

    Probe() : startedMs(nowMs()), session(NULL), reissue(false), reissued(0), accepted(0) {}
};

/* Resident set size of this process in KiB, from /proc/self/status. */
long residentKib()
{
    FILE *status = fopen("/proc/self/status", "r");
    if (!status) return -1;
    char line[128];
    long value = -1;
    while (fgets(line, sizeof(line), status))
        if (sscanf(line, "VmRSS: %ld", &value) == 1) break;
    fclose(status);
    return value;
}

/* Highest descriptor of this process that refers to a socket. */
int highestSocket()
{
    DIR *directory = opendir("/proc/self/fd");
    if (!directory) return -1;
    int highest = -1;
    while (struct dirent *entry = readdir(directory)) {
        char path[300], target[64];
        snprintf(path, sizeof(path), "/proc/self/fd/%s", entry->d_name);
        ssize_t length = readlink(path, target, sizeof(target) - 1);
        if (length <= 0) continue;
        target[length] = 0;
        int fd = atoi(entry->d_name);
        if (!strncmp(target, "socket:", 7) && fd > highest) highest = fd;
    }
    closedir(directory);
    return highest;
}

const char *outcomeName(SnmpNativeResult::Outcome outcome)
{
    switch (outcome) {
    case SnmpNativeResult::Response: return "response";
    case SnmpNativeResult::Timeout: return "timeout";
    case SnmpNativeResult::SendFailed: return "send_failed";
    case SnmpNativeResult::SecurityError: return "security_error";
    case SnmpNativeResult::ProtocolError: return "protocol_error";
    case SnmpNativeResult::Closed: return "closed";
    }
    return "unknown";
}

std::string hex(const char *data, size_t length)
{
    static const char digits[] = "0123456789abcdef";
    std::string text;
    for (size_t i = 0; i < length; ++i) {
        text += digits[(unsigned char)data[i] >> 4];
        text += digits[(unsigned char)data[i] & 15];
    }
    return text;
}

std::string quoted(const std::string &value)
{
    std::string text = "\"";
    for (size_t i = 0; i < value.size(); ++i) {
        char c = value[i];
        if (c == '"' || c == '\\') text += '\\';
        if ((unsigned char)c >= 0x20) text += c;
    }
    return text + "\"";
}

void complete(void *context, SnmpIdentity transaction, const SnmpNativeResult &result)
{
    Probe *probe = static_cast<Probe *>(context);
    unsigned count = ++probe->completions[transaction];
    bool sessionOpen = probe->session && probe->session->isOpen();
    std::string values = "[";
    for (size_t i = 0; i < result.values.size(); ++i) {
        const SnmpValue &value = result.values[i];
        char item[96];
        snprintf(item, sizeof(item), "%s{\"valid\":%s,\"kind\":%d,\"wire_type\":%u,\"text\":\"", i ? "," : "",
                 value.valid ? "true" : "false", (int)value.kind, (unsigned)value.wireType);
        values += item;
        if (value.valid) values += hex(&value.text[0], strnlen(&value.text[0], value.text.size()));
        values += "\"}";
    }
    values += "]";
    printf("SNMPNATIVE {\"label\":%s,\"event\":\"completion\",\"transaction\":%llu,\"count\":%u,"
           "\"outcome\":\"%s\",\"error_status\":%ld,\"error_index\":%ld,\"resends\":%u,"
           "\"session_open\":%s,\"elapsed_ms\":%.3f,\"values\":%s}\n",
           quoted(probe->label).c_str(), (unsigned long long)transaction, count, outcomeName(result.outcome),
           result.errorStatus, result.errorIndex, result.resends, sessionOpen ? "true" : "false",
           nowMs() - probe->startedMs, values.c_str());
    fflush(stdout);
    if (probe->reissue && !probe->reissued && probe->session) {
        ++probe->reissued;
        SnmpIdentity next = nextTransaction++;
        bool sent = probe->session->get(next, probe->oids, valueCapacity);
        if (sent) ++probe->accepted;
        printf("SNMPNATIVE {\"label\":%s,\"event\":\"reissue\",\"from\":%llu,\"transaction\":%llu,\"sent\":%s,"
               "\"error\":%s}\n", quoted(probe->label).c_str(), (unsigned long long)transaction,
               (unsigned long long)next, sent ? "true" : "false", quoted(sent ? "" : probe->session->error()).c_str());
        fflush(stdout);
    }
}

bool parseOids(const char *list, std::vector<std::vector<unsigned long> > &oids)
{
    std::string text(list ? list : "");
    size_t start = 0;
    while (start <= text.size()) {
        size_t end = text.find(',', start);
        if (end == std::string::npos) end = text.size();
        std::string item = text.substr(start, end - start);
        std::vector<unsigned long> value;
        const char *cursor = item.c_str();
        while (*cursor) {
            if (*cursor == '.') ++cursor;
            char *next;
            unsigned long part = strtoul(cursor, &next, 10);
            if (next == cursor) return false;
            value.push_back(part);
            cursor = next;
        }
        if (value.empty()) return false;
        oids.push_back(value);
        start = end + 1;
    }
    return !oids.empty();
}

/* Occupies every free descriptor below floor so the session socket opened
 * next must use a descriptor at or above it. */
bool occupyBelow(int floor, std::vector<int> &fillers)
{
    while (true) {
        int fd = open("/dev/null", O_RDONLY);
        if (fd < 0) return false;
        if (fd >= floor) {
            close(fd);
            return true;
        }
        fillers.push_back(fd);
    }
}

void release(std::vector<int> &fillers)
{
    for (size_t i = 0; i < fillers.size(); ++i) close(fillers[i]);
    fillers.clear();
}

/* Keeps the strings the session description points to alive through open. */
struct Settings {
    snmp_session session;
    std::string peer, user;
};

bool configure(Settings &settings, const char *peer, const char *user, const char *authPass,
               const char *privPass, int timeoutUs, int retries)
{
    settings.peer = peer ? peer : "";
    settings.user = user ? user : "";
    snmp_sess_init(&settings.session);
    settings.session.peername = &settings.peer[0];
    settings.session.timeout = timeoutUs;
    settings.session.retries = retries;
    if (settings.user.empty() || settings.user == "-") {
        settings.session.version = SNMP_VERSION_2c;
        settings.session.community = (u_char *)"public";
        settings.session.community_len = strlen("public");
        return true;
    }
    if (!authPass || !privPass) return false;
    settings.session.version = SNMP_VERSION_3;
    settings.session.securityName = &settings.user[0];
    settings.session.securityNameLen = settings.user.size();
    settings.session.securityLevel = SNMP_SEC_LEVEL_AUTHPRIV;
    settings.session.securityAuthProto = usmHMACSHA1AuthProtocol;
    settings.session.securityAuthProtoLen = OID_LENGTH(usmHMACSHA1AuthProtocol);
    settings.session.securityPrivProto = usmAESPrivProtocol;
    settings.session.securityPrivProtoLen = OID_LENGTH(usmAESPrivProtocol);
    settings.session.securityAuthKeyLen = USM_AUTH_KU_LEN;
    settings.session.securityPrivKeyLen = USM_PRIV_KU_LEN;
    return generate_Ku(settings.session.securityAuthProto, settings.session.securityAuthProtoLen,
                       (const u_char *)authPass, strlen(authPass), settings.session.securityAuthKey,
                       &settings.session.securityAuthKeyLen) == SNMPERR_SUCCESS &&
           generate_Ku(settings.session.securityAuthProto, settings.session.securityAuthProtoLen,
                       (const u_char *)privPass, strlen(privPass), settings.session.securityPrivKey,
                       &settings.session.securityPrivKeyLen) == SNMPERR_SUCCESS;
}

void summary(Probe &probe, unsigned pending, unsigned long long adapterCompletions, const char *stop)
{
    unsigned duplicates = 0, delivered = 0;
    for (std::map<SnmpIdentity, unsigned>::const_iterator i = probe.completions.begin();
         i != probe.completions.end(); ++i) {
        delivered += i->second;
        if (i->second > 1) ++duplicates;
    }
    printf("SNMPNATIVE {\"label\":%s,\"event\":\"summary\",\"accepted\":%u,\"completed_transactions\":%u,"
           "\"delivered\":%u,\"duplicates\":%u,\"pending\":%u,\"adapter_completions\":%llu,\"stop\":\"%s\","
           "\"rss_kib\":%ld,\"elapsed_ms\":%.3f}\n",
           quoted(probe.label).c_str(), probe.accepted, (unsigned)probe.completions.size(), delivered, duplicates,
           pending, adapterCompletions, stop, residentKib(), nowMs() - probe.startedMs);
    fflush(stdout);
}

/* nativeProbe(label, peer, user, authPass, privPass, timeoutUs, retries, oids,
 * requests, closeAfterMs, descriptorFloor, oidRepeat, action): opens one
 * session, sends requests GETs at once, each carrying the comma-separated
 * OIDs repeated oidRepeat times, services until every request completed or
 * closeAfterMs elapsed, then closes. user "-" selects v2c. action "reissue"
 * makes the first completion send one more GET on the same session; action
 * "gap:<ms>" sends the requests one at a time and pauses that long after each
 * completes, keeping the session open. */
void nativeProbe(const iocshArgBuf *args)
{
    Probe probe;
    probe.label = args[0].sval ? args[0].sval : "";
    std::vector<std::vector<unsigned long> > listed, oids;
    Settings settings;
    int requests = args[8].ival, closeAfterMs = args[9].ival, floor = args[10].ival, repeat = args[11].ival;
    std::string action = args[12].sval ? args[12].sval : "none";
    int gapMs = action.compare(0, 4, "gap:") ? 0 : atoi(action.c_str() + 4);
    if (!parseOids(args[7].sval, listed) || requests < 0 || repeat < 1 ||
        (action != "none" && action != "reissue" && gapMs <= 0) ||
        !configure(settings, args[1].sval, args[2].sval, args[3].sval, args[4].sval, args[5].ival, args[6].ival)) {
        printf("SNMPNATIVE {\"label\":%s,\"event\":\"invalid_arguments\"}\n", quoted(probe.label).c_str());
        fflush(stdout);
        return;
    }
    for (int r = 0; r < repeat; ++r) oids.insert(oids.end(), listed.begin(), listed.end());
    SnmpNativeSession session(complete, &probe);
    probe.session = &session;
    probe.oids = listed;
    probe.reissue = action == "reissue";
    long rssBefore = residentKib();
    std::vector<int> fillers;
    bool occupied = floor <= 0 || occupyBelow(floor, fillers);
    bool opened = occupied && session.open(settings.session);
    printf("SNMPNATIVE {\"label\":%s,\"event\":\"open\",\"success\":%s,\"descriptor_floor\":%d,"
           "\"occupied\":%s,\"fillers\":%u,\"highest_socket\":%d,\"rss_kib\":%ld,\"error\":%s,\"elapsed_ms\":%.3f}\n",
           quoted(probe.label).c_str(), opened ? "true" : "false", floor, occupied ? "true" : "false",
           (unsigned)fillers.size(), highestSocket(), rssBefore, quoted(opened ? "" : session.error()).c_str(),
           nowMs() - probe.startedMs);
    fflush(stdout);
    release(fillers);
    std::vector<SnmpNativeSession *> single(1, &session);
    for (int i = 0; opened && i < requests; ++i) {
        if (gapMs && i) {
            while (session.pending() && nowMs() - probe.startedMs < probeLimitMs)
                if (SnmpNativeSession::service(single, serviceSliceSeconds) < 0) break;
            printf("SNMPNATIVE {\"label\":%s,\"event\":\"gap\",\"before\":%d,\"elapsed_ms\":%.3f}\n",
                   quoted(probe.label).c_str(), i, nowMs() - probe.startedMs);
            fflush(stdout);
            epicsThreadSleep(gapMs / 1000.0);
        }
        SnmpIdentity transaction = nextTransaction++;
        bool sent = session.get(transaction, oids, valueCapacity);
        if (sent) ++probe.accepted;
        printf("SNMPNATIVE {\"label\":%s,\"event\":\"send\",\"transaction\":%llu,\"sent\":%s,\"error\":%s,"
               "\"elapsed_ms\":%.3f}\n",
               quoted(probe.label).c_str(), (unsigned long long)transaction, sent ? "true" : "false",
               quoted(sent ? "" : session.error()).c_str(), nowMs() - probe.startedMs);
        fflush(stdout);
    }
    const char *stop = "drained";
    std::vector<SnmpNativeSession *> sessions(1, &session);
    while (session.pending()) {
        double elapsed = nowMs() - probe.startedMs;
        if (closeAfterMs >= 0 && elapsed >= closeAfterMs) {
            stop = "closed_with_pending";
            printf("SNMPNATIVE {\"label\":%s,\"event\":\"close_request\",\"pending\":%u,\"elapsed_ms\":%.3f}\n",
                   quoted(probe.label).c_str(), (unsigned)session.pending(), elapsed);
            fflush(stdout);
            session.close();
            break;
        }
        if (elapsed > probeLimitMs) {
            stop = "probe_limit";
            session.close();
            break;
        }
        if (SnmpNativeSession::service(sessions, serviceSliceSeconds) < 0) {
            stop = "service_error";
            session.close();
            break;
        }
    }
    session.close();
    summary(probe, (unsigned)session.pending(), session.completions(), stop);
}

/* nativeProbeMixed(label, firstPeer, firstTimeoutUs, secondPeer, secondTimeoutUs,
 * retries, oids): two v2c sessions with their own endpoints and native
 * deadlines, one GET each, serviced by one owner loop. */
void nativeProbeMixed(const iocshArgBuf *args)
{
    Probe probe;
    probe.label = args[0].sval ? args[0].sval : "";
    std::vector<std::vector<unsigned long> > oids;
    Settings first, second;
    if (!parseOids(args[6].sval, oids) ||
        !configure(first, args[1].sval, "-", NULL, NULL, args[2].ival, args[5].ival) ||
        !configure(second, args[3].sval, "-", NULL, NULL, args[4].ival, args[5].ival)) {
        printf("SNMPNATIVE {\"label\":%s,\"event\":\"invalid_arguments\"}\n", quoted(probe.label).c_str());
        fflush(stdout);
        return;
    }
    SnmpNativeSession a(complete, &probe), b(complete, &probe);
    bool opened = a.open(first.session) && b.open(second.session);
    SnmpIdentity ta = nextTransaction++, tb = nextTransaction++;
    if (opened) {
        probe.accepted += a.get(ta, oids, valueCapacity);
        probe.accepted += b.get(tb, oids, valueCapacity);
    }
    printf("SNMPNATIVE {\"label\":%s,\"event\":\"mixed_start\",\"opened\":%s,\"accepted\":%u,"
           "\"first\":%llu,\"second\":%llu}\n", quoted(probe.label).c_str(), opened ? "true" : "false",
           probe.accepted, (unsigned long long)ta, (unsigned long long)tb);
    fflush(stdout);
    std::vector<SnmpNativeSession *> sessions;
    sessions.push_back(&a);
    sessions.push_back(&b);
    const char *stop = "drained";
    while (a.pending() || b.pending()) {
        if (nowMs() - probe.startedMs > probeLimitMs) {
            stop = "probe_limit";
            break;
        }
        if (SnmpNativeSession::service(sessions, serviceSliceSeconds) < 0) {
            stop = "service_error";
            break;
        }
    }
    a.close();
    b.close();
    summary(probe, (unsigned)(a.pending() + b.pending()), a.completions() + b.completions(), stop);
}

const iocshArg labelArg = {"label", iocshArgString};
const iocshArg peerArg = {"peer", iocshArgString};
const iocshArg userArg = {"user", iocshArgString};
const iocshArg authArg = {"authPass", iocshArgString};
const iocshArg privArg = {"privPass", iocshArgString};
const iocshArg timeoutArg = {"timeoutUs", iocshArgInt};
const iocshArg retriesArg = {"retries", iocshArgInt};
const iocshArg oidsArg = {"oids", iocshArgString};
const iocshArg requestsArg = {"requests", iocshArgInt};
const iocshArg closeArg = {"closeAfterMs", iocshArgInt};
const iocshArg floorArg = {"descriptorFloor", iocshArgInt};
const iocshArg repeatArg = {"oidRepeat", iocshArgInt};
const iocshArg actionArg = {"action", iocshArgString};
const iocshArg secondPeerArg = {"secondPeer", iocshArgString};
const iocshArg secondTimeoutArg = {"secondTimeoutUs", iocshArgInt};
const iocshArg *const probeArgs[] = {&labelArg, &peerArg, &userArg, &authArg, &privArg, &timeoutArg,
                                     &retriesArg, &oidsArg, &requestsArg, &closeArg, &floorArg, &repeatArg,
                                     &actionArg};
const iocshArg *const mixedArgs[] = {&labelArg, &peerArg, &timeoutArg, &secondPeerArg, &secondTimeoutArg,
                                     &retriesArg, &oidsArg};
const iocshFuncDef probeDef = {"nativeProbe", 13, probeArgs};
const iocshFuncDef mixedDef = {"nativeProbeMixed", 7, mixedArgs};

void registerNativeProbe()
{
    iocshRegister(&probeDef, nativeProbe);
    iocshRegister(&mixedDef, nativeProbeMixed);
}

}

epicsExportRegistrar(registerNativeProbe);
