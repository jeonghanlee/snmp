#ifndef SNMP_NATIVE_H
#define SNMP_NATIVE_H

#include <map>
#include <string>
#include <vector>
#include "snmpTypes.h"

struct snmp_session;
struct snmp_pdu;
struct variable_list;

/* Copies one native varbind into owned typed storage. The result is valid only
 * for a supported, non-exception type whose value and bounded legacy text fit
 * the storage reserved in result. Native storage is never retained. */
void snmpNativeCopyValue(SnmpValue &result, const variable_list *value);

/* Terminal outcome of one native exchange, valid only during the completion
 * call. Response: the agent answered; errorStatus and errorIndex come from
 * the response PDU, and values holds one entry per requested OID in request
 * order, valid only when errorStatus is zero and exactly one matching varbind
 * of a supported type arrived. Timeout: the library exhausted its retries.
 * SendFailed: the library reported a transport failure after the request
 * was accepted. SecurityError: the library reported a USM failure
 * (SEC_ERROR); a report it recovers from is not an outcome. ProtocolError:
 * another message type or an unknown callback operation. Closed: the session
 * closed first. resends counts the library's RESEND callbacks. */
struct SnmpNativeResult {
    enum Outcome { Response, Timeout, SendFailed, SecurityError, ProtocolError, Closed };
    Outcome outcome;
    long errorStatus;
    long errorIndex;
    unsigned resends;
    std::vector<SnmpValue> values;
};

/* Owner of one Net-SNMP Single Session handle and of the state of every
 * request sent through it. Only the documented snmp_sess_* family and its
 * large descriptor-set variants service the handle; the traditional global
 * session list is never used. Wire retransmission, discovery and USM state
 * remain library behavior: the adapter sends each accepted request once and
 * reports the library's first terminal callback for it.
 *
 * Threading: one owner thread calls every member and service(). The Net-SNMP
 * library must already be initialized in the process (init_snmp); in the IOC
 * the record transport does this when devSnmp starts.
 *
 * Lifetimes: open() copies what it needs from settings. context must outlive
 * the session. The handle is released by close() or the destructor. The
 * library owns and frees each accepted PDU; get() frees a rejected one. The
 * per-request state is released right after its completion, and close()
 * releases whatever is still pending.
 *
 * Requests: the caller supplies a nonzero transaction identity and never
 * reuses one within the process. get() returns true when the request was
 * accepted; exactly one completion then follows. get() returns false with
 * error() set and no completion when the request was rejected, including a
 * send that the library failed immediately; the PDU is then freed here.
 *
 * Completions run on the owner thread inside service() or close(), never
 * inside get(). A completion may call get() on any session but must not close
 * or destroy a session. Requests still pending at close() complete as
 * Closed, whether the library reports them while closing or not. */
class SnmpNativeSession {
public:
    typedef void (*Completion)(void *context, SnmpIdentity transaction, const SnmpNativeResult &result);

    SnmpNativeSession(Completion completion, void *context);
    ~SnmpNativeSession();

    bool open(const snmp_session &settings);
    bool get(SnmpIdentity transaction, const std::vector<std::vector<unsigned long> > &oids, unsigned capacity);
    void close();
    bool isOpen() const { return handle != 0; }
    size_t pending() const { return exchanges.size() + deferred.size(); }
    unsigned long long completions() const { return completed; }
    const std::string &error() const { return lastError; }

    /* Delivers any completion held from get(), then waits at most maxWait
     * seconds (negative means zero), less when a library retransmission or
     * timeout is due, reads ready sockets and runs library timeouts for every
     * open session in sessions. EINTR ends the wait early and still runs the
     * timeouts. Returns the number of completions delivered, or -1 when the
     * wait failed, in which case no session was read. The wait watches only
     * session sockets; nothing else can end it early, so an owner with other
     * work bounds its latency through maxWait. The worker wake path belongs
     * to the worker loop design. */
    static int service(const std::vector<SnmpNativeSession *> &sessions, double maxWait);

private:
    struct Exchange;

    SnmpNativeSession(const SnmpNativeSession &);
    SnmpNativeSession &operator=(const SnmpNativeSession &);

    static int dispatch(int operation, snmp_session *session, int requestId, snmp_pdu *pdu, void *magic);
    Exchange *find(long requestId, const snmp_pdu *pdu);
    void finish(Exchange *exchange);
    void deliverDeferred();
    void recordError();

    Completion completion;
    void *context;
    void *handle;
    bool closing;
    unsigned long long completed;
    long sendingId;
    std::map<long, Exchange *> exchanges;
    std::vector<Exchange *> deferred;
    std::string lastError;
};

#endif
