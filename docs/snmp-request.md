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

Lock order is record lock then request mutex for acceptance and consumption.
Network completion uses the request mutex without taking a record lock.
The request worker uses only the request mutex. Trace writes take the trace
mutex inside the request mutex; trace reporting never takes request locks.
Existing legacy networking and record-lock interactions remain in legacy code.

## Diagnostics and shutdown

`snmpr` reports each non-idle request's record, generation, state, and callback
pending flag even when tracing is disabled. The trace holds at most 8192 events;
overflow is reported and invalidates a
complete sequencing audit. Each entry contains monotonic time, record name,
generation, event, and success flag. `accepted`, optional `claimed`, `result`,
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

## Validation boundary

The local validation uses Debian 13, Base 7.0.10, system Net-SNMP, numeric v2c
loopback peers, and real Base/driver/CA paths. APC PDU consumer verification uses
its shipped MIB, loaders, DB, and PVA/CA tests. This does not establish SNMPv3
security behavior, other OS builds, hardware compatibility, long-duration
resource stability, or firmware equivalence. Current evidence and remaining
checks are tracked in [the milestone](milestone-db9ebf5.md).
