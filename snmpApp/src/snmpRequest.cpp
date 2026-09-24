#include "snmpRequest.h"

#include <stdio.h>
#include <string.h>
#include <atomic>
#include <limits.h>
#include <epicsThread.h>
#include <epicsGuard.h>
#include <epicsEvent.h>

int snmpRequestTimeoutMSec = 10000;
int snmpRequestTrace = 0;

namespace {
const unsigned TraceCapacity = 8192;
struct TraceEntry {
    epicsUInt64 time;
    unsigned long long generation;
    unsigned long long transaction;
    long wireId;
    char oid[1537];
    char record[61];
    char event[16];
    bool success;
};
epicsMutex traceMutex;
TraceEntry traceEntries[TraceCapacity];
unsigned traceCount = 0;
bool traceOverflow = false;
std::vector<devSnmp_request *> requests;
epicsMutex workerMutex;
epicsEvent workerWake, workerExited;
bool workerStop = false, workerStarted = false;
std::atomic<bool> configurationLocked(false);
}

devSnmp_request::devSnmp_request(const SnmpBinding &input, const SnmpCompletion &target)
    : binding(input), completion(target), state(Idle), result(input.capacity),
      stopping(false), callbackPending(false), generation(0), transaction(0),
      wireId(0), accepted(0), deadline(0)
{
    unsigned used = 0;
    numericOid[0] = '\0';
    for (unsigned i = 0; i < binding.oid.size() && used < sizeof(numericOid); ++i) {
        int count = snprintf(numericOid + used, sizeof(numericOid) - used, ".%lu", binding.oid[i]);
        if (count < 0 || (unsigned)count >= sizeof(numericOid) - used) break;
        used += count;
    }
    memset(&statistics, 0, sizeof(statistics));
    requests.push_back(this);
}

devSnmp_request::~devSnmp_request()
{
    for (unsigned i = 0; i < requests.size(); ++i)
        if (requests[i] == this) requests[i] = NULL;
}

void devSnmp_request::event(const char *name, bool success)
{
    if (!snmpRequestTrace) return;
    epicsGuard<epicsMutex> guard(traceMutex);
    if (traceCount == TraceCapacity) {
        traceOverflow = true;
        return;
    }
    TraceEntry &entry = traceEntries[traceCount++];
    entry.time = epicsMonotonicGet();
    entry.generation = generation;
    entry.transaction = transaction;
    entry.wireId = wireId;
    snprintf(entry.oid, sizeof(entry.oid), "%s", numericOid);
    snprintf(entry.record, sizeof(entry.record), "%s", binding.name.c_str());
    snprintf(entry.event, sizeof(entry.event), "%s", name);
    entry.success = success;
}

/* Copy each bounded record snapshot under its mutex, then release that mutex
 * before printing. Totals combine sequential snapshots. */
void devSnmp_request::report(const char *recordName)
{
    const char *states[] = {"idle", "queued", "inflight", "ready", "scheduled", "consuming"};
    unsigned count = 0, queued = 0, active = 0;
    unsigned long long acceptedTotal = 0, rejectedTotal = 0;
    unsigned long long validTotal = 0, failedTotal = 0, completedTotal = 0, retriesTotal = 0;
    for (unsigned i = 0; i < requests.size(); ++i) {
        devSnmp_request *request = requests[i];
        if (!request || (recordName && strcmp(recordName, request->binding.name.c_str()))) continue;
        Statistics snapshot;
        State current;
        bool pending, stopped;
        unsigned long long generation, now;
        {
            epicsGuard<epicsMutex> guard(request->mutex);
            snapshot = request->statistics;
            current = request->state;
            pending = request->callbackPending;
            stopped = request->stopping;
            generation = request->generation;
            now = epicsMonotonicGet();
        }
        ++count;
        queued += current == Queued;
        active += current != Idle || pending;
        acceptedTotal += snapshot.acceptedCount;
        rejectedTotal += snapshot.rejectedCount;
        validTotal += snapshot.validCount;
        failedTotal += snapshot.failedCount;
        completedTotal += snapshot.completedCount;
        retriesTotal += snapshot.callbackRetries;
        double validAge = snapshot.lastValidAt ? (now - snapshot.lastValidAt) / 1e6 : -1;
        double queueAge = current == Queued ? (now - snapshot.acceptedAt) / 1e6 : 0;
        double queueTime = snapshot.dispatchedAt ? (snapshot.dispatchedAt - snapshot.acceptedAt) / 1e6 : -1;
        double networkTime = snapshot.terminalAt && snapshot.dispatchedAt ?
            (snapshot.terminalAt - snapshot.dispatchedAt) / 1e6 : -1;
        double callbackTime = snapshot.appliedAt ? (snapshot.appliedAt - snapshot.terminalAt) / 1e6 : -1;
        double processingTime = snapshot.completedAt ? (snapshot.completedAt - snapshot.appliedAt) / 1e6 : -1;
        double totalTime = snapshot.completedAt ? (snapshot.completedAt - snapshot.acceptedAt) / 1e6 : -1;
        printf("SNMPDIAG %llu %s generation=%llu state=%s callback=%d stopping=%d "
               "accepted=%llu rejected=%llu valid=%llu failed=%llu completed=%llu callback_retries=%llu "
               "last_valid_generation=%llu accepted_ns=%llu claimed_ns=%llu dispatched_ns=%llu "
               "terminal_ns=%llu applied_ns=%llu completed_ns=%llu last_valid_ns=%llu "
               "last_valid_age_ms=%.6f queue_age_ms=%.6f queue_ms=%.6f network_ms=%.6f "
               "callback_ms=%.6f processing_ms=%.6f total_ms=%.6f\n",
               now, request->binding.name.c_str(), generation, states[current], pending, stopped,
               snapshot.acceptedCount, snapshot.rejectedCount, snapshot.validCount, snapshot.failedCount,
               snapshot.completedCount, snapshot.callbackRetries, snapshot.lastValidGeneration,
               snapshot.acceptedAt, snapshot.claimedAt, snapshot.dispatchedAt, snapshot.terminalAt,
               snapshot.appliedAt, snapshot.completedAt, snapshot.lastValidAt,
               validAge, queueAge, queueTime, networkTime, callbackTime, processingTime, totalTime);
    }
    printf("SNMPDIAG_TOTAL records=%u queued=%u active=%u accepted=%llu rejected=%llu "
           "valid=%llu failed=%llu completed=%llu callback_retries=%llu\n",
           count, queued, active, acceptedTotal, rejectedTotal, validTotal, failedTotal,
           completedTotal, retriesTotal);
    fflush(stdout);
}

