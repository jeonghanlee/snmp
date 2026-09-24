#include <stdio.h>
#include <atomic>
#include <string.h>
#include <dbAccess.h>
#include <dbLock.h>
#include <subRecord.h>
#include <epicsTime.h>
#include <registryFunction.h>
#include <callback.h>
#include <epicsThread.h>
#include <epicsEvent.h>
#include <iocsh.h>
#include <epicsExport.h>
#include "snmpRequest.h"

/* Inputs are real NPP database links read by sub record support. */
static long requestAudit(subRecord *record)
{
    char source[61] = {}, value[MAX_STRING_SIZE] = {}, encoded[2 * MAX_STRING_SIZE + 1] = {};
    DBADDR address;
    long count = 1;
    const char *name = record->inpb.type == DB_LINK ? record->inpb.value.pv_link.pvname : NULL;
    if (!name || strlen(name) >= sizeof(source)) return -1;
    snprintf(source, sizeof(source), "%s", name);
    char *field = strrchr(source, '.');
    if (field) *field = '\0';
    if (dbNameToAddr(source, &address) || dbGetField(&address, DBR_STRING, value, NULL, &count, NULL)) {
        printf("SNMPAUDIT_ERROR %s\n", record->name);
        fflush(stdout);
        return -1;
    }
    for (unsigned i = 0; i < strlen(value); ++i)
        snprintf(encoded + 2 * i, sizeof(encoded) - 2 * i, "%02x", (unsigned char)value[i]);
    record->val += 1;
    devSnmp_request::report(source);
    printf("SNMPAUDIT %llu %s %.17g %.0f %.0f %.0f status=%.0f undefined=%.0f raw=%.17g text=%s\n",
           (unsigned long long)epicsMonotonicGet(), record->name,
           record->a, record->b, record->c, record->val,
           record->d, record->e, record->f, encoded);
    fflush(stdout);
    return 0;
}
epicsRegisterFunction(requestAudit);

/* Fill the actual Base callback queue; no driver function is substituted. */
static epicsCallback blockers[3];
static epicsEvent blockerEntered;
static void blockCallback(epicsCallback *)
{
    blockerEntered.signal();
    epicsThreadSleep(0.9);
}

static void blockCallbacks(const iocshArgBuf *)
{
    for (unsigned i = 0; i < 3; ++i) {
        callbackSetCallback(blockCallback, &blockers[i]);
        callbackSetPriority(priorityLow, &blockers[i]);
        if (callbackRequest(&blockers[i])) {
            printf("SNMPBLOCK failure\n");
            return;
        }
        if (i == 0 && !blockerEntered.wait(1.0)) return;
    }
    printf("SNMPBLOCK ready\n");
    fflush(stdout);
}

static const iocshFuncDef blockDef = {"requestBlockCallbacks", 0, NULL};

/* Keep the real low-priority Base queue occupied until an explicit release.
 * Static callback storage remains valid through IOC exit and queue draining. */
static epicsCallback sustained[3];
static epicsEvent sustainedEntered, sustainedRelease;
static std::atomic<bool> sustainedActive(false);
static void sustainCallback(epicsCallback *callback)
{
    if (callback == &sustained[0]) {
        sustainedEntered.signal();
        bool released = sustainedRelease.wait(70.0);
        printf("SNMPSUSTAIN stopped released=%d time=%llu\n", released,
               (unsigned long long)epicsMonotonicGet());
    }
    if (callback == &sustained[2]) sustainedActive = false;
    fflush(stdout);
}

static void sustainCallbacks(const iocshArgBuf *)
{
    if (sustainedActive.exchange(true)) return;
    for (unsigned i = 0; i < 3; ++i) {
        callbackSetCallback(sustainCallback, &sustained[i]);
        callbackSetPriority(priorityLow, &sustained[i]);
        if (callbackRequest(&sustained[i])) {
            printf("SNMPSUSTAIN failure\n");
            sustainedRelease.signal();
            return;
        }
        if (i == 0 && !sustainedEntered.wait(1.0)) return;
    }
    printf("SNMPSUSTAIN ready time=%llu\n", (unsigned long long)epicsMonotonicGet());
    fflush(stdout);
}

static void releaseCallbacks(const iocshArgBuf *)
{
    sustainedRelease.signal();
}

static void queueState(const iocshArgBuf *)
{
    callbackQueueStats stats;
    callbackQueueStatus(0, &stats);
    printf("SNMPQUEUE time=%llu size=%d used=%d overflow=%d max=%d\n",
           (unsigned long long)epicsMonotonicGet(), stats.size,
           stats.numUsed[priorityLow], stats.numOverflow[priorityLow], stats.maxUsed[priorityLow]);
    fflush(stdout);
}

static const iocshFuncDef sustainDef = {"requestSustainCallbacks", 0, NULL};
static const iocshFuncDef releaseDef = {"requestReleaseCallbacks", 0, NULL};
static const iocshFuncDef queueDef = {"requestQueueState", 0, NULL};
static const iocshFuncDef diagnosticsDef = {"requestDiagnostics", 0, NULL};
static void diagnostics(const iocshArgBuf *)
{
    devSnmp_request::report();
    printf("SNMPDIAG_END %llu\n", (unsigned long long)epicsMonotonicGet());
    fflush(stdout);
}
static const iocshArg stateName = {"record", iocshArgString};
static const iocshArg stateToken = {"token", iocshArgInt};
static const iocshArg *stateArgs[] = {&stateName, &stateToken};
static const iocshFuncDef stateDef = {"requestRecordState", 2, stateArgs};

/* Observe Base state under the same record lock without processing it. */
static void recordState(const iocshArgBuf *args)
{
    DBADDR address;
    if (!args[0].sval || dbNameToAddr(args[0].sval, &address)) return;
    dbCommon *record = address.precord;
    dbScanLock(record);
    printf("SNMPSTATE %d %llu %s pact=%d rpro=%d lcnt=%d notify=%d\n",
           args[1].ival, (unsigned long long)epicsMonotonicGet(), record->name,
           record->pact, record->rpro, record->lcnt, record->ppn != NULL);
    fflush(stdout);
    dbScanUnlock(record);
}

static void registerProbe()
{
    iocshRegister(&blockDef, blockCallbacks);
    iocshRegister(&sustainDef, sustainCallbacks);
    iocshRegister(&releaseDef, releaseCallbacks);
    iocshRegister(&queueDef, queueState);
    iocshRegister(&diagnosticsDef, diagnostics);
    iocshRegister(&stateDef, recordState);
}
epicsExportRegistrar(registerProbe);
