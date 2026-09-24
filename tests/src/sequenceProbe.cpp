#include <stdio.h>
#include <subRecord.h>
#include <epicsTime.h>
#include <registryFunction.h>
#include <callback.h>
#include <epicsThread.h>
#include <epicsEvent.h>
#include <iocsh.h>
#include <epicsExport.h>

/* Inputs are real NPP database links read by sub record support. */
static long requestAudit(subRecord *record)
{
    record->val += 1;
    printf("SNMPAUDIT %llu %s %.17g %.0f %.0f %.0f\n",
           (unsigned long long)epicsMonotonicGet(), record->name,
           record->a, record->b, record->c, record->val);
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
static void registerProbe()
{
    iocshRegister(&blockDef, blockCallbacks);
}
epicsExportRegistrar(registerProbe);
