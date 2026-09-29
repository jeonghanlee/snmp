#include "snmpNative.h"

#include <cfloat>
#include <cmath>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/time.h>

#include <net-snmp/net-snmp-config.h>
#include <net-snmp/net-snmp-includes.h>
#include <net-snmp/library/large_fd_set.h>

static_assert(sizeof(oid) == sizeof(unsigned long), "Native OID elements must match binding storage");

void snmpNativeCopyValue(SnmpValue &result, const variable_list *value)
{
  result.valid = result.hasLong = result.hasDouble = false;
  result.kind = SnmpValue::Empty;
  result.length = 0;
  result.oid.clear();
  if (!value || value->type == SNMP_NOSUCHOBJECT ||
      value->type == SNMP_NOSUCHINSTANCE || value->type == SNMP_ENDOFMIBVIEW) return;
  result.wireType = value->type;
  // The library's float and double printers need a few hundred bytes of room
  // regardless of the printed length, so format into a scratch buffer. A text
  // that does not fit the bounded legacy view yields no value at all here; a
  // request write copies into a result sized above any printed value and
  // applies its own text rule when the slot finishes.
  std::vector<char> scratch(result.text.size() < 1024 ? 1024 : result.text.size());
  int count = snprint_value(&scratch[0], scratch.size(), value->name, value->name_length, value);
  if (count < 0 || static_cast<unsigned>(count) >= result.text.size()) return;
  memcpy(&result.text[0], &scratch[0], count + 1);
  switch (value->type) {
  case ASN_INTEGER:
    if (!value->val.integer) return;
    result.kind = SnmpValue::Signed;
    result.signedValue = *value->val.integer;
    result.hasLong = true;
    break;
  case ASN_COUNTER:
  case ASN_UNSIGNED:
  case ASN_TIMETICKS:
    if (!value->val.integer) return;
    result.kind = SnmpValue::Unsigned;
    result.unsignedValue = static_cast<uint32_t>(*value->val.integer);
    result.hasLong = value->type != ASN_TIMETICKS;
    break;
  case ASN_COUNTER64:
    if (!value->val.counter64) return;
    result.kind = SnmpValue::Unsigned;
    result.unsignedValue = (static_cast<uint64_t>(value->val.counter64->high) << 32) |
                           static_cast<uint32_t>(value->val.counter64->low);
    break;
#ifdef NETSNMP_WITH_OPAQUE_SPECIAL_TYPES
  case ASN_OPAQUE_FLOAT:
    if (!value->val.floatVal) return;
    result.kind = SnmpValue::Real;
    result.realValue = *value->val.floatVal;
    result.hasDouble = true;
    break;
  case ASN_OPAQUE_DOUBLE:
    if (!value->val.doubleVal) return;
    result.kind = SnmpValue::Real;
    result.realValue = *value->val.doubleVal;
    result.hasDouble = true;
    break;
#endif
  case ASN_OBJECT_ID: {
    size_t length = value->val_len / sizeof(oid);
    if (value->val_len % sizeof(oid) || length > result.oid.capacity() ||
        (length && !value->val.objid)) return;
    result.kind = SnmpValue::ObjectId;
    for (size_t i = 0; i < length; ++i) {
      if (value->val.objid[i] > UINT32_MAX) return;
      result.oid.push_back(static_cast<uint32_t>(value->val.objid[i]));
    }
    break;
  }
  case ASN_OCTET_STR:
  case ASN_BIT_STR:
  case ASN_IPADDRESS:
  case ASN_OPAQUE:
    if (value->val_len > result.bytes.size() || (value->val_len && !value->val.string)) return;
    result.kind = SnmpValue::Octets;
    result.length = static_cast<unsigned>(value->val_len);
    if (result.length) memcpy(&result.bytes[0], value->val.string, result.length);
    break;
  }
  result.valid = true;
}

unsigned char snmpNativeWireAsnType(SnmpWireType wireType)
{
  switch (wireType) {
  case SnmpWireInteger: return ASN_INTEGER;
  case SnmpWireOctets: return ASN_OCTET_STR;
#ifdef NETSNMP_WITH_OPAQUE_SPECIAL_TYPES
  case SnmpWireFloat: return ASN_OPAQUE_FLOAT;
#endif
  default: return 0;
  }
}

