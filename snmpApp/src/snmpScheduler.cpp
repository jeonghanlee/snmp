#include "snmpScheduler.h"
#include <algorithm>
#include <set>
#include <stdio.h>

SnmpScheduler::SnmpScheduler(size_t pending)
    : pendingLimit(pending), bytes(0), highCount(0), highBytes(0), rejected(0), stopped(false) {}

void SnmpScheduler::setPendingLimit(size_t pending)
{
    std::lock_guard<std::mutex> guard(mutex);
    pendingLimit = pending;
}

bool SnmpScheduler::admit(SnmpTicket ticket)
{
    std::lock_guard<std::mutex> guard(mutex);
    if (stopped || ticket.charge() > snmpIpc::maxFrameBytes) { ++rejected; return false; }
    if (ticket.coalesce) {
        for (std::deque<SnmpTicket>::iterator i = queue.begin(); i != queue.end(); ++i) {
            if (i->coalesce && i->binding == ticket.binding && i->write == ticket.write) {
                if (ticket.charge() > maxBytes - (bytes - i->charge())) { ++rejected; return false; }
                bytes -= i->charge(); bytes += ticket.charge();
                *i = std::move(ticket);
                highBytes = std::max(highBytes, bytes);
                return true;
            }
        }
    }
    if (queue.size() >= pendingLimit || ticket.charge() > maxBytes - bytes) { ++rejected; return false; }
    size_t charge = ticket.charge();
    queue.push_back(std::move(ticket));
    bytes += charge;
    highCount = std::max(highCount, queue.size());
    highBytes = std::max(highBytes, bytes);
    return true;
}

std::vector<SnmpTicket> SnmpScheduler::take()
{
    std::lock_guard<std::mutex> guard(mutex);
    std::vector<SnmpTicket> batch;
    std::set<std::vector<unsigned long> > oids;
    size_t encoded = snmpIpc::headerBytes + 4;
    unsigned capacity = 0, limit = 0;
    for (std::deque<SnmpTicket>::iterator i = queue.begin(); i != queue.end(); ++i) {
        if (!batch.empty() && (batch.front().write || i->write || i->session != batch.front().session)) break;
        unsigned nextCapacity = std::max(capacity, std::max(1024u, i->capacity));
        unsigned nextLimit = batch.empty() ? i->maxOids : std::min(limit, i->maxOids);
        size_t oidCount = oids.size() + (oids.count(i->oid) ? 0 : 1);
        /* The result carries text and octets plus a maximum-length OID for
         * every waiter, including those sharing one wire OID. */
        size_t resultBound = snmpIpc::headerBytes + 4 + (batch.size() + 1) * (2 * nextCapacity + 640);
        if (oidCount > nextLimit || resultBound > snmpIpc::maxFrameBytes ||
            encoded + 4 + i->command.size() > snmpIpc::maxFrameBytes) break;
        encoded += 4 + i->command.size(); capacity = nextCapacity; limit = nextLimit;
        oids.insert(i->oid);
        batch.push_back(*i);
    }
    for (size_t i = 0; i < batch.size(); ++i) { bytes -= queue.front().charge(); queue.pop_front(); }
    return batch;
}

std::vector<SnmpTicket> SnmpScheduler::expire()
{
    std::lock_guard<std::mutex> guard(mutex);
    std::vector<SnmpTicket> expired;
    uint64_t now = snmpIpc::now();
    for (std::deque<SnmpTicket>::iterator i = queue.begin(); i != queue.end();) {
        if (i->deadline <= now) {
            expired.push_back(std::move(*i));
            bytes -= expired.back().charge();
            i = queue.erase(i);
        } else ++i;
    }
    return expired;
}

void SnmpScheduler::stop()
{
    std::lock_guard<std::mutex> guard(mutex);
    stopped = true; queue.clear(); bytes = 0;
}

void SnmpScheduler::report(uint64_t epoch)
{
    std::lock_guard<std::mutex> guard(mutex);
    printf("SNMPQUEUE epoch=%llu count=%zu bytes=%zu high_count=%zu high_bytes=%zu rejected=%llu pending_limit=%zu\n",
           (unsigned long long)epoch, queue.size(), bytes, highCount, highBytes, (unsigned long long)rejected,
           pendingLimit);
}
