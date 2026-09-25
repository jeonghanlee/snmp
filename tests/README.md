# Real IOC Tests

## Scope

The runner executes the built SNMP module through real EPICS record processing,
CA clients and UDP. It uses an external controllable peer for faults and a
real Net-SNMP snmpd for native protocol, USM, GET and SET coverage. Test-only
FLNK audit support belongs to `snmpRequestTest`, not the production IOC.

Hardware, production operation, the future worker/profile architecture and
extended pressure/resource acceptance are outside these suites. Their
acceptance requirements and observed results remain in
[the canonical milestone document](../docs/milestone-db9ebf5.md).

## Build Independent Inputs

Requirements: Linux, Python 3, make, a C++11 compiler, Net-SNMP development
files, and an installed EPICS Base. The published profiles declare Base 7.0.10
and native Net-SNMP versions 5.8, 5.9.1, 5.9.3 or 5.9.4.pre2. A declaration is
not proof that every matrix cell passed on that platform. The protocol suite
also requires the actual `snmpd` and `snmpget` programs in PATH.

Run these commands from this Git checkout. Set `SNMP_TEST_BASE` to the actual
Base installation and choose new output paths; the build tool refuses to
reuse an existing output directory.

```bash
export SNMP_TEST_BASE=/absolute/path/to/base
export PATH="$SNMP_TEST_BASE/bin/linux-x86_64:$PATH"
SNMP_TEST_BUILD=/tmp/snmp-candidate
python3 tests/build_fixture.py --base "$SNMP_TEST_BASE" --output "$SNMP_TEST_BUILD"
SNMP_TEST_IOC="$SNMP_TEST_BUILD/bin/linux-x86_64/snmpRequestTest"
```

`build_fixture.py` copies the current tracked and untracked, nonignored source,
records its hashes, and builds that independent copy. It sets the selected
Base through RELEASE.local, keeps INSTALL_LOCATION unset, and records build
configuration, logs, binary/library/DBD hashes and source provenance in
`build-inputs.json`. The installed dependency tree is a read-only input.

Create the unmodified legacy baseline separately:

```bash
SNMP_BASELINE=/tmp/snmp-baseline
python3 tests/build_fixture.py --base "$SNMP_TEST_BASE" --output "$SNMP_BASELINE" --revision db9ebf5
```

This archives `db9ebf51bc81d6f63d9395513d94d60b3b7eda83`; its IOC is
`$SNMP_BASELINE/bin/linux-x86_64/snmp`. Run the tests from this checkout for
both executables so they consume the same delivered DB and peer definitions.
The baseline does not provide SnmpRequest or request trace support.

## Execute

### Complete platform matrix

Run the same matrix once on each declared Linux platform with the selected
Base clients, native tools and development packages in PATH:

```bash
SNMP_MATRIX_OUTPUT=/absolute/path/to/new-matrix-directory
python3 tests/run_matrix.py --base "$SNMP_TEST_BASE" --output "$SNMP_MATRIX_OUTPUT"
```

The output directory must not already exist. This command builds the exact
working source, an ASan candidate, the original db9ebf5 comparison baseline,
the selected operational rollback commit
30d8b81fb10ff1940d9ff29d46d6954679a1f5ba, and the committed pre-deadline-fix
source. It runs all suites at their full default
counts, both native acquisition modes, actual legacy and waveform comparisons,
registration/examples, observer/provenance negative controls and the two real
deadline regressions on the defective build. Expected failures must contain
their intended assertion; an infrastructure error does not satisfy them.
ASan runs native protocol, failures, full teardown, legacy and waveform tests.
The selected waveform and rollback terminal subcases complement the complete
candidate suites; their individual result files remain marked partial.

Operational rollback uses its production snmp executable with legacy Snmp
DB/startup. Its legacy equivalence, waveform, native protocol and EOF/explicit
terminal tests are required acceptance steps. The original baseline remains
required for legacy/waveform comparison and the registration mismatch tests.
Its native protocol suite is a historical observation with
acceptance_required=false: each real failure and exit code remains recorded,
but it does not qualify or reject the selected operational rollback. No other
step is exempt from acceptance. matrix.json's passed field covers required
steps; all_steps_passed includes the historical observation and
historical_failures names any failing observation. A successful matrix with
historical_failures does not mean every executed test passed.

