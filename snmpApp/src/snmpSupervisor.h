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
    SnmpOperation operation;
    SnmpWireType wireType;
    uint64_t profile;
    SnmpWorkerBinding();
    ~SnmpWorkerBinding();
    void encode(snmpIpc::Writer &writer) const;
    bool decode(snmpIpc::Reader &reader);
};

bool snmpSupervisorConfigure(const char *executable, int maximum, std::string &error);
bool snmpSupervisorOverride(int milliseconds, std::string &error);
bool snmpSupervisorEnabled();
void snmpSupervisorLock();
uint64_t snmpSupervisorBind(const SnmpWorkerBinding &binding, std::vector<unsigned long> &oid,
                            std::string &error);
void snmpSupervisorAttach(uint64_t binding, devSnmp_request *request);
bool snmpSupervisorStart();
bool snmpSupervisorStop();
void snmpSupervisorReport();

#endif
