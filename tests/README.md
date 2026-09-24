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
and native Net-SNMP versions 5.9.1, 5.9.3 or 5.9.4.pre2. A declaration is not
proof that every matrix cell passed on that platform. The protocol suite also
requires the actual `snmpd` and `snmpget` programs in PATH.

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

The lifecycle transport case compiles `socket_fault.c` with the system C
compiler and preloads it only into the owned test IOC. It does not intercept
Net-SNMP, device support, callbacks or Base record processing. An explicitly
armed, one-shot AF_INET/SOCK_DGRAM socket creation fails with EMFILE; an
explicitly armed sendto/sendmsg to the selected loopback peer fails with EIO.
The file control is inactive for ordinary startup, CA clients and recovery.

Every injected failure must have one logged real socket call between claim
and terminal result, no corresponding wire request, READ/INVALID at FLNK,
retained valid value, idle completion and a successful fresh recovery. Open
failure has no dispatch attempt; send failure has one attempt without wire
transmission. Unconsumed controls, unused fault events and missing evidence
fail the test. `socket-build.json` retains compiler arguments, source/library
hashes and build output; `socket-fault.jsonl` retains the actual fault events.

Twenty-start PTY shutdown, the extended pressure/resource matrix,
final platforms and hardware acceptance remain separate canonical
criteria. A full lifecycle pass does not close those requirements.