matrix.json records each command, result, log hash and actual OS/compiler/
native/crypto identity. artifact-pairs.json locates the complete isolated build
trees, binary/library/DBD hashes, database inputs and actual startup files.
Keep those trees and evidence together for review and rollback reproduction.
Candidate startup uses the shipped example; operational rollback and historical
comparison use the actual legacy fixtures. artifact-pairs.json identifies
candidate, operational_rollback, historical_comparator and sanitized_candidate
roles separately. Only the original comparison baseline lacks SnmpRequest
support; the selected rollback intentionally uses legacy DB/startup. No package install,
deployment, tag or publication is performed by this command.

For containers, mount source and dependency inputs read-only and a new owned
output directory read-write; run as the source owner. Use an immutable image
ID, private PID namespace and loopback-only networking. Supply --image-id with
that ID and retain the actual container invocation/inspection separately.
The two scheduling faults require ptrace of owned child threads; use only the
necessary container capability, without host PID access. Missing snmpd or
snmpget, denied tracing and sanitizer failures leave the matrix failed.

### Known Base callback limitation

Actual two-entry queue tests on the recorded Debian 12 Base 7.0.10 build
demonstrated rejected callback admission after the ring became empty. Terminal
SNMP results can remain Ready with increasing callback retries, PACT set and
missing FLNK completion. The controlled reproduction and earlier natural
failures remain distinct: the earlier failures did not capture the internal
overflow flag. Passing repeats or other-platform runs do not prove immunity.
Production-size failure frequency has not been measured.

The pressure assertion remains required. A failed pressure test still makes
the matrix's `passed` false and returns exit 1; there is no automatic timeout
waiver. The [Base callback limitation decision](../docs/decisions/ADR-20260924-base-callback-limitation.md)
permits a manually reviewed, explicitly recorded local development exception
for this identified limitation after every remaining required check runs.
Inspect actual trace, diagnostics and failure context before applying that
exception. Unrelated failures still block acceptance. Do not enlarge the
queue, relax assertions or relabel a failure to obtain a passing result.
This exception neither verifies a Base correction nor authorizes production
operation. Preserve the failed evidence and state the exception in the handoff.

### Individual suites

```bash
python3 tests/run_snmp.py --ioc "$SNMP_TEST_IOC" --profile tests/profiles/loopback.json --suite legacy
python3 tests/run_snmp.py --ioc "$SNMP_TEST_IOC" --profile tests/profiles/loopback.json --suite sequencing
python3 tests/run_snmp.py --ioc "$SNMP_TEST_IOC" --profile tests/profiles/loopback.json --suite failures
python3 tests/run_snmp.py --ioc "$SNMP_TEST_IOC" --profile tests/profiles/snmpv3.json --suite protocol
```

Use the baseline executable for its legacy run. For its protocol run, also
pass `--dtyp Snmp`. The protocol candidate uses `--dtyp SnmpRequest` by default;
output records use legacy Snmp in both. For candidate legacy equivalence, pass
`--baseline-evidence <successful-baseline-run-directory>` to the legacy command.
The comparison requires an unmodified git-archive build of the exact baseline
commit above, consistent build/runtime executable, DBD and loaded-library
identities, and the same profile and fixture/observer hashes. A candidate run
passed as `--baseline-evidence` fails explicitly on provenance. It compares
all captured values, raw values, activity and alarms except timeout input
STAT/SEVR, whose active-scan alarm transition depends on Base scan timing.
`baseline-comparison.json` preserves both inputs and the exact exclusion.
Version configuration uses the existing
API's exact SNMP_VERSION_1, SNMP_VERSION_2c and SNMP_VERSION_3 tokens.

Every invocation needs a successful build manifest. The runner verifies the
actual IOC executable, DBD, loaded module, selected Base clients, Base banner,
native library version, and a fresh instance UUID read through CA. It creates
owned loopback IOC/CA-repeater processes with private ports and native config
and state directories. Only processes created by this run are stopped.

