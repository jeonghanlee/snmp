#include "snmpEpics.h"
#include "snmpRequest.h"
#include "devSnmp.h"

#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <dbAccess.h>
#include <dbChannel.h>
#include <dbEvent.h>
#include <recSup.h>
#include <recGbl.h>
#include <alarm.h>
#include <errlog.h>
#include <epicsMutex.h>
#include <epicsGuard.h>
#include <epicsThread.h>
#include <epicsExport.h>
#include <aiRecord.h>
#include <longinRecord.h>
#include <stringinRecord.h>
#include <aoRecord.h>
#include <longoutRecord.h>
#include <stringoutRecord.h>

/* Handle registry indexed by handle - 1. It grows only during record
 * initialization, before the acquisition worker starts, and is read without
 * a lock from that worker afterwards; a destroyed adapter nulls its slot and
 * the vector never shrinks, so a handle is never reused in the process. A
 * late binding path would need a lock here.
 *
 * The OOPT monitor shares one IOC event context and its snmpOopt thread for
 * every request longout; both are created at the first longout binding. */
namespace {
std::vector<devSnmp_epics *> completions;
epicsMutex ooptMutex;
dbEventCtx ooptContext = NULL;
const char *ooptThreadName = "snmpOopt";
}

devSnmp_epics::devSnmp_epics(dbCommon *prec, unsigned capacity, const unsigned long *oid,
                             unsigned oidLength, SnmpIdentity profile, SnmpOperation op,
                             SnmpWireType wireType)
    : record(prec), acquisition(NULL), handle(completions.size() + 1), operation(op),
      ooptChannel(NULL), ooptSubscription(NULL)
{
    memset(&callback, 0, sizeof(callback));
    callbackSetCallback(complete, &callback);
    callbackSetPriority(record->prio, &callback);
    callbackSetUser(this, &callback);
    SnmpBinding binding;
    binding.id = handle;
    binding.profile = profile;
    binding.operation = op;
    binding.wireType = wireType;
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
    unwatchOopt();
    delete acquisition;
}

/* Runs under the record lock with no completion pending. Each request takes
 * the record's PRIO when it is admitted; a PRIO change during an active read
 * applies from the next request. */
bool devSnmp_epics::begin(const SnmpValue *payload)
{
    callbackSetPriority(record->prio, &callback);
    return acquisition->begin(payload);
}

bool devSnmp_epics::schedule(SnmpIdentity handle)
{
    if (!handle || handle > completions.size() || !completions[handle - 1]) return false;
    return callbackRequest(&completions[handle - 1]->callback) == 0;
}

/* A failed write raises its alarm here, before record processing, so the
 * alarm appears in this pass whether or not record support reaches the write
 * routine (simulation mode, IVOA). A longout's OOPT is restored first; the
 * write itself is reported exactly as the agent answered. */
void devSnmp_epics::complete(epicsCallback *callback)
{
    devSnmp_epics *adapter = static_cast<devSnmp_epics *>(callback->user);
    devSnmp_request *request = adapter->acquisition;
    if (!request->completionWanted()) return;
    dbScanLock(adapter->record);
    if (adapter->ooptChannel) adapter->restoreOopt("completion");
    bool process = request->beginConsumption();
    if (process && adapter->isWrite() && !request->valid())
        recGblSetSevr(adapter->record, request->timedOut() ? TIMEOUT_ALARM : WRITE_ALARM, INVALID_ALARM);
    if (process) (*adapter->record->rset->process)(adapter->record);
    request->completed(process, !adapter->record->pact);
    dbScanUnlock(adapter->record);
}

bool devSnmp_epics::watchOopt()
{
    epicsGuard<epicsMutex> guard(ooptMutex);
    if (!ooptContext) {
        dbEventCtx context = db_init_events();
        if (!context) return false;
        if (db_start_events(context, ooptThreadName, NULL, NULL, epicsThreadPriorityCAServerLow) != DB_EVENT_OK) {
            db_close_events(context);
            return false;
        }
        ooptContext = context;
    }
    std::string field = std::string(record->name) + ".OOPT";
    ooptChannel = dbChannelCreate(field.c_str());
    if (!ooptChannel || dbChannelOpen(ooptChannel)) return false;
    ooptSubscription = db_add_event(ooptContext, ooptChannel, ooptEvent, this, DBE_VALUE);
    if (!ooptSubscription) return false;
    db_event_enable(static_cast<dbEventSubscription>(ooptSubscription));
    return true;
}

void devSnmp_epics::unwatchOopt()
{
    if (ooptSubscription) db_cancel_event(static_cast<dbEventSubscription>(ooptSubscription));
    if (ooptChannel) dbChannelDelete(ooptChannel);
    ooptSubscription = NULL;
    ooptChannel = NULL;
}

bool devSnmp_epics::restoreOopt(const char *where)
{
    longoutRecord *prec = reinterpret_cast<longoutRecord *>(record);
    if (prec->oopt == longoutOOPT_Every_Time) return false;
    epicsEnum16 replaced = prec->oopt;
    prec->oopt = longoutOOPT_Every_Time;
    db_post_events(prec, &prec->oopt, DBE_VALUE | DBE_LOG);
    errlogPrintf("devSnmp: %s OOPT %u restored to Every Time (%s)\n", prec->name, (unsigned)replaced, where);
    return true;
}