bool snmpNativeAddSetVariable(snmp_pdu *pdu, const unsigned long *oidValue, size_t oidLength,
                              SnmpWireType wireType, const SnmpValue &payload)
{
  if (!pdu || !oidValue || !oidLength || !payload.valid) return false;
  switch (snmpNativeWireAsnType(wireType)) {
  case ASN_INTEGER: {
    if (payload.kind != SnmpValue::Signed) return false;
    if (payload.signedValue < INT32_MIN || payload.signedValue > INT32_MAX) return false;
    long value = static_cast<long>(payload.signedValue);
    return snmp_pdu_add_variable(pdu, oidValue, oidLength, ASN_INTEGER, &value, sizeof(value)) != NULL;
  }
#ifdef NETSNMP_WITH_OPAQUE_SPECIAL_TYPES
  case ASN_OPAQUE_FLOAT: {
    if (payload.kind != SnmpValue::Real) return false;
    double real = payload.realValue;
    if (!std::isfinite(real) || std::fabs(real) > FLT_MAX) return false;
    float value = real == 0.0 ? 0.0f : static_cast<float>(real);
    return snmp_pdu_add_variable(pdu, oidValue, oidLength, ASN_OPAQUE_FLOAT, &value, sizeof(value)) != NULL;
  }
#endif
  case ASN_OCTET_STR:
    if (payload.kind != SnmpValue::Octets || payload.length > payload.bytes.size()) return false;
    return snmp_pdu_add_variable(pdu, oidValue, oidLength, ASN_OCTET_STR,
                                 payload.length ? &payload.bytes[0] : NULL, payload.length) != NULL;
  }
  return false;
}

bool snmpNativeAuthProtocol(const char *name, std::vector<unsigned long> &protocol)
{
    int type = name ? usm_lookup_auth_type(name) : -1;
    size_t length = 0;
    const oid *found = type < 0 ? NULL : sc_get_auth_oid(type, &length);
    if (!found || !length) return false;
    protocol.assign(found, found + length);
    return true;
}

bool snmpNativePrivProtocol(const char *name, std::vector<unsigned long> &protocol)
{
    int type = name ? usm_lookup_priv_type(name) : -1;
    size_t length = 0;
    const oid *found = type < 0 ? NULL : sc_get_priv_oid(type, &length);
    if (!found || !length) return false;
    protocol.assign(found, found + length);
    return true;
}

bool snmpNativeDeriveKey(const unsigned long *authProtocol, size_t authProtocolLength,
                         const std::string &passphrase, unsigned char *key, size_t *keyLength)
{
    if (!authProtocol || !authProtocolLength || passphrase.empty() || !key || !keyLength) return false;
    return generate_Ku((const oid *)authProtocol, (u_int)authProtocolLength, (const u_char *)passphrase.data(),
                       passphrase.size(), key, keyLength) == SNMPERR_SUCCESS;
}

bool snmpNativeResolveBudget(long &timeoutUs, int &retries)
{
    if (retries == SNMP_DEFAULT_RETRIES) {
        retries = netsnmp_ds_get_int(NETSNMP_DS_LIBRARY_ID, NETSNMP_DS_LIB_RETRIES);
        if (retries < 0) retries = 5;
    }
    if (timeoutUs == SNMP_DEFAULT_TIMEOUT) {
        int seconds = netsnmp_ds_get_int(NETSNMP_DS_LIBRARY_ID, NETSNMP_DS_LIB_TIMEOUT);
        if (seconds <= 0) timeoutUs = 1000000;
        else if (static_cast<uint64_t>(seconds) > static_cast<uint64_t>(LONG_MAX) / 1000000) return false;
        else timeoutUs = static_cast<long>(seconds) * 1000000;
    }
    return timeoutUs > 0 && retries >= 0 && retries < INT_MAX;
}

