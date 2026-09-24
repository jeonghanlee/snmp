# Request-driven SNMP inputs

`DTYP="SnmpRequest"` binds `ai`, `longin`, and `stringin` to an asynchronous
acquisition initiated by record processing. The existing `Snmp` DTYP remains
the default compatibility path. Waveform and output records retain `Snmp`;
this mode does not implement asynchronous SET or a fanout completion barrier.

## Configuration

Use the existing INST_IO input format: host, community, numeric or symbolic
OID, response mask, buffer length, and optional flags. Buffer length must be
2 through 65536 bytes. Load `devSnmp.dbd` through the consumer's generated
registration function; rebuild the consumer against this module.

```text
record(ai, "$(P)Current") {
    field(DESC, "Current readback")
    field(DTYP, "SnmpRequest")
    field(INP, "@$(HOST) $(COMM) $(OID) INTEGER: 128 sR")
    field(SCAN, "Passive")
    field(LINR, "SLOPE")
    field(ESLO, "0.1")
    field(FLNK, "$(P)CurrentCheck")
}
```

Passive records require a processing source such as a periodic trigger and
fanout, a local FLNK, or a CA PROC put. PINI follows Base processing rules.
I/O Intr is rejected during initialization. Change DTYP, INP, or protocol
identity by restarting with a matching DB/DBD and binary; live rebinding is
not implemented.

### Delivered example and registration

The runnable [input example](../examples/request-inputs.db) contains one
request input of each supported type, a string FLNK consumer and a legacy
cached input. The [loader](../examples/request-inputs.iocsh) selects v2c and
loads that exact DB. Its default numeric OIDs and public community belong to
the loopback test peer; supply the device's HOST, COMM and OID macros for a
real application. Set SNMP to this module's complete source/build root.

After loading the consumer's expanded DBD and calling its generated
registration function, before iocInit:

```text
iocshLoad("$(SNMP)/examples/request-inputs.iocsh", "SNMP=$(SNMP),P=EXAMPLE:,HOST=$(HOST)")
iocInit
```

Process Analog, Integer or Text through their PROC fields to acquire a sample.
Legacy scans independently. The optional AI_OID, LI_OID, SI_OID and LEGACY_OID
loader macros replace the four numeric OIDs; masks remain INTEGER:/STRING:.
This example uses Base records only and runs in the production snmp IOC.

Add devSnmp.dbd to the consumer's DBD inputs, link devSnmp, and regenerate
the expanded DBD and registerRecordDeviceDriver source together. The three
new dsets use existing Base record types and do not require DBDINC entries.
An old executable with a new DBD cannot resolve the new device support;
an old DBD rejects SnmpRequest even with a new executable. Treat either
startup error as a rejected configuration. IOC exit zero alone does not
prove that all records initialized successfully.

The selected operational rollback uses commit
30d8b81fb10ff1940d9ff29d46d6954679a1f5ba with legacy Snmp DB/startup.
Restore that pair's library, executable, expanded DBD/registration and startup
together. This module supports SnmpRequest, but the selected rollback runs
legacy records. The original db9ebf5 archive remains the historical comparison
baseline, not the operational rollback; it cannot load SnmpRequest records.
The test matrix retains each role separately in artifact-pairs.json, with
build, binary, DBD, DB and executed startup identities.

Configure these parameters before `iocInit`:

| Parameter | Default | Accepted values | Meaning |
| --- | --- | --- | --- |
| `RequestTimeoutMSec` | 10000 | 1 through 3600000 | Monotonic acquisition deadline from acceptance, including queue wait. |
| `RequestTrace` | 0 | 0 or 1 | Enable the bounded diagnostic trace printed by `snmpr`. |

