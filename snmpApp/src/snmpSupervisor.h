#ifndef SNMP_SUPERVISOR_H
#define SNMP_SUPERVISOR_H

#include "snmpIpc.h"
#include <string>
#include <vector>

class devSnmp_request;

/* Startup snapshot; only explicit values cross the private socket. Native
 * protocol OIDs, keys, handles and record pointers stay on their own side. */
struct SnmpWorkerBinding {
    std::string address, community, securityName, contextName, authType, privType;
    std::string authPassphrase, privPassphrase, oidName;
    std::vector<unsigned char> securityEngineID, contextEngineID;
    int version, securityLevel, retries;
    long timeoutUs;
    unsigned capacity;
    unsigned maxOids;
    bool legacy, checkRanges;
    SnmpOperation operation;
    SnmpWireType wireType;
    uint64_t profile;
    SnmpWorkerBinding();
    ~SnmpWorkerBinding();
    void encode(snmpIpc::Writer &writer) const;
    bool decode(snmpIpc::Reader &reader);
    bool sameSession(const SnmpWorkerBinding &other) const;
};

struct SnmpLegacyTarget {
    void *context;
    void (*notify)(void *, bool write, bool terminal, const SnmpValue *, unsigned outcome, long error,
                   SnmpLegacyMatch match);
};

bool snmpSupervisorConfigure(const char *executable, int maximum, std::string &error);
bool snmpSupervisorOverride(int milliseconds, std::string &error);
bool snmpSupervisorSetQueueSize(const char *address, int pending, std::string &error);
bool snmpSupervisorEnabled();
void snmpSupervisorLock();
uint64_t snmpSupervisorBind(const SnmpWorkerBinding &binding, std::vector<unsigned long> &oid,
                            std::string &error);
void snmpSupervisorAttach(uint64_t binding, devSnmp_request *request);
void *snmpSupervisorAttachLegacy(uint64_t binding, const SnmpLegacyTarget &target);
bool snmpSupervisorLegacy(void *binding, char type = 0, const char *text = NULL);
bool snmpSupervisorStart();
bool snmpSupervisorStop();
void snmpSupervisorReport();

#endif
