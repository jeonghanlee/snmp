#ifndef SNMP_REQUEST_H
#define SNMP_REQUEST_H

#include <vector>
#include <epicsMutex.h>
#include <epicsTime.h>
#include "snmpTypes.h"

extern int snmpRequestTimeoutMSec;
extern int snmpRequestTrace;

/* One preallocated request slot per record, for a request input (one GET)
 * or a request output (one SET). Network work never takes the record lock.
 * Only the EPICS callback consumes a ready result.
 *
 * Transport side: begin() runs with the record lock held and takes the slot
 * mutex itself; for an output it copies the checked value to send into the
 * owned payload, which stays immutable until the slot returns to Idle.
 * markScheduled() lets one scheduler own a queued write until it is claimed
 * or expires, so a write is never queued twice. claim(), dispatched() and
 * finish() identify one transport transaction by an opaque SnmpIdentity
 * that the caller supplies; zero is reserved for no transaction and an
 * identity must never be reused within the process, otherwise a stale
 * response could satisfy a later pass. The native request ID is trace data
 * only, never the identity.
 *
 * Completion side, called from the Base callback thread in this order:
 * completionWanted() (abandons the slot and returns false while stopping),
 * dbScanLock, beginConsumption(), record processing during which device
 * support calls consumed(), completed(), dbScanUnlock. completed() always
 * releases the pending callback and counts a completion only when processed
 * is true; the caller passes processed=false when beginConsumption()
 * refused. A processed pass in which record support never called device
 * support, as under simulation mode, discards the result as failed so the
 * slot returns to Idle. timedOut() reports whether the consumed failure was
 * a library timeout or the request deadline. No other thread may call the
 * completion-side functions. */
class devSnmp_request {
public:
    devSnmp_request(const SnmpBinding &binding, const SnmpCompletion &completion);
    ~devSnmp_request();
    bool begin(const SnmpValue *value = NULL);
    bool pending();
    bool markScheduled(unsigned long long &scheduledGeneration);
    epicsUInt64 acceptedAt();
    bool isWrite() const { return binding.operation == SnmpSet; }
    SnmpWireType wireType() const { return binding.wireType; }
    const SnmpValue &payload() const { return payloadValue; }
    bool claim(SnmpIdentity transaction, unsigned long long scheduledGeneration = 0);
    bool claimWorker(SnmpIdentity transaction, unsigned long long scheduledGeneration);
    void expireWorker(unsigned long long scheduledGeneration);
    typedef bool (*Admission)(void *, unsigned long long, uint64_t, const SnmpValue *);
    void setAdmission(Admission function, void *context);
    void dispatched(SnmpIdentity transaction, long wireId);
    void finish(SnmpIdentity transaction, const SnmpValue &value, bool timedOut);
    unsigned capacity() const { return binding.capacity; }
    void service();
    bool completionWanted();
    bool beginConsumption();
    void completed(bool processed, bool pactClear);
    void consumed(bool success);
    bool raw(char *value, unsigned capacity);
    bool nativeLong(long *value);
    bool nativeDouble(double *value);
    bool hasNativeLong();
    bool hasNativeDouble();
    bool valid();
    bool consuming();
    bool timedOut();
    static void start();
    static bool configurationOpen();
    static bool shutdown();
    static void dumpTrace();
    static void report(const char *recordName = NULL);

private:
    enum State { Idle, Queued, InFlight, Ready, Scheduled, Consuming };
    const SnmpBinding binding;
    const SnmpCompletion completion;
    epicsMutex mutex;
    State state;
    SnmpValue result;
    SnmpValue payloadValue;
    bool stopping, callbackPending, timeout, scheduled;
    unsigned long long generation;
    unsigned long long transaction;
    long wireId;
    char numericOid[1537];
    epicsUInt64 accepted, deadline;
    Admission admission;
    void *admissionContext;
    struct Statistics {
        unsigned long long acceptedCount, rejectedCount, validCount, failedCount;
        unsigned long long completedCount, callbackRetries, lastValidGeneration;
        unsigned long long acceptedAt, claimedAt, dispatchedAt, terminalAt;
        unsigned long long appliedAt, completedAt, lastValidAt;
    } statistics;
    bool expire();
    void ready(bool success, bool timedOut);
    void event(const char *name, bool success);
    static void worker(void *argument);
};

#endif