The initial suites comprise one legacy matrix case, nine sequencing cases, ten
failure/lifetime cases and five native protocol cases. The lifecycle, batch
and conversion suites below add the full ordinary and immediate repetition
profiles. `--case <name>` selects one named case and reports partial coverage;
`--repeat N` repeats the selected suite with fresh instances.
Missing/skipped cases, absent trace, trace overflow, wrong wire identity,
wrong FLNK observations, timeout or cleanup failure return nonzero.

## Pre-Migration SNMPv3 And SET Observations

Build the identified pre-worker module separately and run the current fixtures
against that executable. Both suites require real snmpd and snmpget in PATH;
v3-baseline also requires a C compiler and the Linux x86-64 rtld-audit ABI.
Use a private new build directory and retain it with the resulting evidence.

```bash
SNMP_PRE_WORKER=750ea26243614ec4402994959e21bd970b0a6856
SNMP_V3_BUILD=/tmp/snmp-pre-worker
SNMP_BUILD_ARGS=(--base "$SNMP_TEST_BASE" --revision "$SNMP_PRE_WORKER")
python3 tests/build_fixture.py "${SNMP_BUILD_ARGS[@]}" --output "$SNMP_V3_BUILD"
SNMP_TEST_IOC="$SNMP_V3_BUILD/bin/linux-x86_64/snmpRequestTest"
SNMP_V3_ARGS=(--ioc "$SNMP_TEST_IOC" --profile tests/profiles/snmpv3.json)
python3 tests/run_snmp.py "${SNMP_V3_ARGS[@]}" --suite v3-baseline
python3 tests/run_snmp.py "${SNMP_V3_ARGS[@]}" --suite legacy-set
```

The v3-baseline suite has five observation cases: 100 cold IOC starts,
1000 warm reads with native-call observation, 1000 warm reads without it,
and 1000 reads in each of the two-address control and discovery-loss conditions.
The latter use a 400 ms record deadline, a 4 s transport timeout and a requested
100 ms read interval. Every hundred healthy reads also starts one request
to the second actual agent. The fault proxy drops that address's real packets;
neither native discovery nor an internal module function is substituted.

Native-call observation uses LD_AUDIT only in the owned IOC. It reports actual
module-to-library open/close entry and return without replacing the called
address or changing arguments/return registers. The observer build and source
hashes are retained. Wire discovery counts are independent observations, not
estimates based on session counts. The run without LD_AUDIT keeps observation
overhead distinct from ordinary timing. AuthPriv bodies stay encrypted.

Successful cold/warm reads require applied values, one terminal result and
FLNK before PACT clears. CPU ticks, FD/RSS/thread samples, native calls and
acceptance/dispatch/result/FLNK/completion times are retained. The two-address
cases collect outcomes even when the healthy record becomes INVALID during
the other address's discovery wait. Their observations.json explicitly marks
observation_only=true and reports p99, maximum and invalid_count. A passing
collection does not mean discovery isolation passed: apply M8/T8's separate
zero-INVALID and latency criteria when qualifying the worker candidate.
No restart-isolation or one-hour resource qualification is supplied by this
baseline suite. Run timing comparisons without other laboratory load.

The legacy-set suite has twelve cases. It exercises the shipped ao, longout
and stringout support against disposable writable OIDs implemented through
the real snmpd pass_persist interface. Real native snmpget verifies device
state independently of the IOC and its UDP observer. The ASCII laboratory
values, actual applied SET log and raw request/response metadata remain in
the case directory.

Coverage includes successful SETs, agent error responses, queued writes to
one OID behind a held GET, three output types, shared-OID readback and
SetSkipReadbackMSec, plus request loss and response loss after application.
Each loss direction uses retries 0, 1, 3 and omitted timeout/retry overrides.
The inherited policy therefore includes six real attempts over about a minute
per output; the complete suite takes several minutes. It verifies the actual
wire types/values and request IDs, device value, recovery without another
command, and no additional module SET replay. Native retransmissions may
apply a command more than once; packet counts do not establish exactly-once
device execution.

