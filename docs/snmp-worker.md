# SNMP Worker Runtime

## Scope

This opt-in Linux runtime executes SnmpRequest GETs and SETs in child
processes. Each configured address has one persistent worker; bindings at
that address serialize their native transactions. Different addresses have
independent Net-SNMP state and transport progress deadlines.

Legacy Snmp records, waveform records, legacy v3 host configuration, batching,
bounded queue admission and the final mixed-operation runtime remain outside
this implementation stage. An IOC that does not select workers retains its
existing transport. Selecting workers rejects unsupported legacy bindings;
it does not fall back to parent-side native operations. Qualification status
is recorded in [the milestone document](milestone-db9ebf5.md).

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
For v1/v2c, existing host/version and community link settings are supported.
Load only supported SnmpRequest records, then call `iocInit`.

Local binding resolves the OID, security algorithms and key material inside
the worker. Startup does not require discovery or a responding agent.
The log reports a binding ID, child PID, epoch and effective `progressMSec`.
A missing helper, build mismatch, invalid OID or invalid native security
configuration fails the affected binding. Check startup errors and actual
record alarms; IOC process exit zero is not binding acceptance.

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
The worker suite does not qualify hardware, mixed legacy traffic, bounded
queue capacity, batching or production timing.