The existing `SessionTimeout`, `SessionRetries`, host protocol configuration,
and maximum OIDs per request remain transport controls. The acquisition
deadline does not cancel an already started Net-SNMP session. Old responses
cannot satisfy a later request. Callback queue or DB lock contention can delay
EPICS completion after the acquisition deadline; this is not a hard real-time
completion guarantee. Site timing acceptance requires device measurements.
SessionTimeout is measured in microseconds; RequestTimeoutMSec is measured in
milliseconds. Invalid or post-iocInit request parameter changes are rejected
and leave the prior value unchanged. PassivePollMSec affects legacy polling;
it does not schedule an idle SnmpRequest record.
Deadline checks use the absolute monotonic timestamp under the request mutex
when inspecting queued work, claiming it, accepting a reply and servicing the
request. A reply received after expiry fails even if the completion worker has
not run. Once a terminal result is ready, callback delay cannot change it.

## Ownership and ordering

Each registered input owns one preallocated request slot and result buffer.
An initial device-support call accepts one generation and sets PACT. The send
worker claims compatible queued requests when constructing a session. Waiters
for the same OID share that read; a waiter accepted after membership is frozen
waits for another session. Expired, unclaimed requests are excluded from GETs.
Existing endpoint/community grouping and per-host serialization are retained.
Pending requests are selected first using a rotating OID cursor. Remaining
packet capacity may serve legacy polling; request readiness does not depend on
the legacy poll-period bin's current tail.

The shared native-session lock protects nonblocking readiness checks and
Net-SNMP operations. Waiting for the next receive poll occurs outside that
lock, so an unanswered UDP read does not hold it until the session timeout.
This does not isolate blocking native session opening or SNMPv3 discovery;
the separate worker architecture addresses that boundary.

The network callback finds each expected OID by identity and accepts exactly
one matching varbind. Missing, duplicate, exception, and PDU-error results
terminate the corresponding acquisition as an error. A private buffer retains
the response until EPICS consumes it; unrelated legacy cache updates cannot
complete an idle or waiting request record.

The `snmpComplete` worker checks deadlines and retries rejected Base callback
queue insertions every 10 ms without taking a network or record lock. The
accepted callback takes the record lock, invokes record support, and consumes
the result once. Device support supplies VAL or RVAL and reports success or
READ/INVALID; Base performs conversion, alarm/monitor handling, FLNK, and PACT
clear. A failed acquisition preserves the previous value. Successful unchanged
values still complete and execute FLNK.

Ordinary periodic processing while PACT is set does not create concurrent
acquisitions. CA PROC puts follow Base RPRO behavior and can request one later
processing pass. A local FLNK chain waits for each source completion; fanout
submissions do not wait for all acquisitions. Conversion masks and flags retain
legacy semantics, including quoted STRING representation and `sR` scaling.

### Known Base callback admission limitation

The observed Debian 12 EPICS Base 7.0.10 build can reject callback requests
after its queue has emptied because its overflow flag remains set. Actual
two-entry queue tests left terminal results Ready while callback retries
continued. In this condition, an SNMP response or acquisition timeout does
not guarantee record completion: PACT can remain set and FLNK may not run.
The module's retry worker and the planned transport-worker watchdog do not
repair this Base-side condition.

Use `snmpr` together with record PACT and downstream completion observations.
A Ready result with `terminal_ns` set, increasing `callback_retries`, and no
new application/completion identifies rejected callback admission; those
diagnostics alone do not prove the internal overflow-flag interleaving.
Retained VAL and last-valid diagnostics do not establish a new completed
sample. Passing runs on other platforms do not establish immunity, and the
failure rate at production queue sizes has not been measured.

Base repair is deferred. Local development continues under the documented
exception in the [Base callback limitation decision](decisions/ADR-20260924-base-callback-limitation.md).
Failed pressure tests remain failed; production acceptance and any dependency
correction require their own verification.

Lock order is record lock then request mutex for acceptance and consumption.
Network completion uses the request mutex without taking a record lock.
The request worker uses only the request mutex. Trace writes take the trace
mutex inside the request mutex; trace reporting never takes request locks.
Existing legacy networking and record-lock interactions remain in legacy code.

## Diagnostics and shutdown

`snmpr` prints a `SNMPDIAG` snapshot for every request record, followed by
`SNMPDIAG_TOTAL`. These diagnostics work with tracing disabled and retain only
bounded per-record state. Each record snapshot is copied under its request
mutex; totals combine sequential snapshots and are not a globally atomic view.

