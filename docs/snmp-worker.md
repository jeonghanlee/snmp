# SNMP Worker Runtime

## Scope

This opt-in Linux runtime executes SnmpRequest and legacy Snmp GETs and SETs in child
processes. Each configured address has one persistent worker; bindings at
that address serialize their native transactions. Different addresses have
independent Net-SNMP state and transport progress deadlines.

Legacy polling, native text formatting, output readback suppression and queued
SET replacement use the same worker transport as request records. An IOC that
does not select workers retains its existing transport. Selecting workers
does not fall back to parent-side native operations. Hardware and final
platform/resource qualification are separate from implementation; current
status is recorded in [the milestone document](milestone-db9ebf5.md).

## Startup

Build and retain the module, its `snmpWorker` executable and the consumer IOC
as one identified set. The helper is built under `bin/<arch>/`; select its
absolute path explicitly. Its runtime libraries must also be available.
Rebuild the consumer's DBD registration against the matching module.

After loading the expanded consumer DBD and calling its registration function,
load the shipped startup file before any other devSnmp command:

```text
iocshLoad("$(SNMP)/examples/request-worker.iocsh", "SNMP_WORKER=$(SNMP_WORKER)")
```

Set `SNMP` to the module root and `SNMP_WORKER` to the absolute helper path.
The optional loader macro `SNMP_MAX_WORKERS` defaults to 32. Direct setup is
`devSnmpConfigureWorkers("/absolute/path/to/snmpWorker", 32)`; select one
setup form and call it once. Relative paths, repeated setup and setup after
module initialization are rejected.

For v3, load a named profile with `devSnmpLoadV3Profile`, define the address
with `devSnmpDefineEndpoint`, set endpoint parameters, and bind records using
`endpoint:name` and the literal `-` community placeholder. The profile and
engine grammar remains in [the architecture](snmp-architecture.md).
Existing v3 host setters/files and v1/v2c host/version/community links are also
supported. Load records after their configuration, then call `iocInit`.

Local binding resolves the OID, security algorithms and key material inside
the worker. Startup does not require discovery or a responding agent.
The log reports a binding ID, child PID, epoch and effective `progressMSec`.
A missing helper, build mismatch, invalid OID or invalid native security
configuration fails the affected binding. Check startup errors and actual
record alarms; IOC process exit zero is not binding acceptance.

## Configuration Boundaries

Configure startup settings before loading their records. Binding occurs during
record initialization inside `iocInit`; the security/native configuration
freeze occurs at `initHookAfterIocBuilt`, the end of `iocBuild`. Request
parameters have a separate lock at `initHookAtEnd`, when `iocRun` completes.
Normal `iocInit` performs both phases. The earlier binding boundary still
applies inside the initialization interval.

| Setting or command | Last allowed change |
| --- | --- |
| `devSnmpConfigureWorkers`: executable and process count | Before any module initialization command |
| `devSnmpSetParam`: `WorkerProgressLimitMSec` | Before profile or record initialization locks worker startup |
| `devSnmpLoadV3Profile`: profile and credential files | Before final freeze; a profile name cannot be redefined |
| `devSnmpDefineEndpoint`: address and profile | Before final freeze; an endpoint name cannot be redefined |
| `devSnmpSetEndpointParam`: timeout, retries, batch, context and engine IDs | Before the affected endpoint binds, and before final freeze |
| Legacy version, v3 parameter/file and batch setters | Before the affected host binds, and before final freeze |
| `devSnmpSetParam`: `SessionTimeout`, `SessionRetries`, `CheckRanges` | Before any host binds, and before final freeze |
| `devSnmpSetParam`: `RequestTimeoutMSec`, `RequestTrace` | Before request startup at `initHookAtEnd`; still accepted between `iocBuild` and `iocRun` |
| `devSnmpSetQueueSize`: per-address pending count | Before or after `iocInit`, until shutdown |
| Polling controls, `DebugLevel`, debug command and reports | Remain live |

Legacy aliases `epicsSnmpSetSnmpVersion` and `epicsSnmpSetMaxOidsPerReq`
have the same boundary as their `devSnmp` commands. Live polling controls are
`DataStaleTimeoutMSec`, `MaxOidCompFailures`, `MaxTopPollWeight`,
`DoNotPollWeight`, `PassivePollMSec`, `SetSkipReadbackMSec`,
`ReadStarvationMSec` and `ThreadSleepMSec`. They do not replace the native
security or transport snapshot. Changing an environment variable alone does
not call a setter.

A rejected change to an already bound configuration preserves that
configuration. Unknown generic parameters return an error. Setter errors
reach IOC shell `on error break`; a printed error must not be interpreted as
successful configuration. Invalid unbound startup settings continue to fail
binding explicitly.

The parent retains validated security and transport values. Helper recovery
uses that snapshot without reopening named profile, credential or legacy v3
files. Editing, deleting, restricting permissions or corrupting those files
does not activate new credentials in the running IOC. A complete IOC process
stop and restart validates and activates the new files; invalid new files
fail without falling back to the previous process's credentials.

## Admission And Sessions

Each address has one FIFO for request GET/SET and legacy polling/SET. Admission
order is dispatch order across those classes. Only contiguous compatible GETs
can share a transaction; a SET or a different session configuration ends a
batch. Shared OIDs occupy one native varbind while each request retains its
own result capacity, generation and deadline. `maxOidsPerReq` and both IPC
frame directions bound each batch.

The default count limit is 1024 pending commands per worker, excluding its
active native transaction. `devSnmpSetQueueSize(address, count)` selects a
positive integer up to 2147483647 for one configured address; other address
workers retain their limits. Use the exact address from the record link or
named endpoint, including any transport prefix and port, not the endpoint name.
Set it after command registration and before `iocInit()` in `st.cmd`:

