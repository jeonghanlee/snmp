#ifndef SNMP_REQUEST_H
#define SNMP_REQUEST_H

#include <vector>
#include <callback.h>
#include <epicsMutex.h>
#include <epicsTime.h>

struct dbCommon;
struct variable_list;
class devSnmp_session;

extern int snmpRequestTimeoutMSec;
extern int snmpRequestTrace;

/* One preallocated acquisition slot per input record. Network work never
 * takes the record lock. Only the EPICS callback consumes a ready result. */
class devSnmp_request {
public:
    devSnmp_request(dbCommon *record, unsigned capacity, const unsigned long *oid, unsigned oidLength);
    ~devSnmp_request();
    bool begin();
    bool pending();
    bool claim(devSnmp_session *session);
    void dispatched(devSnmp_session *session, long wireId);
    void finish(devSnmp_session *session, variable_list *value);
    void service();
    void consumed(bool success);
    bool raw(char *value, unsigned capacity);
    bool nativeLong(long *value);
    bool nativeDouble(double *value);
    bool hasNativeLong();
    bool hasNativeDouble();
    bool valid();
    static void start();
    static bool configurationOpen();
    static bool shutdown();
    static void dumpTrace();

private:
    enum State { Idle, Queued, InFlight, Ready, Scheduled, Consuming };
    dbCommon *record;
    epicsMutex mutex;
    epicsCallback callback;
    State state;
    devSnmp_session *owner;
    std::vector<char> text;
    bool good, hasLong, hasDouble, stopping, callbackPending;
    long longValue;
    double doubleValue;
    unsigned long long generation;
    unsigned long long transaction;
    long wireId;
    char numericOid[1537];
    epicsTimeStamp accepted;
    void event(const char *name, bool success);
    static void complete(epicsCallback *callback);
    static void worker(void *argument);
};

#endif