record-samples.json retains values, PACT, UDF, STAT and SEVR, including
transient alarms. Loss observations distinguish a native timeout callback
from the pre-worker module's 60-second stale-session retirement. The latter
is an observed baseline termination route, not successful native timeout
delivery or acceptance of the future worker watchdog. Preserve both outcomes
when comparing a replacement. The short laboratory stale threshold is 500 ms,
output callback period 100 ms and readback suppression 1000 ms; only the
explicit default-policy cases omit SessionTimeout and SessionRetries.

These suites are individual P801 observations. run_matrix.py does not yet
include the replacement-worker acceptance matrix; neither suite qualifies
the final architecture or physical hardware by itself.

## Native Session Adapter

The native suite drives the module's Single Session adapter, snmpNative.cpp,
from the test IOC through the `nativeProbe` and `nativeProbeMixed` IOC shell
commands in tests/src/nativeProbe.cpp. The probe prepares each session
description as a transport would; opening, sending, servicing, closing and
completion delivery run in the real module adapter against a real snmpd and
the transparent UDP observer. The IOC's record transport is not involved.

```bash
SNMP_NATIVE_ARGS=(--ioc "$SNMP_TEST_IOC" --profile tests/profiles/snmpv3.json)
python3 tests/run_snmp.py "${SNMP_NATIVE_ARGS[@]}" --suite native
```

The nineteen cases cover v2c and v3 authPriv responses, twenty concurrent
requests, request loss at retries 0, 1 and 3, reply loss, close with pending
requests, an unresolvable endpoint, oversized GETs that the library fails
inside the send, an unknown v3 user and a wrong authentication key, a
completion that sends another GET, recovery after the agent restarts with a
higher engineBoots, a USM report carrying a foreign request ID, an SNMPv3
retransmission whose send fails at the socket boundary, two sessions
with different deadlines in one service loop, a silent endpoint beside a
healthy one, and a session socket above FD_SETSIZE. Every accepted request must complete exactly once,
and a rejected request never completes. Retry cases require one wire attempt
per try under a single request ID, completion near the configured timeout
times the attempts, and one library RESEND callback per retransmission; they
also require snmpget with the same timeout and retries to send the same
number of attempts. The send-failure case bounds resident memory growth over
twenty rejected 6000-varbind requests. The descriptor case occupies every
free descriptor below 1100 before opening and requires a socket at or above
it, so the process descriptor limit must exceed that; raise it for
containers, for example with `--ulimit nofile=4096:4096`.

These are adapter results. They do not qualify discovery isolation of the
record path, worker processes or profile handling.

## Named Profiles, Endpoints And Engine Identity

The config suite starts the actual test IOC with named SNMPv3 profiles and
endpoints, the legacy host setters and configuration files, against real
snmpd agents through the transparent UDP observer. Profile and credential
files are written per case with disposable test secrets. tests/endpoint.db
holds a request-mode and a legacy polled record that select an endpoint with
the `endpoint:NAME -` link.

```bash
SNMP_CONFIG_ARGS=(--ioc "$SNMP_TEST_IOC" --profile tests/profiles/snmpv3.json)
python3 tests/run_snmp.py "${SNMP_CONFIG_ARGS[@]}" --suite config
```

The eight cases cover reads through a named endpoint beside an unchanged
legacy host link; noAuthNoPriv, authNoPriv and authPriv profiles for one
address, each observed on the wire at its own level; authPriv with SHA-224,
SHA-256, SHA-384 and SHA-512 against agents configured for each; startup
rejection of invalid names, paths, sizes, NUL bytes, fields, levels,
algorithms outside policy, credential symlinks, permissions and FIFOs,
unterminated last lines, short passphrases, duplicate or unknown definitions, conflicting credentials at one
address, out-of-range endpoint parameters, invalid engine IDs, a wrong link
placeholder, an unknown endpoint, records of an endpoint whose setting was
rejected, the reserved endpoint prefix through the legacy security and
batch-size setters, invalid legacy host settings including a setter call
missing its value, a legacy configuration
file with a tab-separated passphrase containing a space, an unknown key and
an overlong line, and every definition attempted after iocInit; IOC shell error propagation
under `on error break`; wrong user, authentication secret, privacy secret and
context, each completing once as INVALID with no value, then a corrected
restart; automatic, explicit, host-setter (with the def prefix) and file engine IDs
with a wrong explicit ID that is sent as configured and fails; and 5-byte and 32-byte
engine IDs completing real exchanges with agents restarted under those IDs,
where every request carries the configured ID and no discovery is sent.
Every case searches the IOC log and startup file, or the shell output, for
the disposable secrets.
The case of a credential file owned by another user needs a second account
and is not run.

