#ifndef SNMP_EPICS_H
#define SNMP_EPICS_H

#include <callback.h>
#include "snmpTypes.h"

struct dbCommon;
struct link;
class devSnmp_request;

/* Record and callback storage share the same shutdown lifetime. */
class devSnmp_epics {
public:
    devSnmp_epics(dbCommon *record, unsigned capacity, const unsigned long *oid,
                  unsigned oidLength, SnmpIdentity profile);
    ~devSnmp_epics();
    devSnmp_request *request() { return acquisition; }

private:
    dbCommon *record;
    epicsCallback callback;
    devSnmp_request *acquisition;
    SnmpIdentity handle;
    static bool schedule(SnmpIdentity handle);
    static void complete(epicsCallback *callback);
};

/* Implemented by the transport in devSnmp.cpp: INP parsing, dpvt binding and
 * the exit flag stay there; the adapter owns only record completion. */
bool devSnmpAttachRequest(dbCommon *record, struct link *input);
bool devSnmpExiting();

#endif
