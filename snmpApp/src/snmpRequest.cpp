#include "devSnmp.h"
#include "snmpRequest.h"

#include <stdio.h>
#include <string.h>
#include <dbAccess.h>
#include <recSup.h>
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

devSnmp_request::devSnmp_request(dbCommon *prec, unsigned capacity,
                               const unsigned long *oid, unsigned oidLength)
    : record(prec), state(Idle), owner(NULL), text(capacity, 0),
      good(false), hasLong(false), hasDouble(false), stopping(false),
      callbackPending(false), longValue(0), doubleValue(0), generation(0),
      transaction(0), wireId(0)
{
    unsigned used = 0;
    numericOid[0] = '\0';
    for (unsigned i = 0; i < oidLength && used < sizeof(numericOid); ++i) {
        int count = snprintf(numericOid + used, sizeof(numericOid) - used, ".%lu", oid[i]);
        if (count < 0 || (unsigned)count >= sizeof(numericOid) - used) break;
        used += count;
    }
    memset(&callback, 0, sizeof(callback));
    callbackSetCallback(complete, &callback);
    callbackSetPriority(record->prio, &callback);
    callbackSetUser(this, &callback);
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
    snprintf(entry.record, sizeof(entry.record), "%s", record->name);
    snprintf(entry.event, sizeof(entry.event), "%s", name);
    entry.success = success;
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
                   request->record->name, request->generation,
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
    if (stopping || state != Idle) return false;
    ++generation;
    good = hasLong = hasDouble = false;
    owner = NULL;
    transaction = 0;
    wireId = 0;
    epicsTimeGetMonotonic(&accepted);
    state = Queued;
    event("accepted", true);
    return true;
}

bool devSnmp_request::pending()
{
    epicsGuard<epicsMutex> guard(mutex);
    return !stopping && state == Queued;
}

bool devSnmp_request::claim(devSnmp_session *session)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (stopping || state != Queued) return false;
    owner = session;
    transaction = session->traceId();
    state = InFlight;
    event("claimed", true);
    return true;
}

void devSnmp_request::dispatched(devSnmp_session *session, long nativeId)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (state != InFlight || owner != session) return;
    wireId = nativeId;
    event("dispatch", true);
}

void devSnmp_request::finish(devSnmp_session *session, variable_list *value)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (stopping || state != InFlight || owner != session) return;
    good = hasLong = hasDouble = false;
    if (value && value->type != SNMP_NOSUCHOBJECT &&
        value->type != SNMP_NOSUCHINSTANCE && value->type != SNMP_ENDOFMIBVIEW) {
        int count = snprint_value(&text[0], text.size(), value->name, value->name_length, value);
        good = count >= 0 && (unsigned)count < text.size();
        switch (value->type) {
        case ASN_INTEGER:
        case ASN_COUNTER:
        case ASN_UNSIGNED:
            if (value->val.integer) {
                longValue = *value->val.integer;
                hasLong = good;
            }
            break;
#ifdef NETSNMP_WITH_OPAQUE_SPECIAL_TYPES
        case ASN_OPAQUE_FLOAT:
            if (value->val.floatVal) {
                doubleValue = *value->val.floatVal;
                hasDouble = good;
            }
            break;
        case ASN_OPAQUE_DOUBLE:
            if (value->val.doubleVal) {
                doubleValue = *value->val.doubleVal;
                hasDouble = good;
            }
            break;
#endif
        }
    }
    owner = NULL;
    state = Ready;
    event("result", good);
}

void devSnmp_request::service()
{
    epicsGuard<epicsMutex> guard(mutex);
    if (stopping) return;
    if (state == Queued || state == InFlight) {
        epicsTimeStamp now;
        epicsTimeGetMonotonic(&now);
        if (epicsTimeDiffInSeconds(&now, &accepted) * 1000 >= snmpRequestTimeoutMSec) {
            owner = NULL;
            good = hasLong = hasDouble = false;
            state = Ready;
            event("result", false);
        }
    }
    if (state != Ready || callbackPending) return;
    state = Scheduled;
    callbackPending = true;
    if (callbackRequest(&callback)) {
        state = Ready;
        callbackPending = false;
    }
}

void devSnmp_request::complete(epicsCallback *callback)
{
    devSnmp_request *request = static_cast<devSnmp_request *>(callback->user);
    {
        epicsGuard<epicsMutex> guard(request->mutex);
        if (request->stopping) {
            request->callbackPending = false;
            request->state = Idle;
            return;
        }
    }
    dbScanLock(request->record);
    bool process;
    {
        epicsGuard<epicsMutex> guard(request->mutex);
        process = !request->stopping && request->state == Scheduled;
        if (process) request->state = Consuming;
    }
    if (process) (*request->record->rset->process)(request->record);
    {
        epicsGuard<epicsMutex> guard(request->mutex);
        if (process) request->event("complete", !request->record->pact);
        request->callbackPending = false;
    }
    dbScanUnlock(request->record);
}

void devSnmp_request::consumed(bool success)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (state != Consuming) return;
    event("applied", success);
    state = Idle;
}

bool devSnmp_request::valid()
{
    epicsGuard<epicsMutex> guard(mutex);
    return state == Consuming && good;
}

bool devSnmp_request::raw(char *value, unsigned capacity)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (state != Consuming || !good || !capacity) return false;
    snprintf(value, capacity, "%s", &text[0]);
    return true;
}

bool devSnmp_request::hasNativeLong()
{
    epicsGuard<epicsMutex> guard(mutex);
    return state == Consuming && good && hasLong;
}

bool devSnmp_request::hasNativeDouble()
{
    epicsGuard<epicsMutex> guard(mutex);
    return state == Consuming && good && hasDouble;
}

bool devSnmp_request::nativeLong(long *value)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (state != Consuming || !good || !hasLong) return false;
    *value = longValue;
    return true;
}

bool devSnmp_request::nativeDouble(double *value)
{
    epicsGuard<epicsMutex> guard(mutex);
    if (state != Consuming || !good || !hasDouble) return false;
    *value = doubleValue;
    return true;
}

bool devSnmp_request::shutdown()
{
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
    for (unsigned attempt = 0; attempt < 300; ++attempt) {
        bool pending = false;
        for (unsigned i = 0; i < requests.size(); ++i) {
            if (!requests[i]) continue;
            epicsGuard<epicsMutex> guard(requests[i]->mutex);
            pending |= requests[i]->callbackPending;
        }
        if (!pending) return true;
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