## Observer Negative Controls

Run each option below with the sequencing command. Each invocation runs the
same delayed/unchanged case with a real boundary or DB defect and must return
nonzero for the corresponding reason:

| Option | Defect | Required detection |
| --- | --- | --- |
| `--negative-control wrong-value` | Peer returns 909 instead of 101 | Real record value assertion fails |
| `--negative-control miswired` | Delivered `sequence_miswired.db` connects A to AuditB | Missing expected AuditA completion and wrong source PACT are detected |
| `--negative-control trace-loss` | IOC RequestTrace is disabled | Actual driver evidence is missing |

A nonzero status alone is insufficient: inspect `results.json` to confirm the
failure reason. Startup/configuration failure does not qualify as an observer
negative-control result. No driver function, internal completion path or
library authentication operation is replaced by a mock.

The same three negative controls are available with `--suite lifecycle`.
They exercise `lifecycle.db` and its own generation checker: the external
peer supplies 909, the delivered DB override routes A to AuditB, or the
actual IOC trace is disabled. Use `--cycles 1` for these expected failures.
Both suites retain the normal real acquisition and Base completion path.

## Evidence And Result Interpretation

Each invocation retains `run.json`, `config.json` and `results.json` under a
new `work/snmp-tests/<run-id>/` directory. `--output <new-directory>` chooses
another unused location. Every case has its own startup, IOC/client logs,
wire events, parsed driver/audit observations and runtime identity record.
Failed runs remain intact; later runs use new directories.

| File | Observed content |
| --- | --- |
| `run.json` | Profile, source/build/fixture hashes, timestamps, OS, versions and process/library identities |
| `wire.jsonl` | External request and response observations with native wire IDs and numeric OIDs when plaintext |
| `driver.jsonl` | Actual bounded IOC trace: record/generation, opaque transaction ID, native request ID, OID and event |
| `flnk.jsonl` | Actual downstream value, PACT, severity, status, UDF, RVAL, string text, counter and IOC monotonic time |
| `ca.jsonl` | Actual client calls and replies; snapshots include record timestamps through caget -a |
| `ioc.log`, `st.cmd` | Actual IOC output and exact startup input |
| `results.json` | Per-case outcomes and complete/incomplete run status |

The root identity record distinguishes the built module inputs from the
current harness/fixtures. A copied build tree may have no Git metadata;
its build manifest and individual fixture hashes still identify those inputs.
The loaded library path and checksum are verified against the build manifest.
Protocol/legacy cases have empty request/audit files where that instrumentation
is inapplicable; emptiness never counts as sequencing evidence.

The bounded trace is disabled by default. When enabled it records accepted,
claimed, dispatch-attempt, terminal-result, applied and completed events.
Transaction IDs correlate all claimed members; native wire ID plus numeric OID
is checked against the separate UDP observation. FLNK time is compared only
with monotonic events in the same IOC. A peer arrival timestamp is not a
substitute for causal record ordering. At FLNK, PACT is 1; after completion,
CA must observe PACT=0.

Native authPriv bodies remain encrypted in the wire observer. Public v3
headers prove protocol/flags/discovery, while the actual native client and IOC
readback prove SET application. The observer does not decrypt or reproduce
USM. Credentials in private fixture files are synthetic, disposable test
values, never operational credentials.

## Legacy Comparison Contract

`legacy_matrix.db` includes ai raw scaling, longin, stringin and CHAR waveform
inputs, plus ao raw-integer, longout integer and stringout SET/readback. It
checks actual wire SET types/values, independent peer state, changing inputs,
output readback without an echoed SET, communication loss and recovery.