```iocsh
epicsEnvSet("SNMP_QUEUE_SIZE", "1024")
devSnmpSetQueueSize("$(SNMP_HOST)", $(SNMP_QUEUE_SIZE))
```

`SNMP_HOST` must already identify the target address in the startup script.
Repeat the command with another address and count for another device.
The same `devSnmpSetQueueSize` command also applies after `iocInit()`. Increasing
the limit allows new admissions immediately. Decreasing it preserves every
queued ticket, FIFO position and deadline; new tickets are rejected while
the count is at or above the new limit. An existing queued legacy SET may
still replace its value without adding a ticket. Zero and negative values
are rejected without changing the limit. Changes during shutdown are rejected.
An empty, whitespace-containing or longer-than-255-character address is rejected.
After IOC startup, an address without a configured worker is also rejected.
`snmpr(0)` prints `pending_limit` and the address for each worker. Changing the environment
variable alone does not resize queues: invoke the setter to apply its value.
Live changes are not persisted; IOC restart uses `st.cmd` or the default.
Credential and endpoint configuration freeze rules are unchanged.

The separate 1 MiB charged-data limit remains fixed. Each command is charged its
encoded payload plus 40 bytes: one 32-byte frame header, member count and
length field. This reserves a complete single-command transaction even when
later batching shares framing. Byte accounting does not represent total
process RSS. Request admission failure completes once with READ/INVALID or
WRITE/INVALID, subject to Base alarm priority. Legacy write admission failure
returns a write error; a rejected legacy poll remains eligible for a later poll.

A pending legacy SET to the same OID replaces its value at the existing FIFO
position. Request SETs never coalesce. The supervisor removes expired queued
requests without transmission and resolves the matching generation's timeout
after releasing the queue lock, even while the completion thread is delayed.
Admission counts retained tickets until dispatch or the supervisor expiry pass
removes them. An expired active request completes at its record
deadline while its native transaction continues to own the worker; a later
request cannot bypass that transaction or receive its result.

Compatible bindings share a persistent native session. Address, protocol,
community or profile/security configuration, context, engine IDs and native
timeout/retries must match. Record capacity, OID and operation do not determine
session ownership. Native terminal transport/security failure closes the
session outside the callback; a later command opens a new session. Native
discovery, timeliness handling and retransmission remain Net-SNMP operations.
An explicit security engine ID stays fixed across recovery.

Legacy replies retain positional OID comparison after the response-count
check. Repeated mismatches beyond `MaxOidCompFailures` invalidate the cached
reading. A missing variable instead permits an immediate poll without
incrementing that counter. A valid matching reply resets the counter and
restores the cache. Request records retain independent unique-OID matching.

## Deadlines And Recovery

`RequestTimeoutMSec` governs the record's acquisition deadline. It remains
independent of a native transaction that is still running in its worker.
Result application, FLNK and PACT behavior retain the request contract.

The worker watchdog uses the effective native timeout/retries and the
[watchdog policy](decisions/ADR-20260923-worker-watchdog-policy.md). With module
defaults of 10 seconds and five retries, its value is 150000 ms. The native
`-1` sentinels are resolved inside the helper before admission; they are not
the same as the module defaults. An address shared by multiple bindings uses
the greatest required budget. The watchdog starts once before IPC transaction
delivery and is not renewed by partial frames or record deadline expiry.

An optional positive integer `WorkerProgressLimitMSec` override must be set
after worker selection and before profile or record initialization. Every
affected binding must fit the override; undersized values fail admission
without shortening native timeout or retry settings. Omit the override to
use the calculated value.

On invalid IPC, EOF, child loss or watchdog expiry, the supervisor fails the
active record once and retires the worker. Subsequent work uses a replacement
worker and a new epoch after a restart delay of one second, doubling to at
most 30 seconds after repeated failures. Restart uses the parent's startup
snapshot, including credentials; editing a credential file does not change
that snapshot. A full IOC stop/start is required to load changed credentials.

An already delivered SET has an unknown device outcome after worker loss.
The module never replays it. Read the device state before issuing a new
operator command. Native retries within a live transaction remain Net-SNMP
behavior, distinct from a new module transaction.

Shutdown requests STOP, allows two seconds, then applies SIGTERM for 500 ms
and SIGKILL with a final 500 ms reap wait. Linux parent-death handling also
terminates a helper blocked in a native call when its IOC dies. Incomplete
reaping is reported as incomplete shutdown.

## Diagnostics And Reproduction

`snmpr` reports worker PID, epoch, state, binding count and watchdog budget.
`SNMPQUEUE` reports pending command/byte counts, their high-water values and
admission rejections. Repeated reports contain the same trace history;
sequence numbers identify events across those reports.
Enable `RequestTrace=1` before loading records when transaction correlation is
needed. Parent `dispatch` records IPC ownership transfer with `wire=0`.
Child `SNMPWIRE` entries correlate the parent transaction ID and worker epoch
with the actual native application request ID. Neither identifier is a device
identity or a substitute for the record generation. Trace output contains no
credential or value payload. The parent trace is bounded; the child emits
one diagnostic line per attempted application transaction while tracing is on.

Run the [worker tests](../tests/README.md#worker-process-boundary) against an
isolated build. Preserve the build manifest, source and helper/module hashes,
actual startup files, IOC logs, UDP observations and result files together.
Use the scheduler, legacy-set and batch suites with the explicit matching
helper for mixed traffic, queue count and batching checks. The worker suite
also tests warm session reuse and engine recovery. These suites do not qualify
hardware, production timing or a one-hour resource soak. Current record SET
payloads reach the count limit before the 1 MiB byte limit; byte-bound
qualification remains a separate acceptance item.