void devSnmp_request::dumpTrace()
{
    const char *states[] = {"idle", "queued", "inflight", "ready", "scheduled", "consuming"};
    for (unsigned i = 0; i < requests.size(); ++i) {
        devSnmp_request *request = requests[i];
        if (!request) continue;
        epicsGuard<epicsMutex> guard(request->mutex);
        if (request->state != Idle) {
            printf("SNMPREQUEST %s generation=%llu state=%s callback=%d\n",
                   request->binding.name.c_str(), request->generation,
                   states[request->state], request->callbackPending);
        }
    }
    if (!snmpRequestTrace) return;
    epicsGuard<epicsMutex> guard(traceMutex);
    printf("SNMPREQ_TRACE count=%u overflow=%d\n", traceCount, traceOverflow);
    for (unsigned i = 0; i < traceCount; ++i) {
        const TraceEntry &entry = traceEntries[i];
        printf("SNMPREQ %u %llu %s %llu %s %d tx=%llu wire=%ld oid=%s\n", i,
               (unsigned long long)entry.time, entry.record,
               entry.generation, entry.event, entry.success,
               entry.transaction, entry.wireId, entry.oid);
    }
}

bool devSnmp_request::begin()
{
    epicsGuard<epicsMutex> guard(mutex);
    if (stopping || state != Idle) {
        ++statistics.rejectedCount;
        return false;
    }
    ++generation;
    result.valid = result.hasLong = result.hasDouble = false;
    transaction = 0;
    wireId = 0;
    accepted = epicsMonotonicGet();
    deadline = accepted + (epicsUInt64)snmpRequestTimeoutMSec * 1000000;
    ++statistics.acceptedCount;
    statistics.acceptedAt = accepted;
    statistics.claimedAt = statistics.dispatchedAt = statistics.terminalAt = 0;
    statistics.appliedAt = statistics.completedAt = 0;
    state = Queued;
    event("accepted", true);
    return true;
}

bool devSnmp_request::pending()
{
    epicsGuard<epicsMutex> guard(mutex);
    if (!stopping) expire();
    return !stopping && state == Queued;
}

bool devSnmp_request::claim(SnmpIdentity identity)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (stopping || state != Queued || expire()) return false;
    transaction = identity;
    statistics.claimedAt = epicsMonotonicGet();
    state = InFlight;
    event("claimed", true);
    return true;
}

void devSnmp_request::dispatched(SnmpIdentity identity, long nativeId)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (state != InFlight || transaction != identity) return;
    wireId = nativeId;
    statistics.dispatchedAt = epicsMonotonicGet();
    event("dispatch", true);
}

void devSnmp_request::finish(SnmpIdentity identity, const SnmpValue &value)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (stopping || state != InFlight || transaction != identity || expire()) return;
    result.valid = result.hasLong = result.hasDouble = false;
    if (value.valid && strlen(&value.text[0]) < result.text.size() &&
        value.length <= result.bytes.size() && value.length <= value.bytes.size() &&
        value.oid.size() <= result.oid.capacity()) {
        result.kind = value.kind;
        result.wireType = value.wireType;
        result.signedValue = value.signedValue;
        result.unsignedValue = value.unsignedValue;
        result.realValue = value.realValue;
        result.length = value.length;
        memcpy(&result.text[0], &value.text[0], strlen(&value.text[0]) + 1);
        if (value.length) memcpy(&result.bytes[0], &value.bytes[0], value.length);
        result.oid.assign(value.oid.begin(), value.oid.end());
        result.valid = true;
        result.hasLong = value.hasLong;
        result.hasDouble = value.hasDouble;
    }
    if (!expire()) ready(result.valid);
}