The baseline waveform preserves a leading blank and quotes from native text:
the bytes are space, quote, hello, quote and NORD is 8. CA's default array read returns all 128 configured elements.
After the configured stale threshold, legacy inputs remain active until cache
recovery; output readback raises its communication alarm. These observations
are recorded, not relabeled as request-driven completion. The fixture uses a
500 ms stale threshold, 200 ms native timeout, zero retries and 100 ms output
poll/readback intervals to bound the laboratory run. Production defaults do
not change. Bounded sampling waits for the actual expected readback values and
idle/no-alarm state; every sample, including transients, remains in
`legacy-samples.jsonl`. This measures eventual readback and does not assert
absence of transient legacy INVALID values or atomicity across CA reads. Only
the identified unmodified baseline lacks the candidate shutdown marker and is
exempt from that marker assertion; its owned process exit is still checked.
Other archived revisions receive the same shutdown check as a working candidate.

## Full Lifecycle, Batch And Conversion Profiles

```bash
SNMP_PROFILE=tests/profiles/loopback.json
SNMP_TEST_ARGS=(--ioc "$SNMP_TEST_IOC" --profile "$SNMP_PROFILE")
python3 tests/run_snmp.py "${SNMP_TEST_ARGS[@]}" --suite lifecycle
python3 tests/run_snmp.py "${SNMP_TEST_ARGS[@]}" --suite batch
```

| Suite | Cases | Default repetitions |
| --- | --- | --- |
| lifecycle | 15 | 100 ordinary cycles per variant; 1000 immediate responses |
| batch | 10 | 100 cycles per case, split across four fresh IOCs |
| conversion | 2 | 100 value cycles per case |

`--cycles N` overrides the cycle count for development and always marks the
invocation partial, even if N matches the default. Run without this option
for the declared repetition profile. Every accepted generation is matched
to its independent expected value, exact event sequence, actual wire identity
and one downstream audit. FLNK text is read from the actual source VAL through
Base dbGetField, not reconstructed from the audit's numeric input. Numeric
CA fields may be queried together; these reads are not an atomic snapshot.
The completion predicate and the separate FLNK audit both have to pass.

Lifecycle coverage includes a ten-second idle interval, held and unchanged
values, late same-OID waiters, A-to-B-to-C FLNK, ordinary active PROC/RPRO,
CA put-notify, five actual active periodic scans, the separate extended
SCAN alarm, two-host fanout, an invalid fanout link, 100 fresh PINI starts,
disable before/during acquisition and terminal error recovery. The actual
record LCNT and put-notify pointer establish the scan and notification
preconditions; no internal Base or driver call is replaced. Put-notify must
stay pending through its own acquisition, and client timeout text is a
failure even when caput returns zero.

Batch coverage queues 1, 20 or 21 distinct OIDs behind a held transaction,
using maximums 20 and 1, plus pre-dispatch shared waiters and distinct
community groups. Queued membership is observed before release. Actual wire
batches must obey the limit, contain no duplicate OID and dispatch within the
declared healthy bound after host release. Shared waiters must have the same
transaction; different communities must have distinct wire requests.
The trace is never reset to fit a repetition run: each 25-cycle chunk uses a
fresh IOC and retains its complete trace.

The conversion profile checks ai RVAL 123/246 scaling to 12.3/24.6 with
absolute tolerance 1e-9, supplied VAL without scaling, signed 32-bit longin
boundaries, changing and truncated stringin values, and mixed legacy input
and output readback. With the fixture's STRING: mask, the native empty
OCTET STRING representation does not match that mask: both legacy and request
stringin report READ/INVALID. The request preserves its last valid value and
completes once. A later nonempty value clears the alarm. Idle request records
must not complete during legacy polls, and all these reads must emit no SET.

Waveforms remain legacy records. Test STRING, CHAR and UCHAR at NELM 16 and
128 against the independently archived baseline using the same fixture and
native value sequence. Each five-character payload retains the native leading
blank and quotes; the existing NORD is 8. STRING's existing byte-oriented
buffer/NORD behavior is preserved, not redefined as new request support.