/* Reads the field under the record lock, never the value the event carries,
 * because a first pass or a completion may already have restored it. The
 * alarm is published without processing the record, as dbProcess publishes
 * its SCAN alarm, so SEVR and STAT change at once and nothing stays pending. */
void devSnmp_epics::ooptEvent(void *user, dbChannel *, int, db_field_log *)
{
    devSnmp_epics *adapter = static_cast<devSnmp_epics *>(user);
    if (devSnmpExiting()) return;
    dbCommon *record = adapter->record;
    dbScanLock(record);
    if (adapter->restoreOopt("monitor")) {
        recGblSetSevrMsg(record, WRITE_ALARM, INVALID_ALARM, "OOPT restored");
        unsigned short mask = recGblResetAlarms(record) | DBE_VALUE | DBE_LOG;
        dbFldDes *value = record->rdes->papFldDes[record->rdes->indvalFlddes];
        db_post_events(record, reinterpret_cast<char *>(record) + value->offset, mask);
    }
    dbScanUnlock(record);
}

/* Runs at exit before the request slots stop. Every subscription is
 * cancelled, which waits for a callback in progress, and its channel deleted
 * before the shared context closes, so a later db_post_events on OOPT and the
 * adapter destructors find no event state to touch. */
void devSnmpEpicsStop()
{
    epicsGuard<epicsMutex> guard(ooptMutex);
    for (size_t i = 0; i < completions.size(); ++i)
        if (completions[i]) completions[i]->unwatchOopt();
    if (ooptContext) db_close_events(ooptContext);
    ooptContext = NULL;
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
  if (!(*pv)->epics()->begin()) return -1;
  record->pact = true;
  return 1;
}

/* A library timeout after its retries, which includes a reply the library
 * discards as malformed, or the request deadline raises TIMEOUT; every other
 * failure, such as admission, session open, send, security, agent error
 * status, varbind or conversion, raises READ.
 * Called before consumed() releases the result. */
static epicsEnum16 requestFailure(int start, devSnmp_pv *pv)
{
  return start == 0 && pv->request()->timedOut() ? TIMEOUT_ALARM : READ_ALARM;
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
  else recGblSetSevr(record, requestFailure(start, pv), INVALID_ALARM);
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
  } else recGblSetSevr(record, requestFailure(start, pv), INVALID_ALARM);
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
  } else recGblSetSevr(record, requestFailure(start, pv), INVALID_ALARM);
  if (start == 0) pv->request()->consumed(good);
  return good ? 0 : -1;
}

/* Request outputs. Initialization sends nothing; a longout must start at OOPT
 * Every Time and gets its OOPT monitor here. ao returns 2 so VAL comes from
 * the database without RVAL conversion. */
static long requestOutInit(dbCommon *record, struct link *output, char kind)
{
  if (output->type != INST_IO || record->scan == menuScanI_O_Intr) {
    recGblRecordError(S_db_badField, record, "SnmpRequest: invalid OUT or SCAN");
    return S_db_badField;
  }
  if (kind == 'l' && ((longoutRecord *)record)->oopt != longoutOOPT_Every_Time) {
    recGblRecordError(S_db_badField, record, "SnmpRequest: OOPT must be Every Time");
    return S_db_badField;
  }
  if (!devSnmpAttachRequestWrite(record, output, kind)) {
    recGblRecordError(S_db_badField, record, "SnmpRequest: invalid output configuration");
    return S_db_badField;
  }
  devSnmp_pv *pv = (devSnmp_pv *)record->dpvt;
  if (kind == 'l' && !pv->epics()->watchOopt()) {
    recGblRecordError(S_db_badField, record, "SnmpRequest: OOPT monitor subscription failed");
    return S_db_badField;
  }
  return kind == 'a' ? 2 : 0;
}

static long requestAoInit(aoRecord *record) { return requestOutInit((dbCommon *)record, &record->out, 'a'); }
static long requestLoInit(longoutRecord *record) { return requestOutInit((dbCommon *)record, &record->out, 'l'); }
static long requestSoInit(stringoutRecord *record) { return requestOutInit((dbCommon *)record, &record->out, 's'); }

/* First pass of a request output: the value is checked and admitted under
 * the record lock before any network I/O. A value that fails its check or
 * an admission that fails raises WRITE/INVALID, leaves PACT clear and
 * returns a negative status, so the record completes in this pass. */
static long requestWriteStart(dbCommon *record, devSnmp_pv *pv, const SnmpValue *payload, bool encodable)
{
  if (!encodable || !pv->epics()->begin(payload)) {
    recGblSetSevr(record, WRITE_ALARM, INVALID_ALARM);
    return -1;
  }
  record->pact = true;
  return 0;
}