/* One accepted request, keyed by the request ID that snmp_pdu_create assigns
 * before sending. messageId follows the SNMPv3 message ID of the latest sent
 * attempt, because the library matches received SNMPv3 messages to requests
 * by message ID and reports carry an unrelated request ID. terminal records that the
 * library reported the outcome; later callbacks for the same request are
 * ignored. */
struct SnmpNativeSession::Exchange {
    SnmpIdentity transaction;
    long requestId;
    long messageId;
    bool terminal, write;
    std::vector<std::vector<unsigned long> > oids;
    SnmpNativeResult result;
};

SnmpNativeSession::SnmpNativeSession(Completion target, void *targetContext)
    : completion(target), context(targetContext), handle(0), closing(false), completed(0), sendingId(0)
{
}

SnmpNativeSession::~SnmpNativeSession()
{
    close();
}

bool SnmpNativeSession::open(const snmp_session &settings)
{
    if (handle) {
        lastError = "session already open";
        return false;
    }
    snmp_session copy = settings;
    copy.callback = NULL;
    copy.callback_magic = NULL;
    handle = snmp_sess_open(&copy);
    if (handle) return true;
    char *text = NULL;
    int systemError = 0, libraryError = 0;
    snmp_error(&copy, &systemError, &libraryError, &text);
    lastError = text ? text : "snmp_sess_open failed";
    free(text);
    return false;
}

bool SnmpNativeSession::get(SnmpIdentity transaction, const std::vector<std::vector<unsigned long> > &oids,
                            unsigned capacity)
{
    return transact(transaction, oids, capacity, SnmpWireNone, NULL);
}

bool SnmpNativeSession::transact(SnmpIdentity transaction,
                                const std::vector<std::vector<unsigned long> > &oids,
                                unsigned capacity, SnmpWireType wireType, const SnmpValue *payload, long *wireId)
{
    if (wireId) *wireId = 0;
    if (!handle || closing) {
        lastError = "session not open";
        return false;
    }
    if (!transaction || oids.empty() || !capacity) {
        lastError = "invalid transaction, empty request or zero capacity";
        return false;
    }
    for (std::map<long, Exchange *>::const_iterator i = exchanges.begin(); i != exchanges.end(); ++i) {
        if (i->second->transaction == transaction) {
            lastError = "transaction already pending";
            return false;
        }
    }
    for (size_t i = 0; i < deferred.size(); ++i) {
        if (deferred[i]->transaction == transaction) {
            lastError = "transaction already pending";
            return false;
        }
    }
    if (payload && oids.size() != 1) {
        lastError = "SET requires one binding";
        return false;
    }
    snmp_pdu *pdu = snmp_pdu_create(payload ? SNMP_MSG_SET : SNMP_MSG_GET);
    if (!pdu) {
        lastError = "PDU allocation failed";
        return false;
    }
    if (!pdu->reqid || exchanges.count(pdu->reqid)) {
        snmp_free_pdu(pdu);
        lastError = "request ID unavailable";
        return false;
    }
    for (size_t i = 0; i < oids.size(); ++i) {
        if (oids[i].empty() || (payload
            ? !snmpNativeAddSetVariable(pdu, &oids[i][0], oids[i].size(), wireType, *payload)
            : !snmp_add_null_var(pdu, (const oid *)&oids[i][0], oids[i].size()))) {
            snmp_free_pdu(pdu);
            lastError = "invalid OID";
            return false;
        }
    }
    Exchange *exchange = new Exchange;
    exchange->transaction = transaction;
    exchange->requestId = pdu->reqid;
    exchange->messageId = pdu->msgid;
    exchange->terminal = false;
    exchange->write = payload != NULL;
    exchange->oids = oids;
    exchange->result.outcome = SnmpNativeResult::ProtocolError;
    exchange->result.errorStatus = 0;
    exchange->result.errorIndex = 0;
    exchange->result.resends = 0;
    exchange->result.values.assign(oids.size(), SnmpValue(capacity));
    exchanges[exchange->requestId] = exchange;
    sendingId = exchange->requestId;
    int sent = snmp_sess_async_send(handle, pdu, dispatch, this);
    sendingId = 0;
    if (!sent) {
        recordError();
        exchanges.erase(exchange->requestId);
        delete exchange;
        snmp_free_pdu(pdu);
        return false;
    }
    if (wireId) *wireId = exchange->requestId;
    if (exchange->terminal) {
        exchanges.erase(exchange->requestId);
        deferred.push_back(exchange);
    }
    return true;
}

