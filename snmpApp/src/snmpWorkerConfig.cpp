#include "snmpSupervisor.h"
#include <limits.h>

namespace {
void erase(std::string &s)
{
    volatile char *p = s.empty() ? NULL : &s[0];
    for (size_t i = 0; i < s.size(); ++i) p[i] = 0;
}
}
SnmpWorkerBinding::SnmpWorkerBinding()
    : version(2), securityLevel(1), retries(5), timeoutUs(10000000), capacity(1024), maxOids(20),
      legacy(false), checkRanges(true),
      operation(SnmpGet), wireType(SnmpWireNone), profile(0) {}
SnmpWorkerBinding::~SnmpWorkerBinding() { erase(authPassphrase); erase(privPassphrase); erase(community); }
void SnmpWorkerBinding::encode(snmpIpc::Writer &w) const
{
    w.string(address); w.string(community); w.string(securityName); w.string(contextName);
    w.string(authType); w.string(privType); w.string(authPassphrase); w.string(privPassphrase);
    w.string(oidName);
    w.blob(securityEngineID.empty() ? NULL : &securityEngineID[0], securityEngineID.size());
    w.blob(contextEngineID.empty() ? NULL : &contextEngineID[0], contextEngineID.size());
    w.u32(version); w.u32(securityLevel); w.u32(retries); w.u64(timeoutUs);
    w.u32(capacity); w.u32(operation); w.u32(wireType); w.u64(profile);
    w.u32(maxOids); w.u32(legacy); w.u32(checkRanges);
}
bool SnmpWorkerBinding::decode(snmpIpc::Reader &r)
{
    address = r.string(255); community = r.string(1024); securityName = r.string(32);
    contextName = r.string(32); authType = r.string(32); privType = r.string(32);
    authPassphrase = r.string(1024); privPassphrase = r.string(1024); oidName = r.string(1536);
    securityEngineID = r.blob(32); contextEngineID = r.blob(32);
    unsigned v = r.u32(), level = r.u32(), retry = r.u32();
    uint64_t timeout = r.u64();
    capacity = r.u32(); unsigned op = r.u32(), wire = r.u32(); profile = r.u64();
    maxOids = r.u32(); unsigned mode = r.u32(), ranges = r.u32();
    if (!r.good() || (v != 1 && v != 2 && v != 3) || level < 1 || level > 3 ||
        (retry > INT_MAX - 1 && retry != UINT32_MAX) || timeout == 0 ||
        (timeout > LONG_MAX && timeout != UINT64_MAX) || capacity < 2 ||
        capacity > 65536 || op > SnmpSet || wire > SnmpWireOctets || address.empty() ||
        oidName.empty() || !maxOids || mode > 1 || ranges > 1 || (op == SnmpSet && wire == SnmpWireNone) ||
        (op == SnmpGet && wire != SnmpWireNone)) return false;
    version = v; securityLevel = level;
    retries = retry == UINT32_MAX ? -1 : static_cast<int>(retry);
    timeoutUs = timeout == UINT64_MAX ? -1 : static_cast<long>(timeout);
    operation = static_cast<SnmpOperation>(op); wireType = static_cast<SnmpWireType>(wire);
    legacy = mode;
    checkRanges = ranges;
    return true;
}

bool SnmpWorkerBinding::sameSession(const SnmpWorkerBinding &b) const
{
    return address == b.address && version == b.version && community == b.community &&
        securityName == b.securityName && contextName == b.contextName && securityLevel == b.securityLevel &&
        authType == b.authType && privType == b.privType && authPassphrase == b.authPassphrase &&
        privPassphrase == b.privPassphrase && profile == b.profile && securityEngineID == b.securityEngineID &&
        contextEngineID == b.contextEngineID && timeoutUs == b.timeoutUs && retries == b.retries;
}
