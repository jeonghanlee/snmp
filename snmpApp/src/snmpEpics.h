#ifndef SNMP_EPICS_H
#define SNMP_EPICS_H

#include <callback.h>
#include "snmpTypes.h"

struct dbCommon;
struct link;
struct dbChannel;
struct db_field_log;
class devSnmp_request;

/* Record and callback storage share the same shutdown lifetime. A request
 * output longout also owns an in-IOC monitor subscription on its OOPT field
 * so the module can keep OOPT at Every Time; see docs/snmp-architecture.md
 * "Request-Driven Writes". */
class devSnmp_epics {
public:
    devSnmp_epics(dbCommon *record, unsigned capacity, const unsigned long *oid,
                  unsigned oidLength, SnmpIdentity profile, SnmpOperation operation,
                  SnmpWireType wireType);
    ~devSnmp_epics();
    devSnmp_request *request() { return acquisition; }
    bool begin(const SnmpValue *payload = 0);
    bool isWrite() const { return operation == SnmpSet; }
    /* Subscribes to the longout's OOPT field; false when the IOC event
     * service refused, which fails the binding. */
    bool watchOopt();
    /* Cancels the OOPT subscription and deletes its channel; safe to repeat. */
    void unwatchOopt();
    /* Restores OOPT to Every Time when it was changed, posting the field and
     * logging; the caller holds the record lock. Returns true when it changed. */
    bool restoreOopt(const char *where);

private:
    dbCommon *record;
    epicsCallback callback;
    devSnmp_request *acquisition;
    SnmpIdentity handle;
    SnmpOperation operation;
    dbChannel *ooptChannel;
    void *ooptSubscription;
    static bool schedule(SnmpIdentity handle);
    static void complete(epicsCallback *callback);
    static void ooptEvent(void *user, dbChannel *channel, int remaining, db_field_log *log);
};

/* Implemented by the transport in devSnmp.cpp: INP/OUT parsing, dpvt
 * binding and the exit flag stay there; the adapter owns only record
 * completion. kind selects the output record: 'a' ao, 'l' longout, 's'
 * stringout. */
bool devSnmpAttachRequest(dbCommon *record, struct link *input);
bool devSnmpAttachRequestWrite(dbCommon *record, struct link *output, char kind);
bool devSnmpExiting();

/* Closes the OOPT monitor event service before the request slots stop. */
void devSnmpEpicsStop();

#endif