First capture the complete baseline waveform case in a new directory:

```bash
SNMP_WAVE_BASELINE=/tmp/snmp-wave-baseline
SNMP_BASE_ARGS=(--ioc "$SNMP_BASELINE/bin/linux-x86_64/snmp" --profile "$SNMP_PROFILE")
SNMP_WAVE_ARGS=(--suite conversion --case waveforms --dtyp Snmp --output "$SNMP_WAVE_BASELINE")
python3 tests/run_snmp.py "${SNMP_BASE_ARGS[@]}" "${SNMP_WAVE_ARGS[@]}"
python3 tests/run_snmp.py "${SNMP_TEST_ARGS[@]}" --suite conversion --baseline-evidence "$SNMP_WAVE_BASELINE"
```

The baseline invocation is marked partial because it selects the waveform
case; that case still runs all 100 cycles. The full candidate conversion run
requires this independently identified baseline and compares the complete
observed arrays, lengths, activity, UDF and alarms. A candidate used as its own
baseline fails provenance validation. Baseline and candidate must use matching
profile and relevant fixture/observer hashes.

## Outer Socket Failure Fixture

The lifecycle transport case and the native resend_send_failure case compile
`socket_fault.c` with the system C compiler and preload it only into the owned
test IOC. It does not intercept Net-SNMP, device support, callbacks or Base
record processing. An explicitly
armed, one-shot AF_INET/SOCK_DGRAM socket creation fails with EMFILE; an
explicitly armed sendto/sendmsg to the selected loopback peer fails with EIO.
The file control is inactive for ordinary startup, CA clients and recovery.

In the lifecycle case, every injected failure must have one logged real
socket call between claim and terminal result, no corresponding wire
request, READ/INVALID at FLNK, retained valid value, idle completion and a
successful fresh recovery. Open
failure has no dispatch attempt; send failure has one attempt without wire
transmission. Unconsumed controls, unused fault events and missing evidence
fail the test. `socket-build.json` retains compiler arguments, source/library
hashes and build output; `socket-fault.jsonl` retains the actual fault events.

The native resend_send_failure case arms the send fault only after the proxy
has dropped the first attempt of an SNMPv3 GET. It requires exactly one
logged sendto or sendmsg fault, one send_failed completion for that request
before the session closes, and no other attempt of it on the wire.

## Failure, Diagnostics And Process Lifetime

```bash
python3 tests/run_snmp.py "${SNMP_TEST_ARGS[@]}" --suite robustness
python3 tests/run_snmp.py "${SNMP_TEST_ARGS[@]}" --suite pressure
python3 tests/run_snmp.py "${SNMP_TEST_ARGS[@]}" --suite teardown
python3 tests/run_snmp.py "${SNMP_TEST_ARGS[@]}" --suite accounting
```

The robustness suite has 16 cases: two absolute-deadline boundary regressions,
old/duplicate packet replay, native retry exhaustion, and twelve response
variants. Each response variant runs 100 prime/fault/recovery cycles using
21 real input records; fresh 20-cycle IOC chunks retain the complete trace.
Reordered/extra OIDs preserve requested results; missing, duplicate and wrong
OIDs fail only affected records. Exceptions, wrong types, oversized values,
malformed BER and a mixed per-OID failure batch check retained values and
subsequent recovery. Packet replay and retry exhaustion run 100 cycles each.
The native retry case observes exactly an initial GET and two retransmissions
with the same wire ID. All accepted generations have one FLNK audit and a
matching actual wire transaction, except explicitly proven pre-send failures.

The two deadline regressions each use a 400 ms request deadline and suspend
only the owned IOC's `snmpComplete` Linux thread with ptrace. Driver code,
Net-SNMP, Base callbacks and the monotonic clock remain unchanged. After a
600 ms external hold, the real reply is processed before that thread resumes.
The late request must fail; an expired queued record must emit no GET.
`thread-*.json` records ownership, actual stop/resume timestamps and cleanup.
The host must permit ptrace of this child thread. A permission failure is an
incomplete execution, not a passing regression. `--cycles` changes ordinary
robustness repetition counts and marks the invocation partial; it does not
repeat these two scheduling-boundary cases.