/* Terminal arbitration runs under the request mutex on every entry path.
 * A ready result is immutable even while callback admission is delayed. */
void devSnmp_request::ready(bool success)
{
    result.valid = success;
    if (!success) result.hasLong = result.hasDouble = false;
    state = Ready;
    statistics.terminalAt = epicsMonotonicGet();
    event("result", success);
}

bool devSnmp_request::expire()
{
    if ((state == Queued || state == InFlight) && epicsMonotonicGet() >= deadline) {
        ready(false);
        return true;
    }
    return false;
}

void devSnmp_request::service()
{
    epicsGuard<epicsMutex> guard(mutex);
    if (stopping) return;
    expire();
    if (state != Ready || callbackPending) return;
    state = Scheduled;
    callbackPending = true;
    if (!completion.schedule(completion.handle)) {
        ++statistics.callbackRetries;
        state = Ready;
        callbackPending = false;
    }
}

bool devSnmp_request::completionWanted()
{
    epicsGuard<epicsMutex> guard(mutex);
    if (!stopping) return true;
    callbackPending = false;
    state = Idle;
    return false;
}

bool devSnmp_request::beginConsumption()
{
    epicsGuard<epicsMutex> guard(mutex);
    if (stopping || state != Scheduled) return false;
    state = Consuming;
    return true;
}

void devSnmp_request::completed(bool processed, bool pactClear)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (processed) {
        statistics.completedAt = epicsMonotonicGet();
        ++statistics.completedCount;
        event("complete", pactClear);
    }
    callbackPending = false;
}

void devSnmp_request::consumed(bool success)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (state != Consuming) return;
    statistics.appliedAt = epicsMonotonicGet();
    if (success) {
        ++statistics.validCount;
        statistics.lastValidAt = statistics.appliedAt;
        statistics.lastValidGeneration = generation;
    } else {
        ++statistics.failedCount;
    }
    event("applied", success);
    state = Idle;
}

bool devSnmp_request::valid()
{
    epicsGuard<epicsMutex> guard(mutex);
    return state == Consuming && result.valid;
}

bool devSnmp_request::raw(char *value, unsigned capacity)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (state != Consuming || !result.valid || !capacity) return false;
    snprintf(value, capacity, "%s", &result.text[0]);
    return true;
}

bool devSnmp_request::hasNativeLong()
{
    epicsGuard<epicsMutex> guard(mutex);
    return state == Consuming && result.valid && result.hasLong;
}

bool devSnmp_request::hasNativeDouble()
{
    epicsGuard<epicsMutex> guard(mutex);
    return state == Consuming && result.valid && result.hasDouble;
}

bool devSnmp_request::nativeLong(long *value)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (state != Consuming || !result.valid || !result.hasLong) return false;
    if (result.kind == SnmpValue::Signed) {
        if (result.signedValue < LONG_MIN || result.signedValue > LONG_MAX) return false;
        *value = static_cast<long>(result.signedValue);
    } else {
        if (result.unsignedValue > static_cast<uint64_t>(LONG_MAX)) return false;
        *value = static_cast<long>(result.unsignedValue);
    }
    return true;
}

bool devSnmp_request::nativeDouble(double *value)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (state != Consuming || !result.valid || !result.hasDouble) return false;
    *value = result.realValue;
    return true;
}

bool devSnmp_request::shutdown()
{
    printf("devSnmp: request shutdown entered\n");
    for (unsigned i = 0; i < requests.size(); ++i) {
        if (!requests[i]) continue;
        epicsGuard<epicsMutex> guard(requests[i]->mutex);
        requests[i]->stopping = true;
    }
    {
        epicsGuard<epicsMutex> guard(workerMutex);
        workerStop = true;
    }
    workerWake.signal();
    if (workerStarted && !workerExited.wait(3.0)) return false;
    printf("devSnmp: completion worker stopped\n");
    for (unsigned attempt = 0; attempt < 300; ++attempt) {
        bool pending = false;
        for (unsigned i = 0; i < requests.size(); ++i) {
            if (!requests[i]) continue;
            epicsGuard<epicsMutex> guard(requests[i]->mutex);
            pending |= requests[i]->callbackPending;
        }
        if (!pending) {
            printf("devSnmp: request callbacks drained\n");
            return true;
        }
        epicsThreadSleep(0.01);
    }
    return false;
}

void devSnmp_request::start()
{
    configurationLocked = true;
    if (requests.empty()) return;
    epicsThreadMustCreate("snmpComplete", epicsThreadPriorityMedium,
                         epicsThreadGetStackSize(epicsThreadStackBig), worker, NULL);
    workerStarted = true;
}

bool devSnmp_request::configurationOpen()
{
    return !configurationLocked;
}

void devSnmp_request::worker(void *)
{
    while (true) {
        {
            epicsGuard<epicsMutex> guard(workerMutex);
            if (workerStop) break;
        }
        for (unsigned i = 0; i < requests.size(); ++i)
            if (requests[i]) requests[i]->service();
        workerWake.wait(0.01);
    }
    workerExited.signal();
}