static bool requestWriteEntry(dbCommon *record, devSnmp_pv **pv)
{
  *pv = (devSnmp_pv *)record->dpvt;
  /* An active simulation callback can enter device support without a SET.
   * Only the request completion callback may consume a terminal result. */
  return !devSnmpExiting() && *pv && (*pv)->request() &&
      (!record->pact || (*pv)->request()->consuming());
}

static long requestAoWrite(aoRecord *record)
{
  devSnmp_pv *pv;
  if (!requestWriteEntry((dbCommon *)record, &pv)) {
    recGblSetSevr(record, WRITE_ALARM, INVALID_ALARM);
    return -1;
  }
  devSnmp_request *request = pv->request();
  if (record->pact) {
    long value;
    if (request->wireType() == SnmpWireInteger && request->hasNativeLong() && request->nativeLong(&value) &&
        value >= INT_MIN && value <= INT_MAX)
      record->rbv = value;
    request->consumed(request->valid());
    return 0;
  }
  SnmpValue payload(request->capacity());
  bool encodable = false;
  if (request->wireType() == SnmpWireInteger) {
    if (pv->usesRawValue()) {
      payload.signedValue = record->rval;
      encodable = true;
    } else {
      double value = record->oval;
      encodable = isfinite(value) && value == floor(value) && value >= INT32_MIN && value <= INT32_MAX;
      payload.signedValue = encodable ? (long)value : 0;
    }
    payload.kind = SnmpValue::Signed;
  } else if (request->wireType() == SnmpWireFloat) {
    double value = record->oval;
    encodable = isfinite(value) && fabs(value) <= FLT_MAX;
    payload.kind = SnmpValue::Real;
    payload.realValue = value;
  }
  payload.valid = encodable;
  return requestWriteStart((dbCommon *)record, pv, &payload, encodable);
}

static long requestLoWrite(longoutRecord *record)
{
  devSnmp_pv *pv;
  if (!requestWriteEntry((dbCommon *)record, &pv)) {
    recGblSetSevr(record, WRITE_ALARM, INVALID_ALARM);
    return -1;
  }
  devSnmp_request *request = pv->request();
  if (record->pact) {
    request->consumed(request->valid());
    return 0;
  }
  /* OOPT is re-read on every first pass because it can change at run time;
   * record processing publishes the alarm raised here. */
  if (record->oopt != longoutOOPT_Every_Time) {
    pv->epics()->restoreOopt("write");
    recGblSetSevr(record, WRITE_ALARM, INVALID_ALARM);
    return -1;
  }
  SnmpValue payload(request->capacity());
  payload.kind = SnmpValue::Signed;
  payload.signedValue = record->val;
  payload.valid = true;
  return requestWriteStart((dbCommon *)record, pv, &payload, true);
}

static long requestSoWrite(stringoutRecord *record)
{
  devSnmp_pv *pv;
  if (!requestWriteEntry((dbCommon *)record, &pv)) {
    recGblSetSevr(record, WRITE_ALARM, INVALID_ALARM);
    return -1;
  }
  devSnmp_request *request = pv->request();
  if (record->pact) {
    request->consumed(request->valid());
    return 0;
  }
  size_t length = strnlen(record->val, sizeof(record->val));
  SnmpValue payload(request->capacity());
  bool encodable = length <= payload.bytes.size();
  if (encodable) {
    payload.kind = SnmpValue::Octets;
    payload.length = (unsigned)length;
    if (length) memcpy(&payload.bytes[0], record->val, length);
  }
  payload.valid = encodable;
  return requestWriteStart((dbCommon *)record, pv, &payload, encodable);
}

struct RequestDset {
  long number;
  DEVSUPFUN report, init, init_record, get_ioint_info, read, special_linconv;
};
static RequestDset devSnmpRequestAi = {6, NULL, NULL, (DEVSUPFUN)requestAiInit, NULL, (DEVSUPFUN)requestAiRead, NULL};
static RequestDset devSnmpRequestLi = {5, NULL, NULL, (DEVSUPFUN)requestLiInit, NULL, (DEVSUPFUN)requestLiRead, NULL};
static RequestDset devSnmpRequestSi = {5, NULL, NULL, (DEVSUPFUN)requestSiInit, NULL, (DEVSUPFUN)requestSiRead, NULL};
static RequestDset devSnmpRequestAo = {6, NULL, NULL, (DEVSUPFUN)requestAoInit, NULL, (DEVSUPFUN)requestAoWrite, NULL};
static RequestDset devSnmpRequestLo = {5, NULL, NULL, (DEVSUPFUN)requestLoInit, NULL, (DEVSUPFUN)requestLoWrite, NULL};
static RequestDset devSnmpRequestSo = {5, NULL, NULL, (DEVSUPFUN)requestSoInit, NULL, (DEVSUPFUN)requestSoWrite, NULL};
epicsExportAddress(dset, devSnmpRequestAi);
epicsExportAddress(dset, devSnmpRequestLi);
epicsExportAddress(dset, devSnmpRequestSi);
epicsExportAddress(dset, devSnmpRequestAo);
epicsExportAddress(dset, devSnmpRequestLo);
epicsExportAddress(dset, devSnmpRequestSo);