Diagnostics at each real FLNK are matched to the request trace and source
record audit. They must report application before completion, exact accepted/
valid/failed counts, and unchanged last-valid generation/time on errors.
The final idle snapshot checks completed counts and latency decomposition.
The accounting suite additionally checks queued age, useful reports with
tracing disabled, and 1000 healthy-host reads both alone and with a silent
second host. It retains every latency sample and applies the profile's maximum
and p99 difference limits. Timings measure acceptance to callback completion.

The pressure suite holds the actual Base low-priority callback queue for
60 seconds, after ten warmup acquisitions of 21 records. It observes the full
two-entry queue, actual callback insertion rejection, and 21 occupied record
slots. Active CA PROC puts must coalesce into one later acquisition per record.
The already-ready result remains immutable past its acquisition deadline;
release consumes it once and then acquires the new value. `/proc` observations
record FD count/targets, RSS and threads throughout pressure and after draining.
The initial FD count must remain unchanged for 100 ms. After record completion,
the FD count must return to that baseline and remain there for 100 ms within
the profile action timeout; record completion alone does not synchronize native
session or CA connection disposal. Immediate and settled counts, plus all
settlement samples, are retained; a persistent increase still fails. Thread
counts must remain at baseline; RSS growth is bounded to 4 MiB for this
short test. This does not replace the separate one-hour resource acceptance.
User/system CPU ticks and clock frequency are sampled from the same owned
process. resource-summary.json derives elapsed CPU time and percentage of one
core; it is an observation, with no unapproved site CPU threshold.

The teardown suite runs 20 fresh owned PTY starts for each of four graceful
variants: terminal EOF and explicit IOC exit, each with network work or a real
completion callback pending. It requires the ordered module shutdown markers,
exit zero and no FLNK after shutdown entry. Twenty separate forced-kill cases
require signal termination without a graceful marker and successful fresh-IOC
recovery. Terminal identity and the child's actual fd 0 are retained. Base's
real `atExitDebug` output compares EOF and explicit exit on both the candidate
and the exact archived baseline; select `base_exit_observer` with the baseline
`snmp` executable. On POSIX Base, its registered C `atexit` handler runs cleanup
even when the old main's version check selects the empty local epicsExit.
That source-level defect alone does not establish missing runtime cleanup.
The PTY helper waits for the actual prompt before sending EOF, keeping terminal
readiness separate from CA readiness and report completion.

The isolated builder accepts `--sanitizer address` and records compiler/linker
flags, source identity and artifacts. This instruments this module and its IOC;
the installed Base and system Net-SNMP libraries remain their original builds.
Use the same public suites against that executable. Sanitizer failures, runtime
restrictions and unavailable diagnostics remain explicit failures or incomplete
coverage; they are not suppressed into a passing resource claim.

Final platforms and hardware acceptance remain separate canonical criteria.

## Registration And Examples

The registration suite runs examples/request-inputs.iocsh and its exact DB
in both snmp and snmpRequestTest. Actual peer reads cover ai, longin and
stringin SnmpRequest plus legacy Snmp; exported dsets, expanded DBD and generated
registration identities support the runtime evidence. Invalid SCAN, missing or
malformed INP, buffer lengths, flags/OIDs and request parameters fail visibly.
Post-iocInit parameter changes leave the configured 400 ms deadline unchanged,
verified by a real unanswered acquisition. Both old/new binary/DBD mismatch
directions execute actual IOC startup and must produce the expected binding
error. A manifest rejection alone is not this test.

```bash
SNMP_BASELINE_IOC="$SNMP_BASELINE/bin/linux-x86_64/snmp"
SNMP_PROFILE=tests/profiles/loopback.json
SNMP_REGISTRATION=(--profile "$SNMP_PROFILE" --suite registration)
python3 tests/run_snmp.py --ioc "$SNMP_TEST_IOC" "${SNMP_REGISTRATION[@]}" --baseline-ioc "$SNMP_BASELINE_IOC"
```

These commands use a Bash array for the shared arguments. Evidence is retained
even when Base continues startup after a configuration error.