| Fields | Definition |
| --- | --- |
| `generation`, `state`, `callback`, `stopping` | Current generation, lifecycle state, callback ownership and shutdown admission state. State can be idle while its finishing callback still owns the record lock. |
| `accepted`, `rejected` | Accepted generations and rejected device-support admission attempts. Base coalescing of active PROC puts is not an admission attempt or a rejection here. |
| `valid`, `failed` | Successful and failed device-support consumptions. A decoded transport reply is not counted until mask/type/buffer conversion and device-support application succeed. |
| `completed` | Record-support calls that returned through the owned completion callback. |
| `callback_retries` | Rejected calls to the real Base callback queue, retried by the completion worker. This differs from Base's overflow-event counter. |
| `last_valid_generation`, `last_valid_ns`, `last_valid_age_ms` | Last successful device-support consumption and its current monotonic age; errors preserve these values. No success is represented by generation/time zero and age -1. |
| `accepted_ns`, `claimed_ns`, `dispatched_ns`, `terminal_ns`, `applied_ns`, `completed_ns` | Current-generation monotonic timestamps. Zero means that phase has not occurred. Claim selects session membership; dispatch is the native send attempt, not proof of transmission. |
| `queue_age_ms` | Time since acceptance while queued; zero in other states. |
| `queue_ms`, `network_ms` | Acceptance to dispatch and dispatch to terminal result. Queue time includes native session opening. |
| `callback_ms`, `processing_ms`, `total_ms` | Terminal result to application, application to record-support return, and acceptance to return. |
| Totals `records`, `queued`, `active` | Registered request records, queued states, and non-idle states or outstanding callbacks. Remaining totals sum their corresponding per-record counters. |

Latencies are -1 until both endpoints exist. At FLNK, device-support
application has occurred but `completed_ns` is still zero. `valid` measures
acquisition and device-support conversion; it does not assert that Base's
configured value alarms have zero severity. Base ai conversion and final alarm
handling follow application, so observe final VAL/SEVR through a downstream
record when needed. Shutdown abandonment does not increment valid/failed or
completed counters. All counters and timestamps are unsigned 64-bit values.

The trace holds at most 8192 events;
overflow is reported and invalidates a
complete sequencing audit. Each entry contains monotonic time, record name,
generation, event, success flag, transaction ID, native request ID and OID.
`accepted`, optional `claimed` and `dispatch`, `result`,
`applied`, and `complete` describe one request. `claimed` is session membership
selection, not proof of wire transmission. `applied` marks device-support
consumption before Base conversion and final alarm handling; FLNK audit records
are needed to observe the final record value/alarm. `complete` is recorded after
record support returns and reports whether PACT cleared.

The Base `initHookAtShutdown` hook starts module cleanup before Base stops its
callback queues. Graceful exit prevents new requests, stops the completion worker, drains its
queued callbacks, and stops network workers before deleting storage. Pending
acquisitions are abandoned during IOC shutdown without a synthetic FLNK.
If a worker or callback cannot stop within its shutdown wait, storage is retained
until process exit and `shutdown incomplete` is reported. This is a failure to
drain, not successful cleanup. Both explicit IOC exit and stdin EOF invoke Base
cleanup. Process kill does not establish graceful cleanup.
The log reports request shutdown entry, completion-worker exit, drained request
callbacks, stopped network workers and final storage cleanup separately.

## Validation boundary

The public matrix executes real Base/driver/CA paths with numeric loopback
fault peers and native snmpd. Native coverage includes v1, v2c and v3
noAuthNoPriv, authNoPriv and authPriv with the declared SHA/AES test settings,
plus writable SET and independent readback. This does not qualify other
security algorithms or the future helper/profile API. Registration tests run
the delivered example in both production and test IOCs and reject invalid
record/parameter and mismatched binary/DBD configurations.

Platform identities and complete observed results are recorded in
[the milestone](milestone-db9ebf5.md), separately from this executable test
contract. APC consumer, hardware, long-duration resources and firmware
equivalence retain their own acceptance conditions.