void SnmpNativeSession::close()
{
    if (!handle) return;
    closing = true;
    snmp_sess_close(handle);
    handle = 0;
    deliverDeferred();
    while (!exchanges.empty()) {
        Exchange *exchange = exchanges.begin()->second;
        exchange->result.outcome = SnmpNativeResult::Closed;
        finish(exchange);
    }
    closing = false;
}

int SnmpNativeSession::service(const std::vector<SnmpNativeSession *> &sessions, double maxWait,
                               int wakeDescriptor)
{
    unsigned long long before = 0;
    for (size_t i = 0; i < sessions.size(); ++i) before += sessions[i]->completed;
    for (size_t i = 0; i < sessions.size(); ++i) sessions[i]->deliverDeferred();
    if (maxWait < 0) maxWait = 0;
    struct timeval wait;
    wait.tv_sec = (time_t)maxWait;
    wait.tv_usec = (suseconds_t)((maxWait - wait.tv_sec) * 1e6);
    netsnmp_large_fd_set descriptors;
    netsnmp_large_fd_set_init(&descriptors, FD_SETSIZE);
    NETSNMP_LARGE_FD_ZERO(&descriptors);
    int count = 0;
    if (wakeDescriptor >= 0) {
        NETSNMP_LARGE_FD_SET(wakeDescriptor, &descriptors);
        count = wakeDescriptor + 1;
    }
    for (size_t i = 0; i < sessions.size(); ++i) {
        SnmpNativeSession *session = sessions[i];
        if (!session->handle) continue;
        int block = 1;
        struct timeval due = {0, 0};
        snmp_sess_select_info2(session->handle, &count, &descriptors, &due, &block);
        if (!block && timercmp(&due, &wait, <)) wait = due;
    }
    int ready = netsnmp_large_fd_set_select(count, &descriptors, NULL, NULL, &wait);
    int status = 0;
    if (ready < 0 && errno != EINTR) status = -1;
    for (size_t i = 0; i < sessions.size() && status == 0; ++i) {
        SnmpNativeSession *session = sessions[i];
        if (!session->handle) continue;
        if (ready > 0) snmp_sess_read2(session->handle, &descriptors);
        if (session->handle) snmp_sess_timeout(session->handle);
    }
    netsnmp_large_fd_set_cleanup(&descriptors);
    if (status) return status;
    unsigned long long after = 0;
    for (size_t i = 0; i < sessions.size(); ++i) after += sessions[i]->completed;
    return (int)(after - before);
}

/* Records the outcome of the first terminal callback for a pending request.
 * RESEND, CONNECT and a received report message are intermediate: the library
 * may recover from a report by retransmitting, as for notInTimeWindow after an
 * agent restart, and for a rejected SNMPv3 request it always delivers
 * SEC_ERROR, before or after the report message depending on the library
 * version. A callback for a request that is not pending, or after its outcome
 * was recorded, is ignored. An outcome reported inside snmp_sess_async_send is
 * left for get() to settle. */
