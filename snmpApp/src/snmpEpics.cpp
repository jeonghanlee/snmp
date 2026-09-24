#include "snmpEpics.h"
#include "snmpRequest.h"
#include "devSnmp.h"

#include <limits.h>
#include <string.h>
#include <dbAccess.h>
#include <recSup.h>
#include <recGbl.h>
#include <alarm.h>
#include <epicsExport.h>
#include <aiRecord.h>
#include <longinRecord.h>
#include <stringinRecord.h>

/* Handle registry indexed by handle - 1. It grows only during record
 * initialization, before the acquisition worker starts, and is read without
 * a lock from that worker afterwards; a destroyed adapter nulls its slot and
 * the vector never shrinks, so a handle is never reused in the process. A
 * late binding path would need a lock here. */
namespace {
std::vector<devSnmp_epics *> completions;
}

devSnmp_epics::devSnmp_epics(dbCommon *prec, unsigned capacity, const unsigned long *oid,
                             unsigned oidLength, SnmpIdentity profile)
    : record(prec), acquisition(NULL), handle(completions.size() + 1)
{
    memset(&callback, 0, sizeof(callback));
    callbackSetCallback(complete, &callback);
    callbackSetPriority(record->prio, &callback);
    callbackSetUser(this, &callback);
    SnmpBinding binding;
    binding.id = handle;
    binding.profile = profile;
    binding.operation = SnmpGet;
    binding.name = record->name;
    binding.oid.assign(oid, oid + oidLength);
    binding.capacity = capacity;
    SnmpCompletion target = {handle, schedule};
    acquisition = new devSnmp_request(binding, target);
    completions.push_back(this);
}

devSnmp_epics::~devSnmp_epics()
{
    completions[handle - 1] = NULL;
    delete acquisition;
}

bool devSnmp_epics::schedule(SnmpIdentity handle)
{
    if (!handle || handle > completions.size() || !completions[handle - 1]) return false;
    return callbackRequest(&completions[handle - 1]->callback) == 0;
}

void devSnmp_epics::complete(epicsCallback *callback)
{
    devSnmp_epics *adapter = static_cast<devSnmp_epics *>(callback->user);
    devSnmp_request *request = adapter->acquisition;
    if (!request->completionWanted()) return;
    dbScanLock(adapter->record);
    bool process = request->beginConsumption();
    if (process) (*adapter->record->rset->process)(adapter->record);
    request->completed(process, !adapter->record->pact);
    dbScanUnlock(adapter->record);
}

static long requestInit(dbCommon *record, struct link *input)
{
  if (input->type != INST_IO || record->scan == menuScanI_O_Intr) {
    recGblRecordError(S_db_badField, record, "SnmpRequest: invalid INP or SCAN");
    return S_db_badField;
  }
  if (!devSnmpAttachRequest(record, input)) {
    recGblRecordError(S_db_badField, record, "SnmpRequest: invalid input configuration");
    return S_db_badField;
  }
  return 0;
}

static long requestAiInit(aiRecord *record) { return requestInit((dbCommon *)record, &record->inp); }
static long requestLiInit(longinRecord *record) { return requestInit((dbCommon *)record, &record->inp); }
static long requestSiInit(stringinRecord *record) { return requestInit((dbCommon *)record, &record->inp); }

/* Positive means the initial asynchronous pass; zero means consumption.
 * PACT stays true throughout record support's conversion and FLNK pass. */
static int requestReadStart(dbCommon *record, devSnmp_pv **pv)
{
  *pv = (devSnmp_pv *)record->dpvt;
  if (devSnmpExiting() || !*pv || !(*pv)->request()) return -1;
  if (record->pact) return 0;
  if (!(*pv)->request()->begin()) return -1;
  record->pact = true;
  return 1;
}

static long requestAiRead(aiRecord *record)
{
  devSnmp_pv *pv;
  int start = requestReadStart((dbCommon *)record, &pv);
  if (start > 0) return 0;
  long status = -1;
  if (start == 0) {
    if (pv->usesRawValue()) {
      long value;
      if (pv->getValueLong(&value) && value >= INT_MIN && value <= INT_MAX) {
        record->rval = value;
        status = 0;
      }
    } else {
      double value;
      if (pv->getValueDouble(&value)) {
        record->val = value;
        status = 2;
      }
    }
  }
  if (status >= 0) record->udf = false;
  else recGblSetSevr(record, READ_ALARM, INVALID_ALARM);
  if (start == 0) pv->request()->consumed(status >= 0);
  return status;
}

static long requestLiRead(longinRecord *record)
{
  devSnmp_pv *pv;
  int start = requestReadStart((dbCommon *)record, &pv);
  if (start > 0) return 0;
  long value;
  bool good = start == 0 && pv->getValueLong(&value) && value >= INT_MIN && value <= INT_MAX;
  if (good) {
    record->val = value;
    record->udf = false;
  } else recGblSetSevr(record, READ_ALARM, INVALID_ALARM);
  if (start == 0) pv->request()->consumed(good);
  return good ? 0 : -1;
}

static long requestSiRead(stringinRecord *record)
{
  devSnmp_pv *pv;
  int start = requestReadStart((dbCommon *)record, &pv);
  if (start > 0) return 0;
  char value[sizeof(record->val)] = {};
  bool good = start == 0 && pv->getValueString(value, sizeof(value));
  if (good) {
    memcpy(record->val, value, sizeof(value));
    record->udf = false;
  } else recGblSetSevr(record, READ_ALARM, INVALID_ALARM);
  if (start == 0) pv->request()->consumed(good);
  return good ? 0 : -1;
}

struct RequestDset {
  long number;
  DEVSUPFUN report, init, init_record, get_ioint_info, read, special_linconv;
};
static RequestDset devSnmpRequestAi = {6, NULL, NULL, (DEVSUPFUN)requestAiInit, NULL, (DEVSUPFUN)requestAiRead, NULL};
static RequestDset devSnmpRequestLi = {5, NULL, NULL, (DEVSUPFUN)requestLiInit, NULL, (DEVSUPFUN)requestLiRead, NULL};
static RequestDset devSnmpRequestSi = {5, NULL, NULL, (DEVSUPFUN)requestSiInit, NULL, (DEVSUPFUN)requestSiRead, NULL};
epicsExportAddress(dset, devSnmpRequestAi);
epicsExportAddress(dset, devSnmpRequestLi);
epicsExportAddress(dset, devSnmpRequestSi);

