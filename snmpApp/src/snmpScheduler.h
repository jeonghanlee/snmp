#ifndef SNMP_SCHEDULER_H
#define SNMP_SCHEDULER_H

#include "snmpIpc.h"
#include <deque>
#include <mutex>

/* A ticket owns its complete encoded command. The queue lock never protects
 * request or record state; callers release it before claiming or completing
 * a request. Expiry returns every removed ticket for terminal arbitration.
 * Pending limits include retained tickets until dispatch or expiry removes
 * them and exclude the one active native transaction. */
struct SnmpTicket {
    uint64_t binding, generation, deadline, session;
    unsigned maxOids, capacity;
    bool write, coalesce;
    std::vector<unsigned long> oid;
    std::vector<unsigned char> command;
    size_t charge() const { return snmpIpc::headerBytes + 8 + command.size(); }
};

class SnmpScheduler {
public:
    static const size_t defaultPending = 1024;
    static const size_t maxBytes = 1024 * 1024;
    explicit SnmpScheduler(size_t pending = defaultPending);
    void setPendingLimit(size_t pending);
    bool admit(SnmpTicket ticket);
    std::vector<SnmpTicket> take();
    std::vector<SnmpTicket> expire();
    void stop();
    void report(uint64_t epoch);
private:
    std::mutex mutex;
    std::deque<SnmpTicket> queue;
    size_t pendingLimit, bytes, highCount, highBytes;
    uint64_t rejected;
    bool stopped;
};

#endif