int SnmpNativeSession::dispatch(int operation, snmp_session *, int requestId, snmp_pdu *pdu, void *magic)
{
    SnmpNativeSession *self = static_cast<SnmpNativeSession *>(magic);
    if (!self) return 1;
    Exchange *exchange = self->find(requestId, pdu);
    if (!exchange || exchange->terminal) return 1;
    SnmpNativeResult &result = exchange->result;
    if (operation == NETSNMP_CALLBACK_OP_RESEND) {
        ++result.resends;
        if (pdu) exchange->messageId = pdu->msgid;
        return 1;
    }
    if (operation == NETSNMP_CALLBACK_OP_CONNECT) return 1;
    if (self->closing) {
        result.outcome = SnmpNativeResult::Closed;
    } else if (operation == NETSNMP_CALLBACK_OP_RECEIVED_MESSAGE) {
        if (pdu && pdu->command == SNMP_MSG_RESPONSE) {
            result.outcome = SnmpNativeResult::Response;
            result.errorStatus = pdu->errstat;
            result.errorIndex = pdu->errindex;
            for (size_t i = 0; i < exchange->oids.size(); ++i) {
                const std::vector<unsigned long> &expected = exchange->oids[i];
                const variable_list *matched = NULL;
                unsigned matches = 0;
                if (pdu->errstat == SNMP_ERR_NOERROR) {
                    for (const variable_list *v = pdu->variables; v; v = v->next_variable) {
                        if (!snmp_oid_compare((const oid *)&expected[0], expected.size(), v->name, v->name_length)) {
                            matched = v;
                            ++matches;
                        }
                    }
                }
                bool exact = !exchange->write || (pdu->variables && !pdu->variables->next_variable);
                snmpNativeCopyValue(result.values[i], matches == 1 && exact ? matched : NULL);
            }
        } else if (pdu && pdu->command == SNMP_MSG_REPORT) {
            return 1;
        } else {
            result.outcome = SnmpNativeResult::ProtocolError;
        }
    } else if (operation == NETSNMP_CALLBACK_OP_TIMED_OUT) {
        result.outcome = SnmpNativeResult::Timeout;
    } else if (operation == NETSNMP_CALLBACK_OP_SEND_FAILED) {
        result.outcome = SnmpNativeResult::SendFailed;
    } else if (operation == NETSNMP_CALLBACK_OP_SEC_ERROR) {
        result.outcome = SnmpNativeResult::SecurityError;
    } else if (operation == NETSNMP_CALLBACK_OP_DISCONNECT) {
        result.outcome = SnmpNativeResult::Closed;
    } else {
        result.outcome = SnmpNativeResult::ProtocolError;
    }
    exchange->terminal = true;
    if (exchange->requestId != self->sendingId) self->finish(exchange);
    return 1;
}

/* Finds the pending request the library matched. Callbacks that carry the
 * request's own PDU (RESEND, TIMED_OUT, SEND_FAILED, and failures inside the
 * send) are matched by request ID, because the library may assign a new
 * SNMPv3 message ID to an attempt it then fails to send. Callbacks that carry
 * a received SNMPv3 response or report are matched by the message ID of the
 * latest sent attempt, as the library matches them; its request ID may be
 * zero or foreign. */
SnmpNativeSession::Exchange *SnmpNativeSession::find(long requestId, const snmp_pdu *pdu)
{
    if (pdu && pdu->version == SNMP_VERSION_3 &&
        (pdu->command == SNMP_MSG_RESPONSE || pdu->command == SNMP_MSG_REPORT)) {
        for (std::map<long, Exchange *>::iterator i = exchanges.begin(); i != exchanges.end(); ++i)
            if (i->second->messageId == pdu->msgid) return i->second;
        return NULL;
    }
    std::map<long, Exchange *>::iterator found = exchanges.find(requestId);
    return found == exchanges.end() ? NULL : found->second;
}

void SnmpNativeSession::finish(Exchange *exchange)
{
    exchanges.erase(exchange->requestId);
    ++completed;
    if (completion) completion(context, exchange->transaction, exchange->result);
    delete exchange;
}

/* Delivers outcomes that the library reported inside a send that then
 * succeeded; the library already owns and releases those PDUs. */
void SnmpNativeSession::deliverDeferred()
{
    while (!deferred.empty()) {
        Exchange *exchange = deferred.front();
        deferred.erase(deferred.begin());
        ++completed;
        if (completion) completion(context, exchange->transaction, exchange->result);
        delete exchange;
    }
}

void SnmpNativeSession::recordError()
{
    char *text = NULL;
    int systemError = 0, libraryError = 0;
    if (handle) snmp_sess_error(handle, &systemError, &libraryError, &text);
    lastError = text ? text : "native send failed";
    free(text);
}
