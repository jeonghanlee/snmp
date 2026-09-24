# Real IOC Tests

## Scope

The runner executes the built SNMP module through real EPICS record processing,
CA clients and UDP. It uses an external controllable peer for faults and a
real Net-SNMP snmpd for native protocol, USM, GET and SET coverage. Test-only
FLNK audit support belongs to `snmpRequestTest`, not the production IOC.

Hardware, production operation, the future worker/profile architecture and
full repetition/pressure acceptance are outside these initial suites. Their
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

The four suites comprise one legacy matrix case, nine sequencing cases, ten
failure/lifetime cases and five native protocol cases. `--case <name>` selects
one named case and reports partial coverage; `--repeat N` repeats the selected
suite with fresh instances. Neither changes the canonical acceptance counts.
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
| `flnk.jsonl` | Actual downstream subroutine value, PACT, severity, counter and IOC monotonic time |
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

Sequencing/failure fixtures retain the initial 19 cases. Full 100/1000-cycle
ordering, five observed active scans, 20-start shutdown, 60-second pressure,
final architecture and hardware acceptance are separate canonical criteria.
