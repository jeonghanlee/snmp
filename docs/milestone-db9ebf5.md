# SCAN-Driven SNMP Development Milestone

Release line: master (feature development; no release number assigned)
Milestone index: db9ebf5
Canonical path: `docs/milestone-db9ebf5.md`
Canonical branch or ref: `feature/scan-driven-io`
Git upstream: none at creation
Remote tracker: none
Source baseline: `db9ebf51bc81d6f63d9395513d94d60b3b7eda83`
Created: 2026-09-22

Next session entry point: commit M8 step 3, the native session adapter, then
begin P804 validated profiles. Step 3 passes its native suite 19/19 and the
regression suites on Debian 13 and Rocky 8, and its third bounded recheck
(fup20260924_212921) passed on 2026-09-24 after the review and recheck
findings were corrected. The reviewed
M8 step 1 fixtures and step 2 extraction are committed. Step 2 passed
its regressions on Debian 13 and Rocky 8 under D10 and its independent
third-person and maintainer reviews on 2026-09-24; the stale-session
deletion race is carried to step 6. Step 1's corrected baseline and
current-state documentation passed the bounded third-person and maintainer
recheck on 2026-09-24.
M5 handoff cross-check passed and its fourteen reviewed paths are committed
locally as 750ea26243614ec4402994959e21bd970b0a6856. M8's fresh 43-case
compatibility baseline and 100-cold/1000-warm real IOC v3 observations are
recorded, together with the 12-case writable SET baseline. The corrected APC
consumer converts all 63 loaded SNMP inputs; the prior 15/63 conversion is
retained as a mixed-input observation. This accepts the baseline only;
the replacement implementation and final M8 acceptance remain pending.
The pre-migration discovery-fault observation has 80 INVALID
healthy-record completions in 1000 reads; it does not pass T8 isolation.
The complete final M5 matrices and independent third-person/second-person
review are accepted locally under the documented Base limitation. All 35
required steps pass on each of Debian 13, Debian 12 and Rocky 9; the original
Debian 12 comparator's three v3 shutdown failures remain recorded as failed.
The deferred Base correction proposal has completed static and maintainer
review, and its corrected limitation documents passed independent review;
no corrected Base has been built or executed.
Decision Date: 2026-09-24; continue
module development with this documented limitation while Base repair remains
deferred. Preserve every failed test as failed; this permits development
progress, not an unconditional completion guarantee or deployment acceptance.
The selected M4 plus legacy DB operational rollback is implemented in the
matrix and instructions; its affected-path and final full-matrix verification
completed on 2026-09-24. Earlier failed matrices and all natural/controlled
Base callback failures remain retained. Final handoff derivatives passed
independent review before the local commit; remote landing remains pending.
M4 local tests, independent third-person/second-person reviews and handoff
cross-check passed; its reviewed 21 paths are committed as 30d8b81.
M3 is committed as 68294c2; its T5/T10 dedicated successful-generation
diagnostic checks have now passed on the later M4 source, as recorded below.
M2 is locally accepted and committed as e1878bc. M1's source contract and independent third-person
and second-person reviews are accepted locally; remote landing remains pending.
Decision Date: 2026-09-24. The owner accepts the current M1-M8 plans and directs
sequential implementation, review, correction and a commit per milestone.
This authorizes local implementation and verification; G2/G3 still require
their concrete environment, acceptance limits and operating window. Required
checks are not waived. Preserve the existing reviewed candidate rather than
reconstructing historical source states. For M8, begin at step 1 and establish
the real IOC v3 and writable SET baselines before transport migration. The
three-reviewer full-plan assessment is complete with no new demonstrated plan
defect; its scope and evidence are recorded under M8. Worker implementation
follows the earlier steps rather than replacing them. D9's inherited
timeout/retries derive 150000 ms, including a selected 20 s operating allowance
above the 130 s native interval budget.
On Debian 13, 32 native cases passed, with about 60 s for ordinary loss,
118 s for delayed discovery followed by application loss and 68 s for delayed
timeliness recovery followed by response loss. These are native measurements,
not worker watchdog acceptance. Other library packages and the complete
IOC/helper path remain subject to qualification.
The earlier native-library
experiment observed about 4 s of healthy-response delay with a serialized owner
and 0.100-0.195 ms with independent processes during the same discovery fault.
It is not an IOC integration result; the full T8 and new worker-boundary T18
remain pending. The existing candidate remains the sequencing baseline;
its remaining protocol/platform/resource and hardware acceptance matrix is
still open. The initial
candidate passed 19 real request IOC tests, 12 unchanged APC legacy tests, and
12 tests with APC input DTYP converted to SnmpRequest. All 21 test IOCs reached
graceful module shutdown. These are the 2026-09-22 results. The M2 evidence below adds actual IOC
SNMPv1/v2c/v3 and writable SET runs on 2026-09-24. The original 19 cases also
ran on Debian 12 and Rocky 9 before the M2 harness changes; those runs do not
qualify the final architecture. Hardware, firmware comparison, long-duration
resource tests and final implementation acceptance remain pending.
No installed tree or original APC checkout was changed.

### Current Local Candidate

Decision Date: 2026-09-22. The instruction to proceed authorizes local
implementation and testing of the separate-DTYP/per-record direction in D3/D4.
It does not authorize production deployment or firmware changes. The initial
candidate supports ai, longin, and stringin; waveform and outputs keep Snmp.
The candidate contract is documented in `docs/snmp-request.md`; its numerical
defaults are implementation settings, not measured production acceptance limits.

The implementation uses one request slot per record, session-frozen OID
membership, matching-response snapshots, a separate completion/deadline worker,
Base callbacks with queue retry, and graceful shutdown before storage deletion.
The real fixtures are `tests/sequence.db`, `tests/legacy.db`,
`tests/snmp_peer.py`, `tests/test_request.py`, and `tests/src/sequenceProbe.*`.
These actual paths supersede the proposed v2c fixture/runner filenames below;
the M2 runner and protocol paths below supersede the original launch procedure.
Broader stress and final architecture scenarios remain planned.

| Observed local result | Evidence |
| --- | --- |
| Candidate module and both IOC builds pass on the selected Debian 13/Base 7.0.10 tree. | `~/scratchpad/snmp-request-candidate/{snmp,apcpdu}-build.log` |
| 19 real IOC tests pass, including value/alarm observation at FLNK, PACT clear, callback pressure, independent deadline, queued timeout, mixed polling, and pending-work EOF/explicit shutdown. | `~/scratchpad/snmp-request-candidate/snmp-retest.log`; each retained case contains IOC, peer, and client logs. |
| The same no-idle-poll assertion fails with real legacy Snmp support because it sends an unsolicited GET. | `~/scratchpad/snmp-request-candidate/negative-control.log` |
| Existing APC PDU tests pass unchanged against the candidate library: 12 tests. | `~/scratchpad/snmp-request-candidate/apcpdu-retest.log` |
| APC PDU input-DTYP conversion passes all 12 unchanged consumer tests, including sensor fault isolation; module shutdown completes. | `~/scratchpad/snmp-request-candidate/apcpdu-request-retest.log`; `apcpdu-pva-4mb6zhek/ioc.log` |
| Pending-input starvation reproduces on the earlier candidate and passes after request-first rotating selection. | `~/scratchpad/snmp-request-candidate/snmp-starvation-before.log`; final `test_legacy_polling_does_not_starve_request` case |
| Final independent builds have no compiler warnings/errors, use the selected dependency tree, and match the source-input digests. | `*-rebuild.log`, `*-ldd-final.txt`, `source-inputs-retested.json` |
| No files under the selected version tree changed during the independent candidate builds/tests. | `install-tree-changes-final.txt` is empty (mtime and ctime check). |

Raw evidence is retained, including failures; newer results do not erase it.
Candidate source identity is recorded in `source-inputs-retested.json` and
`retested.patch` in the same scratch directory. No commit or release is claimed.

Final run: 2026-09-22T19:24:32-07:00 through 19:26:50-07:00.
`retest-summary.json` contains the library/IOC SHA-256 identifiers and return
codes. The initial APC conversion failure is retained in
`apcpdu-request-tests.log`; it is superseded by the final executed result.
The corrections select pending requests independently of legacy poll bins and
start cleanup at Base `initHookAtShutdown`, before callback queues stop.

The broader plans below remain acceptance checklists. Their unexecuted variants
are not waived by the 43 original passing local tests. Subsequent M2 native
protocol evidence does not close final v3/platform qualification.
M3 now records the 20/21-OID boundary variants, extended active scans and
put-with-completion, three-record serial chains and controlled open/send
failures. Sanitizers/resource soak, final implementation review and the
per-device pilot remain subject to their milestone acceptance conditions.

## Scope

This document is the development handoff for an opt-in SNMP read mode whose
requests originate in EPICS record processing. It covers the current data
path, proposed ownership and batching rules, implementation tasks, real-path
verification, downstream IOC migration, controlled deployment, and rollback.

The compatibility direction is established: retain the legacy default and
introduce an explicit opt-in path through a separate input DTYP (D3).
Local implementation is authorized by the later proceed instruction recorded
above. The initial contract and observed checks are concrete; the broader
protocol/platform/resource matrix and device timing acceptance remain open.
No peer has been assigned or contacted by this document.

**Out of scope:** replacing the default polling mode, redesigning SNMP SET
semantics, changing PVA object schemas, rewriting the module around asyn,
and changing device firmware or site security policy. Session lifecycle and
SNMPv3 security architecture are now included in the M8 design scope (D6);
the tested local candidate does not implement that replacement. A release
number, tag, merge, publication, or fleet-wide rollout is
not implied.

## Current Understanding

### Repository And Build State

At creation, the feature branch has the source baseline shown above and no
implementation changes. Recheck its actual branch, HEAD, local changes, and
remote state before resuming; these are observations, not permanent properties.

The source builds `devSnmp` and the `snmp` IOC through
[snmpApp/src/Makefile](../snmpApp/src/Makefile).
[devSnmp.dbd](../snmpApp/src/devSnmp.dbd) declares `Snmp` support for
`ai`, `longin`, `stringin`, `waveform`, `ao`, `longout`, and
`stringout`. The existing Debian 12 and Rocky 9 workflows run builds;
they do not currently demonstrate the proposed asynchronous contract.

The README describes a customized 1.1.0.4 module, while the compiled version
macros in `devSnmp.cpp` still produce 1.1.0.3. Identify test and deployment
artifacts by source commit and binary checksum, not by that string alone.

### Existing Data Path

All symbols in this table belong to
[devSnmp.cpp](../snmpApp/src/devSnmp.cpp) at the source baseline.

| Component | Observed behavior | Consequence for this work |
| --- | --- | --- |
| `devSnmp_pv` constructor | Derives an OID polling period from SCAN; Passive uses `PassivePollMSec`; shared OIDs use the faster requested period. | Passive does not mean that the legacy driver stops polling. |
| `devSnmp_group::processing` | Selects due OIDs by weight and may fill a GET batch with other eligible OIDs. | Scheduling belongs to the driver independently of a particular DB processing request. |
| `devSnmp_host::processing` | Serializes outstanding transactions per host and arbitrates GET/SET queues. | Batching must retain device serialization and bounded read starvation. |
| `snmpAiRead` | Waits if there is no cached value; otherwise reads the cache and may call `queueUpdate` for Passive records. | A processing pass is not necessarily a fresh request followed by its response. |
| `devSnmp_oid::queueUpdate` | Makes an OID due only when the previous send is old enough. | Calling it is not an immediate, individually tracked GET. |
| `replyProcessing`, `updatePVs`, `processRecord(true)` | A received OID can cause all associated records to process under DB locking. | Response processing is not restricted to records that requested that transaction. |
| `readTask`, `host::processing` | Share a session mutex around Net-SNMP operations; the read task also holds it across select/read/timeout. | Record locks, queue locks, and the Net-SNMP lock require an explicit ordering analysis. |
| `pollsPerSecond`, `sessionGotReply` | Poll rate is an average since counter initialization/reset; group reply accounting occurs before success/failure classification. | Reported rates and reply counts are insufficient proof of recent valid acquisition. |
| `readReplyProcessing` | Some no-value or mismatched-OID paths still advance reply accounting. | Last valid sample time must be distinguishable from last callback or attempted read. |

The relevant downstream APC PDU database uses a periodic trigger and fanout
to process Passive input records. For example, `apcpduApp/Db/load_pdu3ev.db`
contains the load trigger, fanout, and an `ai` using `sR` conversion.
A successful SNMP reply can also process those records independently.
The existing architecture therefore has both DB-driven processing and
driver-driven updates. OID batching itself is compatible with EPICS; the
change concerns who requests an acquisition and who owns its completion.

### EPICS Semantics That Must Be Preserved

The following authority was inspected locally at EPICS Base R7.0.10:

- `modules/database/src/ioc/db/dbCommon.dbd.pod`, **Scan Fields**:
  PACT remains true during asynchronous processing; ordinary `dbProcess`
  does not start another processing pass while it is true. Repeated active
  scans can raise a SCAN alarm. FLNK runs near completion, before PACT clears.
- `modules/database/src/ioc/db/callback.c`, **ProcessCallback** and
  **callbackRequestProcessCallback**: the Base callback helper obtains the
  record lock and invokes record support for asynchronous completion.
  Its queueing result must be handled.
- `modules/database/src/std/rec/aiRecord.dbd.pod`,
  **Monitor Parameters**: MDEL=0 posts value monitors on value changes;
  MDEL=-1 posts on each completed processing. Neither setting requests a
  hardware acquisition. Alarm events are a separate reason for a monitor.

The new mode must use each record type's actual asynchronous device-support
contract, including return values and conversion behavior. Do not generalize
`ai` behavior to every other type without checking that type's source.
A network callback must not be replaced by a call to ordinary `dbProcess`
that leaves a PACT-active record unfinished.

### Operational Baseline And Uncertainty

The downstream IOC source at
`6bedd223117f55b253c5834bdc50c013df1a9010` configures
`SessionTimeout=2000000` microseconds and `SessionRetries=1` in its
sector startup file. That timeout change is an existing operational mitigation,
separate from this module development. It does not set SCAN or establish a
two-second acquisition deadline.

User-supplied legacy observations on 2026-09-22 showed 88 PVs sharing 63 OIDs,
a 20-OID request limit, and a desired rate of 0.50 polls/second. Over the
reported 14:59:59 to 15:02:30 interval, the group error counter stayed at 341
while sends increased by 313 and replies by 312. The source timezone of those
reports was not supplied. These are supplied observations, not tests executed
by the author, and the counters have the limitations stated above.

The supplied packet summary showed repeated requests about one second apart
and responses arriving after the first second. It contained packet timing and
lengths, not decoded request identities. Late-reply/retry interaction is a
hypothesis; the cause of `security service 3 error parsing ScopedPDU`
remains unresolved. This project must not claim that changing SCAN ownership
fixes that parser error without separate evidence.

The supplied field observations do not verify the new mode. The local candidate
has executed the tests recorded above; no hardware pilot or deployment has run.

### Available Hardware For Planned Verification

The following inventory was retrieved through `ams-cli get-asset` on
2026-09-22. The owner identified all three devices as using SNMP. These are
inventory observations, not verified network endpoints or protocol settings.

| Asset tag | Model | Asset name | Current AMS location |
| --- | --- | --- | --- |
| T000398 | APC AP8932-NMC2 | APCPDU1 | B46-156 (Controls Lab) |
| T000525 | APC AP8932-NMC3 | Unassigned name | B46-156 (Controls Lab) |
| T001374 | Tripp Lite PDUMH15ATNET | TRIPDU1 | B46-156 (Controls Lab) |

Before hardware tests, record each live endpoint, firmware, enabled SNMP
version/security context, read-only OID subset, actual IOC/DB, and existing
poller. Do not derive live addresses or identical protocol coverage from AMS.
Exercise each device separately, then all three in one approved test IOC to
check shared-manager behavior. Select the first hardware target at G2.

### APC Firmware Baseline And Later Reverification

Observed in AMS on 2026-09-22 through `ams-cli get-asset`:

| Asset tag | Management card | AMS Firmware Version |
| --- | --- | --- |
| T000398 | NMC2 | `7.0.8` |
| T000525 | NMC3 | `rpdu2g:v2.3.1.6,aos:v2.3.1.1,boot:v1.5.0.2` |

These are inventory records; confirm the actual running firmware on each
device before its first hardware test. Keep results separately for each
asset and firmware version.

Decision Date: 2026-09-22. The owner plans firmware updates later, followed
by repeat testing. First retain each device's results on its current firmware.
After the later update, record the actual new firmware and repeat the same
applicable M6 checks with the same SNMP module, IOC executable, DB/DBD,
dependency versions, OID subset, protocol/security settings, SCAN,
timeout/retry settings, batch limit, observation duration, and acceptance
limits. Compare request/result/FLNK order, values and conversions, alarms,
valid-sample age, latency, and errors before and after the update. Record any
unavoidable configuration difference explicitly so it is not attributed to
firmware alone.

Firmware target versions, update dates, and repeat-test results are pending.
This later comparison does not authorize a firmware update now or make it
a prerequisite for the initial tests on the current firmware.

## Proposed Improvement

### Request And Completion Ownership

For an opted-in input record, a processing request should start a fresh
acquisition, not report an old cached value as that request's success.
Keep the record active until that acquisition reaches success or a terminal
error. Cache storage may remain an implementation detail, but cache presence
alone must not satisfy a new request.

The draft data flow is:

1. SCAN, a DB link, PINI, or an explicit processing request enters device
   support while the record is idle.
2. Device support creates a request identity, retains the record's completion
   state, sets PACT, and queues work without performing network I/O in the
   DB processing thread.
3. The scheduler selects compatible pending reads and deduplicates their OIDs.
   Each OID retains its own set of waiting record requests.
4. A batch enters the existing host serialization policy and Net-SNMP sends
   it. The batch limit is a maximum, not a target that must fill before send.
5. The response handler validates transaction identity, OIDs, types, errors,
   and lengths; it stores a result for the exact participating requests.
6. Completion is scheduled through the EPICS callback path. Device support's
   completion pass consumes that request's result and applies the record's
   conversion, UDF, and alarm rules without starting another GET.
7. Record support completes monitor and FLNK processing and returns the
   record to idle. A later processing request may start the next acquisition.

Success, send/open failure, final timeout, malformed response, and queue
rejection must each have an explicit completion path. Shutdown requires
ordered draining or cancellation before record storage becomes unavailable;
no callback may use a destroyed record.

### Timeline And Timing Controls

| Time or control | Intended meaning |
| --- | --- |
| t=0 | DB processing accepts a read request and returns with PACT true; the network operation continues asynchronously. |
| Before transmission | Queue wait and any bounded batching delay are part of acquisition latency. |
| Response arrives | Validate and save the result, then schedule completion; no need to wait for the next periodic SCAN. |
| Next SCAN while this record is active | The scanner still runs; ordinary processing does not create another acquisition for this active record. Verify any Base reprocessing behavior in the actual trigger path. |
| Next SCAN after completion | The now-idle record may request another acquisition. Other records have their own activity state. |
| `SessionTimeout` | Net-SNMP timeout input, in microseconds; distinct from queue wait, discovery, retry policy, and DB completion latency. |
| `SessionRetries` | Retry policy; neither a poll count nor a scan period. Establish total failure time from the shipped library and actual execution. |
| Legacy `PassivePollMSec` | Legacy autonomous polling cadence; must not silently schedule a new-mode-only OID. |
| Batch limit | Maximum OIDs per wire request; does not mean seconds or scans. |
| MDEL | Value monitor deadband; does not change SCAN, request scheduling, or freshness. |

Measure total latency as request-to-dispatch plus dispatch-to-terminal-result
plus terminal-result-to-record-completion. Record discovery and retry effects
separately where possible. Use a monotonic clock for durations and keep last
valid acquisition distinct from failed-attempt time.

A fanout initiating several asynchronous records does not itself constitute
an all-record completion barrier. A multi-OID response also does not guarantee
a physically simultaneous measurement or an atomic multi-record CA/PVA update.
Consumers needing a coherent all-record snapshot require an explicit, separately
accepted contract.

The owner selected per-record sequencing on 2026-09-22 (D4). For local passive
FLNK targets, the successful order is request acceptance, transmission, matching
terminal result, result/alarm application, FLNK processing, and then PACT clear.
"Completion before FLNK" means applying the result before downstream processing;
it does not mean clearing PACT before FLNK. On failure, FLNK still follows the
record type's actual completion path, and downstream logic must observe the
error rather than a falsely fresh value. A failure before transmission has no
dispatch event; it must still reach the defined record error-completion path.
A fanout-wide completion barrier is
not part of D4. Remote CA links require separate delivery observations and are
not evidence of synchronous local FLNK completion.

### Batching And Compatibility Requirements

- Batch only pending requests that share a compatible endpoint, SNMP version,
  security identity, security level, and context. Do not merge solely by
  textual OID or host name.
- Deduplicate the wire OID while preserving every waiting record's request
  identity, conversion, destination, and completion.
- Bound batching delay, queue capacity, and request lifetime. A partly filled
  batch must eventually dispatch. Define overflow behavior explicitly.
- Freeze batch membership at dispatch as the proposed freshness rule.
  Requests arriving after dispatch wait for another acquisition unless G1
  accepts a different, explicitly tested freshness contract.
- Do not add unrelated new-mode OIDs merely to fill a packet. A new-mode-only
  Passive record with no request must produce no periodic GETs.
- A legacy record or output readback sharing the same OID may still require
  polling. Its cache update must not complete an unrelated new-mode request
  or process an idle new-mode record.
- Preserve legacy output writes and readback behavior; a GET completion must
  never accidentally initiate a SET.
- Match responses using verified OID identity, not array position alone.
  Define outcomes for missing, duplicated, reordered, unexpected, and
  exception-valued varbinds.
- Reject late or duplicate results after terminal completion. A late response
  from an earlier request must not satisfy a later request.
- Audit lock ordering, callback queue exhaustion, session destruction, and
  the legacy 60-second stale-session cleanup. Completing record processing
  under the Net-SNMP session lock is not the proposed completion path.
- Do not equate asynchronous EPICS completion with the EPICS asyn module.
  This driver currently uses Net-SNMP directly.

### Decisions Still Required

The local candidate implements the contract in `docs/snmp-request.md`.
G1 retains broader acceptance of the following topics; implemented settings are
available, while production timing limits and the remaining matrix are open.

| Topic | Required design result |
| --- | --- |
| Mode selection | Separate input DTYP selected in D3; retain `Snmp` and the existing INP format. Finalize the new DTYP name, invalid configuration, startup diagnostics, and whether runtime changes are supported. |
| Type coverage | Map the pilot's real DB to supported input types; state treatment of waveform and unchanged output support. |
| Batch formation | Define compatible grouping, maximum wait, dispatch boundary, capacity, and duplicate-OID membership. Decide whether any explicit DB group identifier is needed. |
| Completion | Define ownership, generation identity, callback scheduling failures, error mapping, record timestamp policy, and teardown. |
| Scheduling | Define pending requests during PACT, runtime SCAN changes, legacy/new-mode coexistence, and GET/SET fairness. |
| Timing acceptance | Set numeric limits for queue wait, end-to-end latency, last-valid-sample age, recovery, healthy-host delay, and resource drift. |
| Pilot | Freeze the read-only record subset, observation duration, rollback triggers, and exact binary/DB pairing. |

## Working Procedure

1. Resume from this document and the current source tree. Preserve unrelated
   changes. Read the applicable repository instructions and skills.
2. Complete M1, including a source-backed state/lock diagram and a proposal
   for every G1 choice. Obtain plan acceptance and implementation authority
   as separate records before code changes.
3. Build the M2 real-path harness and establish the legacy baseline. M2 and
   M3 may be developed together after G1; new-mode completion claims require
   the harness to run against the actual candidate library.
4. Implement M3, then exercise M4 failures and resource lifetime. Use small
   changes whose behavioral contract and regression result are reviewable.
5. Run M5 on the final candidate tree. Have an independent review of the
   asynchronous state and locking design before acceptance; when the local
   review workflow applies, use its convergence procedure. A review finding
   is not a substitute for an executed test.
6. Prepare M6 in the downstream IOC repository, with its own owner and
   authorization. Use G2 to establish the pilot environment and allowed
   operations. The SNMP module and IOC configuration must identify each other
   by exact commits/artifacts.
7. After M6 evidence and G3 approval, execute M7 one IOC at a time. Record
   acceptance or rollback evidence before extending the deployment scope.

For each work item, retain the current plan and results in its detail below.
Before execution, replace proposed fixture names and test methods with actual
repository paths and reproducible commands. Record source commits, Base and
Net-SNMP versions, OS/architecture, configuration, start/end times, and result
artifacts. A failure remains a failure; a retry does not erase it.

Use the real built IOC, DB, device support, scheduler, Net-SNMP transport, and
CA client path. A controllable external SNMP peer or UDP fault injector is an
allowed device/network boundary. Do not mock internal reads, callbacks, queue
logic, or DB processing and call the result an integration test. Test SNMPv3
through a real SNMPv3 implementation, including discovery and security handling;
a simple v2c peer is insufficient evidence for v3.

The existing downstream `tests/snmp_peer.py`, `tests/test_pva.py`, and
`scripts/check_apcpdu_pvs.bash` are candidate reuse points, not proof of this
new mode. Inspect their actual coverage before reusing them. Keep runtime
evidence outside tracked source when it contains credentials or site identifiers;
the canonical result should name the safe evidence artifact.

## Milestone

### Work

| ID | Work unit | Type | Status | Ready | Deps | Done when / Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | Processing and configuration contract | Milestone | In progress | No | D1, D3, D4 | Concrete contract and acceptance proposal; [detail](#m1---processing-and-configuration-contract). |
| G1 | Design acceptance and implementation authority | External gate | Complete | No | M1 | Accepted API, limits, and authorized module scope; [detail](#g1---design-acceptance-and-implementation-authority). |
| M2 | Real IOC test harness and legacy baseline | Milestone | In progress | No | M1, G1 | Reproducible IOC/peer/client path and baseline evidence; [detail](#m2---real-ioc-test-harness-and-legacy-baseline). |
| M3 | Request-driven reads and OID batching | Milestone | In progress | No | M1, G1 | Fresh reads complete exactly once through EPICS; [detail](#m3---request-driven-reads-and-oid-batching). |
| M4 | Failure completion and diagnostics | Milestone | In progress | No | M3, G1 | Faults terminate safely with observable results; [detail](#m4---failure-completion-and-diagnostics). |
| M5 | Compatibility and candidate acceptance | Milestone | In progress | No | M2, M3, M4, G1 | Final candidate passes the accepted matrix; [detail](#m5---compatibility-and-candidate-acceptance). |
| G2 | Pilot environment and IOC change authority | External gate | Open | No | M5 | Pilot target, access, scope, and recovery procedure available; [detail](#g2---pilot-environment-and-ioc-change-authority). |
| M6 | Downstream IOC migration and pilot | Milestone | Blocked | No | M5, G2 | Actual IOC DB passes laboratory and device pilot checks; [detail](#m6---downstream-ioc-migration-and-pilot). |
| G3 | Production deployment window and acceptance limits | External gate | Open | No | M6 | Operator approves exact candidate, window, and rollback; [detail](#g3---production-deployment-window-and-acceptance-limits). |
| M7 | Controlled deployment and rollback | Milestone | Blocked | No | M6, G3 | Deployed artifact verified and rollback demonstrated; [detail](#m7---controlled-deployment-and-rollback). |
| M8 | Extensible SNMPv3 architecture | Milestone | In progress | No | D3, D4, D6, D7, D8, D9, D10 | Separated record/request/security responsibilities using native Net-SNMP facilities, explicit engine identity, restart-only credential activation, compatible worker bounds, proven runtime isolation and compatibility evidence; [detail](#m8---extensible-snmpv3-architecture). |

Ready describes dependency readiness only; it is not implementation authority.
Decision Date: 2026-09-24. All current implementation plans are accepted and
authorized for sequential implementation, review and correction. This authority
does not complete their verification or remove the physical conditions in G2/G3.

### Decisions

| ID | Decision | Decision Date |
| --- | --- | --- |
| D1 | Preserve the existing default and introduce an explicit opt-in request-driven read mode, with the PDU IOC as the first downstream target. | 2026-09-22 |
| D2 | Create the development handoff in this repository; implementation and deployment remain future work. | 2026-09-22 |
| D3 | Select a separate input DTYP for request-driven reads. Preserve the existing `Snmp` DTYP and INP syntax; do not select the new mode through an INP special flag. | 2026-09-22 |
| D4 | Preserve each record's request, matching response or terminal error, result application, and FLNK order. Follow Base completion ordering, with PACT cleared after FLNK; do not add a fanout-wide completion barrier. | 2026-09-22 |
| D5 | Use apcpdu branch refactor/snmp-db-processing at 6bedd223117f55b253c5834bdc50c013df1a9010 for the first test IOC. Use its existing alsu-epics-environment/1.3.0/debian-13/7.0.10 dependency tree, with the tested SNMP module built separately. | 2026-09-22 |
| D6 | Expand architecture design beyond optimizing the existing implementation: separate EPICS record processing, request ownership, and SNMPv3 security/session lifecycle so security capabilities can evolve while preserving D3/D4. Prepare the concrete design and migration/test plan; deployment and firmware changes remain outside this direction. | 2026-09-23 |
| D7 | Maximize reuse of stable Net-SNMP facilities. Delegate protocol encoding, authentication/privacy, key transformation, discovery, timeliness and wire retries to verified library APIs; keep EPICS completion and application policy in this module. Revise the architecture and implementation/test plan accordingly. | 2026-09-23 |
| D8 | Exclude live credential/profile replacement from this design; changes require IOC process restart. Add explicit engineID configuration with automatic discovery as the default, real legacy SET regression tests, and test completion criteria aligned with implementation availability. This authorizes the document amendments, not replacement module implementation or deployment. | 2026-09-23 |
| D9 | Preserve effective native timeout/retry settings and derive a finite worker watchdog bound. The finalized formula in [watchdog policy](decisions/ADR-20260923-worker-watchdog-policy.md) gives 150000 ms for inherited defaults, with 130 s of native intervals plus a selected 20 s allowance. Use the maximum endpoint requirement per worker; reject undersized explicit overrides without reducing native settings. Arm once before transaction IPC and never reset on progress. Numeric design is finalized; runtime/platform qualification, overall M8 plan acceptance and replacement implementation remain separate. | 2026-09-23 |
| D10 | Qualify the M8 candidate on Debian 13 and Rocky 8 instead of Debian 12 and Rocky 9, and declare Net-SNMP 5.8 in the shipped test profiles. Retained Debian 12 and Rocky 9 observations remain historical evidence, not current platform coverage. | 2026-09-24 |

### Milestone Details

#### M1 - Processing and configuration contract

Origin: db9ebf5 / M1
Identity History: none
GitHub Issue: none
Status: In progress

##### Summary

Define the exact relationship between one DB processing request, a batched SNMP transaction, and one record completion.

##### Scope

Inspect input record support, shared OID registration, host/group/session ownership, output readback, and the pilot DB inventory. Produce the state transitions, lock ordering, API proposal, compatibility matrix, and measured-timing acceptance plan here.

Out of scope: Implementing the new API, changing the legacy default, or promising group-wide atomic acquisition.

##### Completion Criteria

- Every G1 topic has a concrete proposal and a named unresolved choice, if any.
- The record-type matrix identifies supported, legacy-only, and rejected configurations.
- Each terminal outcome identifies result ownership, alarm/UDF handling, and record completion or shutdown disposition.

##### Dependencies And Decisions

- D1 fixes the compatibility boundary. G1 records acceptance and implementation authority dated 2026-09-24; source-contract review does not establish runtime acceptance.
- D3 selects a separate input DTYP. M1 entered In progress on 2026-09-22; the concrete contract below supplies record coverage, request lifetime, locking, batching and laboratory timing criteria.
- D4 fixes the per-record sequencing scope. It does not require different records to finish in their fanout submission order.

##### Accepted Mode Selection

Decision Date: 2026-09-22

Keep `DTYP="Snmp"` for legacy input processing and output support. Add a
separate DTYP for opted-in input records, preserving their existing INP
endpoint, OID, mask, length, and conversion settings. No new INP special
flag selects the mode. `SnmpRequest` is the selected DTYP for ai, longin and
stringin; waveform and outputs remain legacy-only.

The device-support initialization path identifies the request-driven
mode before PV/OID registration establishes polling requirements. Its read
path will distinguish initial acquisition from completion. Request ownership,
batch dispatch, and completion handling remain shared module responsibilities;
adding a DBD name alone does not implement the behavior. Existing output
registrations and SET semantics remain under the legacy contract.

##### Source Review And Remaining Contract Work

Review Charter: current plan with D3/D4; (1) Base completion semantics,
(2) DTYP/DBD/build integration, and (3) real-path sequencing tests and IOC
lifecycle. Review transport is self-review. The scope includes the module,
the referenced Base R7.0.10 sources, and downstream DB/test sources as evidence;
it does not authorize source changes or device operations.

Source inspection and actual-source preprocessing were performed on
2026-09-22. This is partial M1 / T1 evidence, not an IOC runtime result.
Base sources below are relative to
`EPICS-env/epics-base-src/modules/database/src/`; CONFIG_BASE_VERSION identifies
the inspected source as 7.0.10. No internal function was replaced for a check.

| Charter item | Class | Evidence and consequence |
| --- | --- | --- |
| 1 | Confirmed sequencing requirement | `std/rec/aiRecord.c`, `process`: preserve PACT on the first asynchronous return; apply conversion, alarms and monitors before `recGblFwdLink`, then clear PACT. The ai POD's Device Support Routines contains placeholders for asynchronous/return details, so use the actual record source for these rules. |
| 1 | Confirmed trigger distinction | `ioc/db/dbAccess.c`, `dbProcess` versus `dbPutField`, and `ioc/db/recGbl.c`, `recGblFwdLink`: an active periodic scan does not create a driver request; active CA PROC writes can set RPRO and cause a later processing pass. Test these separately instead of asserting that every active trigger is discarded. |
| 1 | Confirmed callback failure path | `ioc/db/callback.c`, `callbackRequest` and `ProcessCallback`: queue insertion can fail; successful callback processing takes the DB lock and calls record support. M1 must specify who retains and retries a rejected completion without double completion. |
| 1 | Confirmed fanout boundary | `std/rec/fanoutRecord.c`, `process`: All mode visits links in order without waiting for asynchronous acquisition completion. Use this source and the Base fanout POD rather than the diagnostic skill scaffold's claim that fanout stops at the first link error. |
| 2 | Required plan detail after D3 | `snmpApp/src/Makefile` already expands `snmp.dbd` from `base.dbd` and `devSnmp.dbd` and generates `snmp_registerRecordDeviceDriver.cpp`. New dset exports, installed DBD contents, generated registration and actual IOC loading must be tested together in M5 / T6. |
| 3 | Confirmed source finding; correction proposal required | `snmpApp/src/snmpMain.cpp` checks version components independently. Preprocessing this actual file against installed Base 7.0.10 headers selects the empty local `epicsExit`, so the call after iocsh returns does not itself invoke Base cleanup. M4 / T7 must distinguish EOF from explicit IOC exit and observe the module shutdown hook; source correction remains subject to G1. |
| 3 | Confirmed peer limitation | The actual downstream `tests/snmp_peer.py` is a v2c peer, logs PDU type/OIDs, and rejects SET. It lacks the generation/timing evidence required below and is not a v3 or successful-SET fixture without further implementation. |

The source-review table above records the 2026-09-22 baseline inspection.
The following contract consolidates D1/D3/D4 and the current candidate for
implementation and verification. It does not turn source inspection into
runtime acceptance.

##### Record And Configuration Contract

| Record and mode | Successful completion | Error and compatibility boundary |
| --- | --- | --- |
| ai / SnmpRequest, sR | Supply a representable 32-bit RVAL, return 0; Base applies its conversion and alarms before FLNK. | Preserve previous RVAL/VAL and UDF on acquisition or conversion failure; request READ/INVALID and return -1. |
| ai / SnmpRequest, without sR | Supply VAL through the existing mask/numeric conversion, return 2; Base skips raw conversion, handles alarms and runs FLNK. | Same failure contract; no silent integer narrowing. |
| longin / SnmpRequest | Supply a representable 32-bit VAL, clear UDF and return 0. | Preserve VAL and UDF, request READ/INVALID and return -1. |
| stringin / SnmpRequest | Supply a terminated VAL through the existing text-mask path, clear UDF and return 0. | Preserve VAL and UDF, request READ/INVALID and return -1. Preserve legacy quoted STRING representation and destination-width truncation. |
| ai, longin, stringin / Snmp | Existing cache/polling and conversion behavior. | No automatic migration or new request-completion guarantee. |
| waveform / Snmp | Existing buffer, FTVL, NORD and legacy processing behavior. | No SnmpRequest dset; do not apply ai's return-value rules to waveform or claim request-mode length/error semantics. |
| ao, longout, stringout / Snmp | Existing SET queue, native retries and output readback. | No SnmpRequest dset, asynchronous SET contract or output behavior change; real writable-output comparison belongs to M8/T17. |

The module's device-support alarm request is READ/INVALID; Base owns final
STAT/SEVR arbitration, UDF handling and configured value alarms. Record TIME
follows Base completion processing, including failures, and is not a valid-sample
timestamp. A successful-sample timestamp/age must advance only on successful
acquisition; its diagnostic implementation is required by M4/M8.

All supported request inputs use INST_IO and the existing host, community,
OID, mask, buffer length and optional flags. Request buffers accept 2..65536
bytes. Reject malformed/unresolvable links and I/O Intr initialization; do not
accept a generation for an invalid binding. A startup error is not a successful
request or a synthetic FLNK. Passive/PINI, periodic SCAN, CA PROC and local FLNK
use Base processing. Reject live binding/protocol identity changes; activate
changed DTYP, INP, security/profile or engine configuration by full IOC restart.
Legacy configuration compatibility and the M8 startup freeze are distinct:
the current candidate freezes RequestTimeoutMSec/RequestTrace at iocInit,
while the complete profile/endpoint freeze still belongs to M8.

The input completion order is acceptance, matching terminal result, device
conversion/result application, Base alarm/monitor handling, FLNK, then PACT=0.
PACT remains 1 at FLNK. Equal values still complete. A local source FLNK can
start the next dependent input; fanout orders initial calls but supplies no
cross-record completion barrier. Active periodic scans do not submit another
driver acquisition. CA PROC and put completion follow the separate Base RPRO
and notify paths and require separate M3/T6 tests.

##### Request State And Lock Contract

| Current request state | Entry and owner | Permitted next state |
| --- | --- | --- |
| Idle | Preallocated record slot; no completion owed. | Queued after begin accepts a new generation under the record lock. |
| Queued | Request mutex protects generation, absolute acquisition deadline and empty result; PACT is set before the initial record lock is released. | InFlight when session membership is frozen, or Ready with a terminal queue/deadline error. |
| InFlight | Exactly one session owns this generation's result opportunity. | Ready after one matching response or terminal error/deadline; a later session result cannot change it. |
| Ready | Slot owns copied text/native value or an explicit failure. | Scheduled after Base accepts one callback; failed callback insertion retains Ready. |
| Scheduled | One Base callback owns delivery; transport cannot replace the result. | Consuming after the callback obtains the record lock. |
| Consuming | Record support applies the private result once. | Idle after device support consumes it; the same callback retains the record lock through Base conversion, FLNK and PACT clear. |

The request mutex serializes terminal arbitration. A result arriving at or
after the acquisition deadline must not become success; the completion worker's
10 ms check interval is delivery latency, not permission to extend that deadline.
The current candidate checks expiry in service(); finish() deadline arbitration
must be checked and, if needed, corrected by M4/T2 before full acceptance.
The session pointer currently identifies ownership; M8 replaces that internal
identity with an opaque transaction plus generation/profile/worker epoch.

Accepted requests retain one immutable result until consumption. Missing,
duplicate or exception varbinds, PDU errors, open/send failures, native timeout
and conversion failure each produce one terminal error. Match by numeric OID,
not response position. Unrelated legacy cache updates never satisfy a request.
Requests for the same registered OID can share a session only if accepted before
membership freezes; later requests require another transaction. A request that
expires before it is claimed must not add an application GET. Current registration
keys are host text, community text and OID text; M8's complete endpoint/security
identity is the target for safe generalized batching, not an implemented claim.

One preallocated slot per input bounds concurrent record requests. A rejected
attempt receives a synchronous device-support error without accepting a new
generation or setting PACT with no owner. Callback insertion failure retains
the accepted result and retries every 10 ms without a second network request.
Full transaction/IPC admission limits are M8 requirements, not current queue
capacity claims. Batching selects pending request OIDs before legacy polls,
rotating its starting OID, and does not wait for a full packet.

| Path | Lock order and ownership |
| --- | --- |
| Initial read and result consumption | Base record lock, then request mutex; trace mutex may follow request mutex. |
| Network result | Existing host session mutex, then request mutex; no new request completion path takes a record lock. |
| Completion service | Request mutex and Base callback insertion; never a record or network lock. |
| Accepted Base callback | Release preliminary request mutex before taking the record lock, then request mutex to claim consumption; do not hold request mutex across record support. |
| Trace/report | Request-state snapshots release each request mutex before the final trace dump; no trace-to-request lock order. |

Legacy network-to-record interactions still exist outside the new completion
path and must not be described as globally removed. Request initialization is
startup-only. Disabling an idle record follows Base's disable behavior; changing
SDIS while an acquisition is active does not revoke the completion owner. The
callback finishes the already accepted acquisition through record support.

Graceful shutdown stops admission and completion scheduling before Base stops
callbacks, abandons outstanding acquisitions without synthetic FLNK, drains
accepted callbacks, and stops network workers before freeing reachable storage.
If draining fails, retain reachable storage until process exit and report
shutdown incomplete. EOF and explicit exit must both run this path. M8 adds
the independently bounded child shutdown specified in the watchdog ADR.

##### APC Source DB Inventory

Source: apcpdu commit 6bedd223117f55b253c5834bdc50c013df1a9010, source DBs
under apcpduApp/Db and loaders under iocsh. These are source-derived counts,
not a claim that any physical IOC has loaded every option.

| Source group | SNMP inputs | SNMP outputs | Trigger and dependent processing |
| --- | --- | --- | --- |
| device_info.db | 5 stringin | none | PINI/INFO_SCAN bo, default 10 s, starts fanout to the five passive inputs. |
| load_ap7800b.db | 1 ai, sR slope 0.1 | none | PINI/SCAN bo, default 2 s, starts PhaseCurr through fanout. |
| load_pdu3ev.db | 6 ai and 2 longin | 1 longout | PINI/SCAN bo, default 2 s, fans out to eight inputs. Bank1Load and Bank2Load each FLNK to its own calc. |
| outlet_read.template, CHAN 1..24 | 48 longin | none | Per-outlet PINI/SCAN bo fans out to status and command readback. Status mbbi observes its input via CPP MSS. |
| outlet_write.template, CHAN 1..24 | none | 24 longout | Soft mbbo writes via PP; command/status calcout records update command indicators, not the SNMP readback-to-command path. |
| sensor.db, optional | 1 ai and 1 longin | none | PINI/SCAN bo starts Temp/Humidity fanout; Temp uses sR slope 0.1. |

AP7800B plus device information has 6 SNMP inputs. PDU3EV with device information,
24 outlets and sensors has 63 inputs (7 ai, 51 longin, 5 stringin) and, with all
outlet writes enabled, 25 longout outputs. Without sensors it has 61 inputs.
The PDU3EV loader defaults SENSOR_EN to `#`; WRITE_EN controls outlet writes
only. MasterControlCmd_ is in load_pdu3ev.db and is loaded independently of
WRITE_EN. A read-only hardware trial must account for that real output binding.

Each OutletCmdReadback1..24 shares its command OID with OutletCmd1_..24_;
MasterControlReadback shares sPDUMasterControlSwitch.0 with MasterControlCmd_.
With outputs present, these 25 OIDs retain legacy polling even if their input
DTYP changes to SnmpRequest. The other 38 input OIDs in the sensor-enabled
configuration are request-only after migration. The idle-no-GET assertion must
therefore use a request-only OID; it cannot prohibit output-readback GETs.
Readback never processes or overwrites the operator command. Output callback
and SetSkipReadbackMSec behavior remain subject to the real SET baseline.

##### Laboratory Acceptance Contract

The existing M2-M5 and M8 tests remain required. Debian 13 is the local baseline;
Debian 12 and Rocky 9 are required target environments, with exact Base/compiler/
Net-SNMP/crypto identities. Protocol coverage is v1/v2c plus real v3 at each
explicitly configured security level/available algorithm; unavailable cells
remain explicit and cannot be reported as passing.

Use M2's normal 2 s scan, 0.1 s active-scan fixture, 2 s session timeout with zero
retries and 10 s action watchdog; fault cases use 200 ms/zero retries unless
testing retransmission. Keep 100 ordinary-order repetitions, 1000 immediate
repetitions, 20 pending-work exits and 60 s bounded pressure tests. One duplicate,
missing completion or order violation fails the case. Trace overflow invalidates
the audit. M8/T8 additionally requires a 400 ms acquisition deadline, faulted
completion below 1 s, and 1000 healthy reads with p99 at most baseline +100 ms,
maximum below 1 s and no false INVALID samples. M8/T12 requires one hour of
resource observation with descriptors returned to baseline and no post-warmup
growing memory trend. M8's 32-worker, 256-transaction/1 MiB queue and 256 KiB
frame limits are explicit capacity requirements for that implementation.

RequestTimeoutMSec defaults to 10000 ms (accepted range 1..3600000), independently
of D9's automatic 150000 ms worker watchdog at native defaults. These defaults
and laboratory deadlines do not promise production completion latency. G2/G3
still require measured device/site timing, workload, operating window and allowed
operations before pilot/production acceptance. No unresolved production value
is silently assigned by this contract.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-09-24; current plans accepted by the instruction to implement every milestone sequentially
Implementation Authorization: 2026-09-24; implement the current plan, obtain third-person and second-person reviews and apply findings; physical execution remains subject to G2/G3
Superseded Plan Artifacts: none

1. Trace the current input paths in devSnmp.cpp and registration/configuration structures in devSnmp.h and devSnmp.dbd; compare each supported type with EPICS Base R7.0.10 record support.
2. Map the actual PDU DB trigger, fanout, input/output readback, and conversion paths. Identify any shared OIDs that retain legacy polling.
3. Specify the new request state and lock ownership, including immediate replies, callback queue failure, timeout, late replies, disable/reconfiguration, and exit.
4. Specify the separate input DTYP selected in D3, its initialization/read entry points, and invalid-input behavior. Preserve existing INP syntax and keep examples explicitly proposed until implemented.
5. Resolve G1 choices with the owner and replace timing placeholders with numeric acceptance limits before the affected implementation proceeds.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Source contract | Trace every transition to the actual module and Base call sites; compare all supported input types. | Baseline source and Base R7.0.10 | No undocumented completion path or lock-order cycle in the proposed design. |
| T2 | DB inventory | Read the delivered downstream DB/templates and registration DBD; enumerate types, shared OIDs, and processing links. | Selected downstream IOC revision | Every pilot record has a defined mode and completion owner. |
| T3 | Design acceptance | Check the proposed configuration and failure matrix against every G1 topic. | This canonical detail | No unresolved choice is silently implemented; numeric limits are recorded before testing. |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | 2026-09-24 | Current module, request state machine and Base R7.0.10 record/dbProcess/fanout sources | Pass: source contract and independent review | Record/configuration, state and lock tables above; deadline-at-finish check is assigned to M4/T2; no new runtime result |
| T2 | 2026-09-24 | apcpdu source revision 6bedd223117f55b253c5834bdc50c013df1a9010 | Pass: source inventory and actual Base msi expansion | Actual source expansions: 63 inputs, 25 outputs, 25 shared OIDs; 27 fanouts cover the 63 inputs exactly once; no device operation |
| T3 | 2026-09-24 | M1/G1 and M2-M5/M8 contract | Pass: contract coverage and independent reader review | Mode/type/terminal/lock rules and laboratory criteria recorded; physical timing and operations remain explicit G2/G3 conditions |

##### Closure Evidence

- Decision Date: 2026-09-24. Local source-contract acceptance follows the
  independent source/DB verification, third-person review, bounded correction,
  and second-person reader PASS. The two stale authority clauses were corrected;
  no runtime source or required test was changed in this milestone.
- Reviewed contract SHA-256 before this evidence/status update:
  `074842a964364c1a582b7078ed31aaa33b9b672c1541ae460afb5a9a202d3e50`.
  Local reports: rev20260924_014647 and fup20260924_020116 in the active review
  session; their final files retain the exact source checks and msi invocation.
- Repository landing remains pending: the branch has no upstream and no push
  was requested. M1 remains In progress for that formal closure condition;
  its accepted local deliverable permits the authorized M2 work to proceed.
  Local contract commit: `029126824e846a623f9845299326cec08f8f7282`, observed
  2026-09-24; exact five-document inventory verified after commit. This is not
  remote landing evidence.

#### G1 - Design acceptance and implementation authority

Origin: db9ebf5 / G1
GitHub Issue: none
Status: Complete

##### Summary

The owner resolves the M1 choices and accepts the concrete current module plans before implementation. This gate affects M2-M5.

Named condition: Design acceptance and implementation authority.
Prerequisite evidence: M1.

Decision Date: 2026-09-24. The owner accepts the current M1-M8 plans and
explicitly authorizes their implementation, review and correction. M1 now
records the concrete record/state/lock contract, laboratory timing/resource
limits and protocol/platform matrix, verified by independent review. This
closes the design/authority condition; it does not mark any runtime matrix
cell passed or remove G2/G3's physical conditions.

##### Completion Criteria

- Mode syntax, record coverage, freshness/batch rules, error/teardown behavior, and lock ownership are accepted.
- Numeric timing/resource acceptance limits and the required protocol/platform matrix are recorded.
- Plan acceptance and implementation authorization are recorded separately in the affected details; a later material revision is accepted again.

##### Verification Results

| Observed At | Result | Evidence |
| --- | --- | --- |
| 2026-09-24 | Complete: current plans accepted and implementation authorized | Dated authority in all eight plans; M1/T1-T3 source-contract acceptance; physical G2/G3 conditions retained |

##### Closure Evidence

- Decision Date: 2026-09-24. Current plan acceptance and implementation authority are recorded separately; no unresolved local design choice remains. Runtime and physical acceptance remain in their named milestones/gates.

#### M2 - Real IOC test harness and legacy baseline

Origin: db9ebf5 / M2
Identity History: none
GitHub Issue: none
Status: In progress

##### Summary

Create a reproducible transport-to-record test path using the built SNMP module and real EPICS processing.

##### Scope

Add versioned test DBs, IOC startup, an external controllable SNMP peer or fault injector, a CA observer, and a runner with machine-readable failure status. Capture legacy behavior before testing the new mode.

Out of scope: Mocking internal device support or reproducing its logic in the test; treating PVA-only or build-only checks as transport verification.

##### Completion Criteria

- One documented runner starts the actual built IOC and peer, verifies readiness, runs assertions, and exits nonzero on failure.
- Baseline and candidate runs use the same published fixture definitions and isolated endpoints/PV names.
- Evidence records wire requests, request identities, record processing/completion, PACT, VAL/RVAL, alarms, timestamps, and resources as applicable.

##### Dependencies And Decisions

- M1 supplies the fixture contract and record matrix. G1 is Complete as of 2026-09-24; local implementation is authorized. M2 does not depend on completion of M3.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-09-24; current plans accepted by the instruction to implement every milestone sequentially
Implementation Authorization: 2026-09-24; implement the current plan, obtain third-person and second-person reviews and apply findings; physical execution remains subject to G2/G3
Superseded Plan Artifacts: none

1. Inspect the existing build and IOC executable targets; add the test application/DB and runner where the EPICS build can compile and install them.
2. Implement only the external peer/network boundary for controlled values, delays, losses, varbind anomalies, and duplicate/late packets.
3. Use a real SNMPv3 peer/library for v3 cases and isolate test credentials from operational credentials.
4. Build the baseline revision separately and run legacy fixtures before candidate comparison; label new-mode-only tests unavailable on the baseline.
5. Publish launch/cleanup commands, evidence locations, and version capture. Preserve failure evidence and terminate only processes created by the runner.

##### Concrete Harness And Sequencing Evidence Plan

The M2 runner and external peers are implemented. Existing flat DB paths are
retained; the table identifies the delivered artifacts. Extended M3-M5/M8
scenarios and repetition counts below remain acceptance criteria, not results
from the initial suites. This document is the sole test-management record.

| Artifact path | Responsibility |
| --- | --- |
| `tests/run_snmp.py` | Start owned peer/IOC/client processes, await readiness, apply the named scenario, assert results, retain evidence, and return a nonzero status on failure or incomplete coverage. |
| `tests/snmp_peer.py` | External v2c protocol peer with held/released replies, request IDs, per-OID generation values, duplicates, loss and response anomalies. Extend or port the inspected peer; do not import a sibling checkout at runtime. |
| `tests/profiles/loopback.json` | Declared Base/Net-SNMP versions, isolated local endpoints, PV prefix, timeout/retry/batch parameters and deadlines. Operational credentials never appear here. |
| `tests/profiles/snmpv3.json` | Real Net-SNMP snmpd-based v3 peer configuration and discovery/authentication scenarios, with synthetic local test credentials. Record supported security algorithms. |
| `tests/legacy_matrix.db`, `tests/sequence.db` | Legacy four-input/three-output matrix and request fixtures. Baseline and candidate use the same delivered legacy DB. SnmpRequest is unavailable on the baseline. |
| `tests/sequence.db`, `tests/sequence_miswired.db` | Passive request inputs with actual downstream audit records and a wrong-FLNK negative control. The initial suite has A-to-B and fanout cases; the extended three-record/PINI matrix remains M3 work. |
| `tests/legacy.db`, `tests/legacy_saturation.db`, `tests/protocol.db` | Shared legacy/request OIDs, saturated polling and actual native GET/SET/readback. Multi-host/context isolation acceptance remains M8 work. |
| `tests/ioc.py`, `tests/identity.db` | Produce each retained st.cmd, verify the loaded DBD/library and unique instance over CA, and stop owned IOC/repeater processes. |
| `tests/build_fixture.py`, `tests/snmp_agent.py` | Independent archive/candidate build provenance and real native snmpd with a transparent UDP observer. |
| `tests/src/sequenceProbe.cpp`, `tests/src/sequenceProbe.dbd` | Test-only downstream subroutine support that records each real FLNK invocation and its input snapshots. It observes the real record chain; it neither supplies SNMP results nor calls a substitute completion function. |

Wire this test support into the EPICS build with its own test IOC product,
including the real `devSnmp` library and installed DBs. Keep production
registration independent of test-only audit support. No new standard record
type or generated standard-record header is required for a new DTYP.

For each run, write `run.json`, `wire.jsonl`, `driver.jsonl`, `flnk.jsonl`,
`ca.jsonl`, `ioc.log`, and `results.json` beneath an owned
`work/snmp-tests/<run-id>/` directory. Record the source commit and dirty diff
digest, executable/library/DBD/DB checksums, actual loaded library paths,
Base/Net-SNMP/client versions, OS/architecture, profile, start/end times and
scenario seed. Trace overflow, missing events, missing test cases or premature
process exit make the run fail; a retry retains the original failure.

The driver trace must be bounded and disabled by default. Add observation
points to the actual candidate path for `request_accepted`, `dispatch`,
`terminal_result` and `result_applied`, carrying record identity, generation,
transaction identity, OIDs, result status and a monotonic event sequence.
It must not change scheduling, inject results, or replace callbacks. Validate
its identities against the independent external wire log and actual DB
consumer observations. Measure overhead separately before hardware acceptance.

The downstream audit record is a passive real FLNK target. Its links read the
source value, alarm and PACT without requesting another read. It increments
an invocation counter and snapshots those values on each invocation. Use
distinct controlled peer values per acquisition, and a separate unchanged-
value case, so monitors cannot stand in for a completion count. Preserve an
in-IOC sequence for causal ordering; do not sort different processes' wall
timestamps and call that a proof. Cross-process events correlate by request
and transaction identity, not arrival time at the Python observer.

For a successful local FLNK case, assert this partial order for each generation:

```
request_accepted < dispatch < terminal_result < result_applied < flnk_observed
```

At `flnk_observed`, the source value/alarm must already match that result and
the source PACT must still be 1. After processing settles, read PACT=0 through
the actual CA client. The settled-state read alone does not prove the preceding
order. For an accepted request that fails, assert terminal error before result
application before FLNK, with unchanged last-valid generation. Require dispatch
only if transmission was attempted; do not invent a wire event for a local
pre-send failure. Queue admission rejection is a separate record-processing
case: G1 must define its synchronous or asynchronous error return, without
counting rejected work as an accepted driver request. Exactly one result
application and one FLNK invocation are required per accepted request in these
fixtures; rejected work must also reach its defined alarm/idle state.

Use ordinary CA puts for the active-PROC scenario; separately exercise CA put
completion notification without assuming it has the same queuing behavior.
Wait for peer/driver events before injecting the next action, not an arbitrary
sleep. Readiness requires the owned IOC process and selected PVs to identify
the intended test instance. A successful TCP/CA connection alone is insufficient.

Proposed laboratory parameters: 2-second normal SCAN, 0.1-second active-scan
fixture, a peer-held response spanning five active scans, a 2000000-microsecond
normal session timeout with zero retries, and a 10-second per-action watchdog.
The 10-second idle observation uses a 15-second watchdog; the 60-second pressure
case uses at least 75 seconds. Total suite deadlines account for repetitions
and startup time. Fault cases override the session timeout to 200000 microseconds
with zero retries unless the scenario explicitly tests retries=1. Timing
watchdogs are test controls, not production acceptance limits. Release a held response
only after all intended active puts/scans are observed; missing preconditions
are a failed/incomplete test, never an assumed pass.

Run ordinary sequencing cases 100 times, immediate-response cases 1000 times,
and pending-work shutdown cases 20 fresh IOC starts. Run pressure cases for
60 seconds with explicit request limits. One ordering violation fails the
case; aggregate throughput or a high pass percentage cannot waive it. G1
still sets numeric queue, completion, recovery and cross-host latency limits;
the runner must reject an acceptance profile with those fields unset.

Implemented invocations; build independent inputs with tests/build_fixture.py
as described in tests/README.md. `SNMP_TEST_IOC` must name that actual
candidate or baseline executable. The baseline protocol run adds --dtyp Snmp
and the candidate legacy comparison adds --baseline-evidence with the successful
baseline run directory:

```bash
python3 tests/run_snmp.py --ioc "$SNMP_TEST_IOC" --profile tests/profiles/loopback.json --suite legacy
python3 tests/run_snmp.py --ioc "$SNMP_TEST_IOC" --profile tests/profiles/loopback.json --suite sequencing
python3 tests/run_snmp.py --ioc "$SNMP_TEST_IOC" --profile tests/profiles/loopback.json --suite failures
python3 tests/run_snmp.py --ioc "$SNMP_TEST_IOC" --profile tests/profiles/snmpv3.json --suite protocol
```

Execution order: build/registration checks; observer negative controls;
baseline legacy run; candidate sequencing; failure/pressure/lifetime;
final-candidate rerun on Debian 12 and Rocky 9; then G2-authorized hardware.
Local IOC tests do not require a production service installation. For the
hardware/service stage, record the actual IOC server OS and lifecycle method
instead of assuming that the CI OS or the controls skill's example server
describes the installed system. No service restart is implied by a test plan.

##### Observed Independent Legacy Baseline

Observed: 2026-09-22T18:39:59-07:00. The owner authorized proceeding with the
current APC PDU branch and its existing 1.3.0 dependency path. This run covers
baseline preparation only; the proposed request-mode harness and completion
contract are not implemented by this result.

| Item | Actual input or result |
| --- | --- |
| Build host | Debian 13, linux-x86_64 |
| Dependency tree | `/home/jeonglee/gitsrc/alsu-epics-environment/1.3.0/debian-13/7.0.10` |
| Module source | `snmp@db9ebf51bc81d6f63d9395513d94d60b3b7eda83` |
| Consumer source | `apcpdu@6bedd223117f55b253c5834bdc50c013df1a9010` |
| Retained build and evidence root | `/home/jeonglee/scratchpad/snmp-request-baseline` |
| Source preparation | Independent git archives of both commits, without working-tree or untracked files |
| Configuration | Explicit EPICS_BASE; consumer SNMP points to the scratch module; no INSTALL_LOCATION override; CHECK_RELEASE=NO and new-dtags retained |
| Build | Both actual top-level builds returned 0; no compiler warning/error lines found in either build log |
| Link resolution | IOC libdevSnmp resolves to the scratch module; other EPICS libraries resolve to the selected tree; Net-SNMP resolves to the host system library |
| Net-SNMP | `net-snmp-config --version`: 5.9.4.pre2 |
| Runtime test | Unmodified `apcpdu/tests/test_pva.py` and its shipped DB, loader, MIB and peer; 12 tests passed in 41.114 seconds |
| Coverage | Four loopback v2c peers; startup, values, CA/PVA mapping and metadata, timeout/recovery, alarm/monitor behavior, sensor recovery, checker failures, and GET-only wire policy |
| Installation check | No regular file under the selected 1.3.0 tree had mtime or ctime newer than the pre-build `.started` marker |
| Limits | No new DTYP, per-request sequencing proof, waveform coverage, successful SET fixture, SNMPv3 run, physical PDU run, or production IOC operation |

The first run failed at startup because the standard MIB directory was absent
from the test environment; the IOC could not resolve `enterprises` and all
four wire logs were empty. That failed result is retained. The second run
used the existing RFC1155-SMI and RFC1213-MIB files documented by the APC PDU
test procedure, copied from `/tmp/apcpdu-mibs` to the evidence root's
`standard-mibs/`, with hashes recorded. No fixture logic or driver code was
changed to obtain the passing result.

Reproduction uses the retained archive directories. Add the selected tree's
`base/bin/linux-x86_64` and `modules/pvxs/bin/linux-x86_64` to PATH, set
SNMP_MIB_DIR to the retained `standard-mibs/`, and set TMPDIR to the evidence
root. Run `make -j4` in the module copy and then the consumer copy; run
`python3 tests/test_pva.py` from the consumer copy. Keep successive test logs
under different names so another run cannot replace this evidence.

Evidence beneath that root: `run.json`, `snmp-build.log`, `apcpdu-build.log`,
`ioc-ldd.txt`, `ioc-readelf.txt`, `snmp-readelf.txt`, `inputs.sha256.json`
(56 artifacts), `standard-mibs.sha256.json`, `install-tree-changes.txt`,
`apcpdu-tests.log` (failed environment setup), and
`apcpdu-tests-with-mibs.log` (12 passing tests). Runtime evidence is in
`apcpdu-pva-3q3np7j_/`; the failed run is in `apcpdu-pva-kvg_8fnk/`.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Harness | Launch the shipped test DB with the compiled IOC, external peer, and actual CA client. | Isolated local UDP endpoints | A changing peer value reaches the real record/client path. |
| T2 | Harness negative control | Stop the external peer or return a deliberately wrong value and run the same assertions. | Same real IOC and fixture | The runner detects the fault and exits nonzero; no internal substitute is used. |
| T3 | Legacy baseline | Exercise every registered input type and simulated output/readback behavior before modification. | Baseline commit, declared Base/Net-SNMP versions | Observed legacy behavior is retained as comparison evidence, including known limitations. |
| T4 | Protocol coverage | Execute GET cases through actual v2c and v3 encoding, discovery, and authentication paths selected in M1. | External protocol-capable peers | Protocol coverage is observed and explicitly identifies any unavailable matrix cell. |
| T5 | Sequencing observer negative controls | Hold a real peer reply, verify no result/FLNK yet, then release it; repeat with an intentionally miswired delivered test DB variant and with trace loss. | Actual IOC, peer, audit records and runner | Correct chain passes; wrong downstream wiring and incomplete evidence return nonzero. No internal completion function is mocked. |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | 2026-09-24T02:41:06-07:00 | Debian 13, Base 7.0.10, native Net-SNMP 5.9.4.pre2; actual candidate IOC/CA/UDP | Pass: nine sequencing and ten failure/lifetime cases; unique instance, loaded binaries, trace/wire/FLNK and cleanup checks | M2 Local Harness Evidence below |
| T2 | 2026-09-24T02:40:34-07:00 | Same actual candidate with wrong external value | Pass: runner exits 1 on actual 909 versus expected 101 | wrong-value result below |
| T3 | 2026-09-24T03:18:46-07:00 | Independent db9ebf5 and candidate, same shipped legacy matrix | Pass: four input and three output paths, actual SET and bounded recovery; automatic comparison equal; candidate-as-baseline and inconsistent runtime evidence rejected | Provenance verification and accepted independent recheck below; original 12 APC baseline tests remain separate evidence |
| T4 | 2026-09-24T02:40:41-07:00 | Real private snmpd/native IOC, independent baseline and candidate | Pass: v1, v2c, v3 noAuthNoPriv/authNoPriv/authPriv GET, actual SET and readback; SHA/AES selected where required | Protocol runs below; not final M8 package/stress acceptance |
| T5 | 2026-09-24T02:40:44-07:00 | Actual IOC/peer/audit DB | Pass: proper chain passes, wrong FLNK and disabled trace each exit 1 for the intended observation failure | miswired and trace-loss results below |

##### M2 Local Harness Evidence

Observed: 2026-09-24. Candidate source is an independent working-copy snapshot
built after M1 local commit 0291268; baseline is an unmodified archive of
`db9ebf51bc81d6f63d9395513d94d60b3b7eda83`. Both actual builds returned zero
without compiler warning/error lines. Inputs are recorded individually in
`/tmp/snmp-m2-candidate-20260924-b/build-inputs.json` and
`/tmp/snmp-m2-baseline-20260924-a/build-inputs.json`.

Candidate libdevSnmp SHA-256:
`595c968366b81a4c55198870ca196952e6290141560db4b0df6384d09a539113`.
Baseline libdevSnmp SHA-256:
`8ee9ef595616d9d05905c1d11eed50e96ff8abc493a4d0ef9baedf1be8927667`.
Every successful case verifies its executable, DBD and actual loaded module
against that manifest, its selected Base libraries/clients, actual Base/native
versions and a fresh instance identity. The copied module source and current
harness/fixture identities are recorded separately.

Run directories below are relative to `work/snmp-tests/`. Each contains exact
configuration, input digests and machine-readable results. Its case directories
contain the actual IOC, CA and wire evidence, including original failures.

| Run | Directory | Observed result |
| --- | --- | --- |
| Baseline legacy matrix | `20260924T093959-qpfcvyt7` | One matrix case passes; four inputs and three real SET/readback types |
| Baseline native protocol | `20260924T093959-g8h3e4yk` | Five cases pass with Snmp inputs |
| Candidate legacy matrix | `20260924T094031-7vq8xje4` | Initial matrix case passes; retained before the stronger recovery/value comparison |
| Baseline comparison input | `20260924T094558-5uqbvhgf` | Full matrix passes with bounded observed readback-state sampling |
| Candidate automatic comparison | `20260924T094637-fektulfc` | Pass in 13.179 s; baseline-comparison.json records equal initial/changed/timeout/recovered data with the named exclusion |
| Candidate sequencing | `20260924T094031-le0eu1ud` | Nine cases pass in 18.909 s |
| Candidate failure/lifetime | `20260924T094031-27y1xklj` | Ten cases pass in 34.867 s |
| Candidate native protocol | `20260924T094031-k3xx73fw` | Five cases pass in 10.044 s with SnmpRequest inputs and legacy SET |
| Wrong value | `20260924T094032-wfvse75j` | Exit 1; 909 versus 101 assertion |
| Wrong FLNK | `20260924T094032-uj4elckc` | Exit 1; expected audit missing and wrong source PACT observed |
| Missing trace | `20260924T094032-uhuge74y` | Exit 1; missing driver trace despite two actual audit completions |

The legacy waveform includes native-text leading whitespace and quotes; the
actual CHAR NORD is 8 for space/quote/hello/quote. A controlled 500 ms stale
threshold exposes legacy input PACT waiting and output readback alarms without
changing production defaults. Timeout input STAT/SEVR can vary with Base active
scan timing. The automatic comparison excludes only timeout input STAT/SEVR;
all other sampled fields are compared. Sampling waits for actual expected
readback values and idle/no-alarm state, retaining every intermediate sample.
The baseline also exposed transient stringout INVALID values during normal
responses; the test measures eventual readback and does not claim that legacy
transients are absent or CA multi-field reads are atomic. Full final candidate
tests, repeated/pressure cases and M8 workers
are not implied by these initial results.

The pre-M2 cumulative candidate also built and ran all original 19 real IOC
cases on Debian 12/Net-SNMP 5.9.3 and Rocky 9/Net-SNMP 5.9.1, both Base 7.0.10.
All 38 owned IOCs reached module shutdown. Evidence:
`/tmp/snmp-milestones-w9_9lage/platform-results.json` and its per-platform build,
link and case logs. A failed lexical path comparison is retained; normalized
actual library resolution was subsequently checked. These are initial candidate
platform observations, not a final M5/M8 platform verdict.

##### M2 Independent Review And Provenance Verification

Observed: 2026-09-24. Independent report rev20260924_030510 reads the complete
34-file candidate and records fresh builds, 25 passing candidate cases, six
passing baseline cases and three intended failing observer controls under
`/tmp/snmp-m2-review-mswh41o3/`. The operator reader pass passes. Its single
P2 finding concerns baseline identity: the comparison admitted candidate
results in the baseline slot. The actual db9ebf5 comparison still passed.

Imported comparison evidence now requires the exact unmodified db9ebf5 archive,
consistent runtime/build executable, DBD and loaded-module identities, and the
existing matching profile/fixture checks. Only that exact baseline is exempt
from the candidate shutdown marker assertion in legacy and protocol tests.
The production module sources are unchanged by this correction; all 12 source
files match the prior candidate-b build manifest. Current observer/fixture
hashes are independently retained in each new run.

| Correction verification | Directory under `work/snmp-tests/` | Actual result |
| --- | --- | --- |
| Original baseline matrix | `m2-provenance-baseline-legacy` | Exit 0; one complete real matrix, 11.356 s |
| Candidate comparison | `m2-provenance-candidate-legacy` | Exit 0; one matrix, 11.226 s; equal=true and exact baseline commit/build identity recorded |
| Original baseline native protocols | `m2-provenance-baseline-protocol` | Exit 0; all five cases, 15.706 s |
| Candidate native protocols | `m2-provenance-candidate-protocol` | Exit 0; all five cases, 10.026 s |
| Candidate used as baseline | `m2-provenance-wrong-baseline` | Exit 1 after actual matrix execution; explicit unmodified-archive provenance assertion, 13.177 s |

Every IOC in these runs records exit 0 with no cleanup error. The wrong-baseline
failure is the intended comparison rejection, not a startup or teardown error.
Independent correction verification ran from 2026-09-24T03:16:38-07:00 through
03:18:46-07:00 with the actual public runner and the prior independently built
baseline/candidate executables. It passed 12 positive cases and rejected seven
negative cases: candidate-as-baseline, four separate runtime/build identity
mismatches, and two wrong-archive shutdown exemptions. Evidence is retained
under `/tmp/snmp-m2-correction-review-pq26dxfu/`, including exact argv and
timestamps in `execution-results.json`. No new build is claimed for this run.
All 19 owned IOCs exited zero; all 11 candidate lifetimes confirmed module
shutdown, and all 11 native agents exited without forced cleanup. Baseline
and deliberately mislabeled baseline binaries have no module shutdown marker;
the latter are correctly rejected rather than counted as successful cleanup.
The independent third-person and second-person follow-up passed at
2026-09-24T03:25:24-07:00. The baseline provenance finding is implemented and
verified; no correction defect remains. These results do not close later
stress, platform, worker or physical-device checks.

##### Closure Evidence

- Local harness and baseline verification, independent third-person execution
  review and second-person reader review are accepted on 2026-09-24.
  The provenance finding is implemented and verified. Handoff and commit scope
  passed independent cross-check on 2026-09-24. Local commit
  `e1878bc6aba94421448a6cc8035906e62716f28b` contains exactly 34 reviewed files;
  its stat and clean post-commit working tree were verified at
  2026-09-24T03:35:31-07:00. Remote landing and physical G2/G3 remain open.

#### M3 - Request-driven reads and OID batching

Origin: db9ebf5 / M3
Identity History: none
GitHub Issue: none
Status: In progress

##### Summary

Implement the accepted opt-in path from an idle record request to a fresh wire read and one EPICS completion.

##### Scope

Modify input device support, request ownership, pending OID selection, dispatch membership, and completion scheduling in devSnmp.cpp/devSnmp.h. D3 requires new device entries in devSnmp.dbd and matching exported dsets; use the existing DBD expansion and IOC registration build path.

Out of scope: Autonomous polling for new-mode-only records, opportunistic completion from stale cache, output SET redesign, or a new group-atomic API.

##### Completion Criteria

- A new-mode-only Passive input with no processing request generates no periodic GET.
- Every accepted request completes exactly once with a matching fresh result or terminal error.
- Only compatible requested OIDs enter a batch; limits and batching wait bounds are enforced.
- Legacy callers retain their default path; mixed-mode shared OIDs do not cross-complete.

##### Dependencies And Decisions

- M1 defines the behavior and API. G1 is Complete as of 2026-09-24; local implementation is authorized. Completion evidence uses M2 fixtures; implementation may proceed alongside M2 after G1.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-09-24; current plans accepted by the instruction to implement every milestone sequentially
Implementation Authorization: 2026-09-24; implement the current plan, obtain third-person and second-person reviews and apply findings; physical execution remains subject to G2/G3
Superseded Plan Artifacts: none

1. Add the separate input DTYP, its exported dsets and per-record request state; reject unsupported combinations at initialization and verify registration through M5 / T6.
2. Separate the initial request pass from the completion pass for each opted-in type. Preserve ai RVAL/VAL conversion return conventions and per-type semantics.
3. Introduce a bounded pending-request queue and OID-to-request membership. Separate its short critical sections from network operations and DB completion.
4. Dispatch only compatible pending work with bounded collection delay and the accepted membership freeze; preserve per-host serialization.
5. Save results by request identity, schedule EPICS completion, and consume each result once without recursively starting another GET.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Per-record lifecycle | With PINI=NO and SCAN=Passive, observe 10 seconds idle; request values 101 then 202, holding each response until accepted. Also repeat the same value twice. | M2 request DB, actual IOC/peer/audit path | No idle GET; every accepted request has the specified event order, one result application and one FLNK, correct value/alarm, PACT=1 at FLNK and PACT=0 after completion. Repeated values still complete twice. |
| T2 | Batch membership | Submit 1, 20 and 21 distinct OIDs with limit=20, then limit=1. Submit shared OID waiters before dispatch and supported distinct security/context groups. Hold an existing host transaction at the external peer when needed to establish pending work; verify preconditions from real traces. | M2 request/mixed DB and real protocol peers | No batch exceeds its limit; no duplicate wire OID within a batch; all and only its recorded waiters complete once. Partial batches dispatch within the accepted bound; incompatible contexts remain separate. |
| T3 | Late join | Hold generation A after dispatch; accept another record's request for the same OID, then release A and later generation B with a different value. | Real queue/Net-SNMP/DB path | The late waiter receives B, never A; A's FLNK cannot complete the late waiter. Record exact dispatch membership and both transactions. |
| T4 | Active periodic SCAN | Use SCAN=0.1 second and hold the first reply across five observed active scans; release and observe a later idle scan. No CA PROC writes in this case. | M2 sequence DB and real scanner | No second accepted acquisition during the first active interval; first FLNK occurs once. The later idle scan can start another request. A separate extended hold checks Base SCAN alarm behavior without treating that alarm as a new request. |
| T5 | Conversion and mixed mode | Run ai raw values 123/246 with LINR=SLOPE, ASLO=1, AOFF=0, ROFF=0, SMOO=0, ESLO=0.1 and EOFF=0; also test supplied-VAL ai, signed longin, empty/changing stringin and each accepted waveform FTVL/length. Include a legacy record and simulated output readback sharing OIDs. | Real records and simulated external outputs | ai yields 12.3/24.6 within the declared floating-point tolerance in raw conversion mode; each other type follows its own accepted contract. Idle new-mode records remain idle during legacy polls; read completion never emits SET. Values, lengths, alarm and last-valid generation are checked at FLNK. |
| T6 | Active CA PROC and RPRO | Hold one Passive request; send ten ordinary CA PROC puts while active and wait for their acknowledgments before release. Also run one put and separately a put-with-completion case. | Actual CA client, Base dbPutField and M2 sequence DB | For the ordinary PROC scenario, active puts set the Base reprocess condition without creating ten concurrent requests; one later reprocessing acquisition follows the first completion. Put-with-completion expectations are derived separately from its actual Base path before implementation acceptance. |
| T7 | Serial FLNK chain | Use A-to-auditA-to-B-to-auditB-to-C-to-auditC; all are Passive and every connection is a real FLNK. Each audit reads its source without processing it and starts the next input through its own FLNK. Hold/release A, then B, then C, with distinct values. | Delivered sequence DB and external peer | No B request before A's result application and auditA; no C request before B's and auditB. Each audit runs once and reads its source's completed value. Dependent requests are not incorrectly added to A's pre-dispatch batch. |
| T8 | Independent fanout | Submit A then B through local fanout links, with distinct hosts; hold A while allowing B to complete, then release A. Add a deliberately invalid-link variant and inspect subsequent real link processing. | Real Base fanout, two peers and audit records | Submission follows configured links; B may finish before A. Each record preserves its own sequence. The checker does not demand an all-record barrier or use the fanout FLNK as acquisition completion evidence. |
| T9 | Startup and reconfiguration | Cold-start with a PINI trigger/fanout and passive children; hold the first responses. Exercise SCAN changes idle/active and disable before a request and during pending work. | Actual iocInit/scanner/DB path | No derived FLNK value before its source result; no request lost between initialization and manager start. After G1 defines runtime-change behavior, every accepted pending request follows that contract without silent cancellation or duplicate completion. |
| T10 | Error completion order | Timeout A in an A-to-audit chain, then recover with a new value; repeat send failure and missing/type-invalid response cases. | Same real lifecycle and error paths as M4 | Each terminal failure applies the agreed error before one FLNK, preserves last-valid generation and reaches idle. Recovery is a new request with one success completion; stale data is not marked fresh. |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | 2026-09-24T04:23:34-07:00 | Debian 13.7, Base 7.0.10, Net-SNMP 5.9.4.pre2; actual IOC/UDP/CA/FLNK | Executed cases PASS; independent review PASS (2026-09-24) | `m3-lifecycle-full-b`: 10 s idle, 100 held/repeated-value cycles and 1000 immediate cycles; `m3-final-idle-positive`: final harness, 100 cycles. Input-version distinction below. |
| T2 | 2026-09-24T04:12:53-07:00 | Same candidate; held real host transaction and batch.db | Executed cases PASS; independent review PASS (2026-09-24) | `m3-batch-full-b`: 1/20/21 OIDs, shared waiters and distinct supported communities, each at limits 20 and 1; 100 cycles per case. Exact membership and bounded dispatch checked. Generalized v3 contexts remain M8. |
| T3 | 2026-09-24T04:21:35-07:00 | Same candidate; held UDP replies and actual request generations | Executed case PASS; independent review PASS (2026-09-24) | `m3-lifecycle-full-b/test_late_waiter-*`: 100 cycles, separate wire identities and values for the dispatched owner and late waiter. |
| T4 | 2026-09-24T04:21:35-07:00 | Same candidate; actual Base periodic scanner and read-only LCNT observer | Executed cases PASS; independent review PASS (2026-09-24) | `test_five_active_scans-*` and `test_extended_scan_alarm-*`: 100 cycles each, five/eleven observed active scans, no active PROC puts, Base SCAN/INVALID on extended hold and subsequent request recovery. |
| T5 | 2026-09-24T04:18:01-07:00 | Same candidate; actual ai/longin/stringin, legacy input/output readback and six waveform combinations; separate db9ebf5 IOC | Conversion/value/alarm cases PASS; dedicated last-valid-generation checks passed under M4 on 2026-09-24 | `m3-conversion-full`: 100 mixed cycles plus initial text request, 100 waveform cycles; independent `m3-wave-baseline-full-c` comparison equal. The original M3 audit did not expose the dedicated diagnostic field. Later m4-conversion-diagnostics-a verifies it for 401 real generations, including failed empty-mask conversions. |
| T6 | 2026-09-24T04:21:35-07:00 | Same candidate; real caput and caput -c, Base dbPutField/dbNotify | Executed cases PASS; independent review PASS (2026-09-24) | Active one-put and ten-put cases, 100 cycles each: RPRO produces one later acquisition. Put completion separately waits for actual PPN ownership, then completes its own held acquisition; 100 cycles. |
| T7 | 2026-09-24T04:21:35-07:00 | Same candidate; lifecycle.db and actual serial FLNK chain | Executed case PASS; independent review PASS (2026-09-24) | `test_serial_chain-*`: 100 A/auditA/B/auditB/C/auditC cycles, held responses, values and ordered wire/FLNK observations. |
| T8 | 2026-09-24T04:21:35-07:00 | Same candidate; real Base fanout, two distinct UDP peers and actual audit records | Executed cases PASS; independent review PASS (2026-09-24) | `test_two_host_fanout-*` and `test_invalid_fanout_link-*`: 100 cycles each; B completes while A is held. Pre-correction failure and receive-lock correction evidence below. |
| T9 | 2026-09-24T04:21:35-07:00 | Same candidate; actual iocInit/PINI, scanner and DISA | Executed cases PASS; independent review PASS (2026-09-24) | `test_pini-*`: 100 fresh IOCs with held startup responses; `test_disable-*`: 100 cycles, disable before and during work; active/idle SCAN changes in scanner cases. |
| T10 | 2026-09-24T04:21:35-07:00 | Same candidate; real UDP loss/missing/type-invalid responses and outer libc socket failure | Error/value/order cases PASS; dedicated last-valid-generation checks passed under M4 on 2026-09-24 | `test_terminal_errors-*`: 100 prime/error/recovery cycles per fault; `test_transport_failures-*`: 100 cycles each for socket-open/send failure. The original M3 checks covered last value and failed application. Later m4-lifecycle-final-a also checks the dedicated successful-generation field across the complete 100-cycle fault/recovery cases. |

##### M3 Local Verification Evidence

Evidence root: `work/snmp-tests/`. Each run contains its invocation metadata,
start/end times, source and fixture hashes, expected case list and outcome in
`run.json`/`results.json`, with raw IOC, peer, CA and runtime-exit evidence
under the named case. The aggregate `m3-acceptance-summary.json` is derived
from those files; it is not another execution. The public reproduction path
is `tests/run_snmp.py`, documented in `tests/README.md`.

The isolated candidate build is `/tmp/snmp-m3-candidate-20260924-b`;
build-manifest SHA-256 is
`412ea20a548abf500fcbb3cb87073dad9129212678818e7027094fe5246135db`.
Its actual IOC, DBD and module hashes are respectively
`be5714ae8503967c53f7360b7feabc5dedc634e7c173c6816e82c42b0d24f5ca`,
`25a12fc46a7fa5519ddb6598b32bf1e3898222c27052c7b340b568b2e1649de0`
and `5c32582451948d6bd26454a777538cde8f948c176b02e75cc4b58352e55e13b8`.
The baseline is a separate unmodified archive of the full source-baseline
commit, built at `/tmp/snmp-m2-baseline-20260924-a`; manifest SHA-256
`660f6ea6ad936b193328e48c192f4a1324d15b637a81bf362f1413d4eed2196a`.
Both builds use the selected installed Base 7.0.10 without writing it.

| Run | Cases | Request generations / FLNK audits | Owned IOCs with exit 0 and no cleanup error | Result |
| --- | ---: | ---: | ---: | --- |
| `m3-lifecycle-full-b` | 15 | 4802 / 4802 | 114 | PASS; default 100 ordinary / 1000 immediate repetitions, 954.636 s |
| `m3-batch-full-b` | 10 | 10200 / 10200 | 40 | PASS; 100 repetitions per case, 364.202 s |
| `m3-conversion-full` | 2 | 401 / 401 | 2 | PASS; 100 repetitions per case, 241.932 s |
| `m3-final-idle-positive` | 1 selected | 100 / 100 | 1 | PASS; final harness, 100 repetitions; selected-case metadata is partial |
| `m3-wave-baseline-full-c` | 1 selected | legacy path | 1 | PASS; six waveform combinations over 100 cycles; selected-case metadata is partial |
| `m3-legacy-baseline`, `m3-legacy-candidate` | 1 each | legacy path | 2 | PASS; independent observations compare equal |
| `m3-sequencing`, `m3-failures`, `m3-protocol` | 9 / 10 / 5 | suite-specific assertions | 24 | PASS; existing real-path regressions |

The three full new suites account for 15403 accepted generations and 15403
FLNK observations, including 500 terminal-fault INVALID observations and 17
empty-string mask failures. Every generation is matched to its actual wire
transaction or uniquely observed outer socket failure. Each matching FLNK
observes PACT=1 after application, followed by completion with PACT=0. The
largest individual IOC trace contains 6000 events, below the 8192-event
capacity; the acceptance checker requires no loss or overflow. All 184 IOCs
in the table have recorded exit 0 and no cleanup error. The five native
protocol agents also exited 0 without forced termination.

Waveform equality covers STRING/CHAR/UCHAR at NELM 16 and 128, including
the first STRING element, complete CHAR/UCHAR arrays, existing byte-oriented
NORD, PACT, UDF and alarm fields for 100 cycles. The baseline
observations SHA-256 is
`4ff3bbc037d411f9c462004d6b746429f41259928f17a97be6e9ae12dfdc9fab`.
The empty string's READ/INVALID result preserves existing mask behavior and
last value; both real legacy and request stringin paths agree, and the next
nonempty result recovers. The native `snmpget` result in
`m3-native-empty-i452dss5/result.json` confirms the absent `STRING:` prefix.

Input versions are explicit: lifecycle-full-b started before the three final
negative-control branches were added to the public harness. Its recorded
fixture hashes therefore differ in README, request_cases.py, run_snmp.py and
test_lifecycle.py. The final positive idle branch was subsequently executed
for 100 cycles, and all three final negative controls were executed. The
batch run differs only in README; conversion, baseline comparisons and the
listed regression runs identify the final frozen harness. Independent review
executes that frozen harness separately; these runs are not relabeled as the
same input version.

`m3-negative-wrong-value`, `m3-negative-miswired` and
`m3-negative-trace-loss` each returned 1 for the intended value, missing
AuditA or missing trace assertion. The five real runner invocations in
`m3-provenance-et3_jr3g/execution.json` reject candidate-as-baseline and
corrupted runtime manifest/IOC/DBD/module identity, each for its intended
reason; the actual IOCs still exited cleanly. No driver, Base or Net-SNMP
internal function was replaced.

The pre-correction `m3-lifecycle-full-a` failed the two-host fanout case:
B could not dispatch until A's approximately two-second native wait ended.
The receive task held the global native-session mutex while waiting in
`select`. It now polls readiness without blocking under that mutex and
sleeps outside it. Both distinct-host fanout variants passed their complete
100-cycle profile afterward. Blocking native session-open/discovery remains
an M8 isolation requirement. The interrupted `m3-batch-full-a` has tool exit
130 and no final runner result; it is not accepted evidence and is not
classified as graceful cleanup.

Independent third-person execution and second-person maintainer review passed
on 2026-09-24 at 04:43:46 -0700 without a new finding. Fresh isolated builds
of the candidate, exact db9ebf5 baseline and exact e1878bc M2 revision are
recorded under `/tmp/snmp-m3-review-opriy0my/`. The public runner passed 37
positive cases: lifecycle/batch/conversion at 3/3/6 cycles, legacy comparisons,
native v1/v2c/v3 profiles, and separate default-count immediate (1000) and
two-host fanout (100) cases. Selected and cycle-override runs remain partial;
the full ordinary repetition evidence above remains separately identified.
Four intended negative executions returned 1 for wrong value, missing audit,
missing trace and candidate-as-baseline rejection. The same real fanout test
against e1878bc failed before A's response was released, with a measured
2.001586214 s delay before B dispatch. This comparison did not replace any
internal driver path. The review's `execution-results.json`,
`fanout-execution.json`, `protocol-execution.json` and `evidence-audit.json`
retain commands, times, results and runtime/build associations. All 45 newly
started IOCs and the 184 retained positive-run IOCs have exit 0 and no cleanup
error; five newly started native agents exited 0 without forced termination.
All 18 reviewed implementation/document hashes remained unchanged.
Handoff correction cross-check passed at 2026-09-24T05:07:56-07:00.
The two derivative findings were corrected without a runtime change.
The original M3 value/event assertions did not expose dedicated valid-generation
or age diagnostics. Later M4 conversion/lifecycle runs verify these fields on
the final M4 source; these are distinct executions.
No final platform, resource-soak, physical-device or deployment acceptance
follows from this local evidence.

##### Closure Evidence

- Local M3 implementation and its stated verification boundary passed
  independent third-person and second-person review on 2026-09-24.
  Handoff cross-check passed on 2026-09-24. Local commit
  `68294c2a91e74b7559aea0aa1e1ae0fb87e2aa8a` contains exactly the 19 reviewed files;
  commit scope and a clean working tree were verified at 2026-09-24T05:09:25.103891-07:00.
  Remote landing remains pending.
  T5/T10 dedicated successful-generation checks passed under M4 on 2026-09-24.
  M3 is not marked Complete without remote landing; no required check is waived.

#### M4 - Failure completion and diagnostics

Origin: db9ebf5 / M4
Identity History: none
GitHub Issue: none
Status: In progress

##### Summary

Ensure failure, contention, and teardown terminate requests safely and expose valid acquisition progress.

##### Scope

Handle open/send failure, queue rejection, response anomalies, final timeout, callback scheduling failure, duplicate/late replies, session expiry, and shutdown. Add diagnostics needed to distinguish requests, valid results, errors, and completion latency.

Out of scope: Claiming a fix for the observed ScopedPDU error without a reproducer; replacing Net-SNMP security processing; unrelated logging redesign.

##### Completion Criteria

- Every running-record failure path returns to a defined idle/alarm state within the accepted deadline, with no indefinitely active PACT.
- No duplicate completion, use-after-free, callback-after-teardown, or unbounded queue/resource growth is observed.
- Diagnostics distinguish valid data from attempts/timeouts and permit per-interval measurement.
- Healthy-host delay under a silent peer is measured against the accepted limit; a failure is not waived as normal polling.

##### Dependencies And Decisions

- M3 provides the real request lifecycle. G1 is Complete as of 2026-09-24; local implementation is authorized. Global session-lock changes beyond the accepted contract require a revised plan.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-09-24; current plans accepted by the instruction to implement every milestone sequentially
Implementation Authorization: 2026-09-24; implement the current plan, obtain third-person and second-person reviews and apply findings; physical execution remains subject to G2/G3
Superseded Plan Artifacts: none

1. Centralize terminal-result ownership so error paths cannot bypass a waiter or retire it twice.
2. Validate OID, type, length, exception, and transaction association; define batch-level failure versus per-OID success exactly as accepted in M1.
3. Handle callback queue rejection without leaving PACT active forever; establish an executable overload/failure test without mocking the internal callback function.
4. Audit session destruction, stale-session cleanup, cancellation, and IOC exit against outstanding network work and scheduled callbacks.
5. Expose queue depth/age, active requests, valid/failed completions, last valid sample age, and latency components; preserve legacy report interpretation or document changes.
6. Measure the manager-wide lock effect with one silent host and one healthy host. If accepted limits cannot be met, report the measured constraint before expanding the transport design.
7. Resolve the snmpMain.cpp EOF exit-path finding under G1 and specify explicit exit, EOF and forced process termination as different lifecycle cases. Prove graceful hook entry and worker/callback shutdown; a dead PID alone is not cleanup evidence.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Transport failures | Use external loss/delay and real socket/resource failure conditions for open, send, retry exhaustion, and recovery. | Real IOC, Net-SNMP, fault injector | Each request terminates once; alarms and subsequent recovery match the contract. |
| T2 | Response validation | Inject missing/extra/reordered/duplicate OIDs, exception values, wrong types, and malformed responses through the protocol boundary. | Real transport parser and input support | No wrong-record value assignment or false valid-sample advancement; all affected requests finish. |
| T3 | Late/duplicate results | Delay a response past terminal failure, start the next request, and deliver old/duplicate packets. | Real transport and generation tracking | Old traffic cannot complete or overwrite the new request. |
| T4 | Queue/callback pressure | Saturate real pending and callback queues using the shipped runner and observe rejection/recovery. | Isolated IOC under bounded stress | Accepted capacity holds; all accepted work completes or fails without stuck PACT. |
| T5 | Concurrency/lifetime | Run immediate responses, mixed hosts, shared OIDs, and repeated IOC shutdown/start during pending operations. | Real IOC with available memory/thread diagnostics | No deadlock, invalid access, stranded callback, or growing resource trend. |
| T6 | Timing/accounting | Compare raw wire and record evidence with diagnostic deltas under success, failure, and a silent second host. | Same real path | Valid age/counts and measured healthy-host delay satisfy the accepted definitions. |
| T7 | Actual shutdown entry | Start the built test IOC with pending work; test explicit IOC exit and terminal EOF separately over 20 starts. Observe the real module shutdown hook and worker/callback disposition. Test forced termination only as crash recovery. | Built snmpMain.cpp/Base/driver path with owned PTY and processes | Graceful routes reach the actual cleanup path with no callback after storage teardown. Forced termination is never reported as graceful cleanup. Record the pre-fix EOF behavior separately. |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | 2026-09-24T06:06:09-07:00 | Debian 13.7, Base 7.0.10, Net-SNMP 5.9.4.pre2; real IOC/UDP/CA/FLNK | Executed cases PASS | m4-lifecycle-final-a: 100 cycles each of socket-open/send failure and recovery. m4-robustness-full-b: 100 retry-exhaustion cycles, initial plus two native retries. Real outer transport faults, no internal substitute. |
| T2 | 2026-09-24T05:57:58-07:00 | Debian 13.7, Base 7.0.10, Net-SNMP 5.9.4.pre2; real IOC/UDP/CA/FLNK | Executed cases PASS | 12 response variants, 100 prime/fault/recovery cycles each over 21 records. Wire identities, per-record value/alarm, one FLNK and valid-generation preservation checked. Largest trace is 7680 events, below 8192. |
| T3 | 2026-09-24T05:57:58-07:00 | Debian 13.7, Base 7.0.10, Net-SNMP 5.9.4.pre2; real IOC/UDP/CA/FLNK; owned-thread OS suspension | Executed cases PASS; real M3 regressions FAIL as expected | 100 old/duplicate-reply cycles and two absolute-deadline boundary cases pass. Same real M3 path fails late-result SEVR and expired-queued-GET assertions. |
| T4 | 2026-09-24T05:50:35-07:00 | Debian 13.7, Base 7.0.10, Net-SNMP 5.9.4.pre2; real IOC/UDP/CA/FLNK | Executed case PASS | 60 s real Base callback pressure with queue size 2 and 21 record slots; immutable ready result, actual overflow/retry, active-PROC/RPRO recovery. 252 accepted generations and 252 FLNK audits. Current record-slot capacity, not future M8 queue limits. |
| T5 | 2026-09-24T06:09:22-07:00 | Debian 13.7, Base 7.0.10, Net-SNMP 5.9.4.pre2; real IOC/UDP/CA/FLNK; ASan module/IOC, owned PTY | Executed local cases PASS; one-hour and thread-sanitizer qualification remain M8 | Final ordinary lifecycle/robustness/pressure/accounting and final ASan protocol/failures/teardown/legacy/waveform runs pass. No sanitizer report or cleanup error in accepted runs. Module/IOC instrumented; installed Base/native libraries are not. |
| T6 | 2026-09-24T05:53:52-07:00 | Debian 13.7, Base 7.0.10, Net-SNMP 5.9.4.pre2; real IOC/UDP/CA/FLNK | Executed cases PASS | Trace-on/off counters, queued/active totals and age, valid-generation preservation, phase latencies and 1000 healthy requests alone and with a silent peer. m4-conversion-diagnostics-a checks failed conversion cannot advance valid state. |
| T7 | 2026-09-24T05:54:26-07:00 | Debian 13.7, Base 7.0.10, Net-SNMP 5.9.4.pre2; real IOC/UDP/CA/FLNK; ASan module/IOC, owned PTY | Executed cases PASS; forced termination separately classified | 20 starts for each EOF/explicit-exit x network/callback-pending variant: 80 graceful, 20 intentional SIGKILL plus 20 fresh recoveries, and two candidate ASan Base-exit observations. Separate archived-baseline observations are in m4-eof-baseline-d. Ordered shutdown markers, real PTY and no post-entry FLNK checked. POSIX baseline EOF interpretation resolved below. |

##### M4 Local Verification Evidence

Evidence root: `work/snmp-tests/`. Each run retains actual argv/cwd,
start/end times, source/harness identity and results in `run.json` and
`results.json`, with raw IOC, wire, trace, FLNK and runtime-exit records.
`work/m4-acceptance-summary.json` derives counts/hashes from these executions;
it is not another execution. Public reproduction uses `tests/run_snmp.py`
with the suites documented in `tests/README.md`.

The final ordinary build is `/tmp/snmp-m4-candidate-20260924-g`, manifest
SHA-256 `9655fc4db741e48eb4dc3c5e9914d0766718055d6f99357cca38a2f1955c9e43`.
Test IOC, production IOC and module SHA-256 values are respectively
`d6241ea6a5a8156f6a844f6c108b560603ecb42ff8ca8cfcc8e50baae48d661d`,
`1d37db10bdc5ab139ed7142024327273c30349ea6ba37b431c89173a53c26d16` and
`aa1a93ed723ab9beceddb3ef7fa7df2dbc14e8d49a5d89691774a9eaa29592ed`.
The final ASan build is `/tmp/snmp-m4-asan-20260924-d`, manifest SHA-256
`bb0d53923762c9776f8d14db3f88a9d90efdb36600285a525459fbaa89ccc3df`;
test IOC and module hashes are
`f6d3d91619a646a2f634c984807f42298654e7fc1c95965de2f6ed1260d113e2` and
`e6b291583db23d19df9fe35a8aa2fe6d40c171ccc24b8ccd3341050ad128922e`.
Both use test DBD SHA-256
`25a12fc46a7fa5519ddb6598b32bf1e3898222c27052c7b340b568b2e1649de0`.
The accounting total assertion changed after these builds without a production
source change. Runtime manifests identify the exact harness; earlier runs
are not claimed to have identical complete fixture hashes.

| Run | Cases | Persisted accepted trace events / FLNK audits | IOC exits 0 / intentional SIGKILL | Result |
| --- | ---: | ---: | ---: | --- |
| `m4-lifecycle-final-a` | 15 | 4802 / 4802 | 114 / 0 | PASS; 100 ordinary / 1000 immediate repetitions |
| `m4-robustness-full-b` | 16 | 77509 / 77509 | 64 / 0 | PASS; 100 ordinary repetitions; two OS deadline cases |
| `m4-pressure-final-a` | 1 | 252 / 252 | 1 / 0 | PASS; 60-second pressure |
| `m4-accounting-final-b` | 3 | 2012 / 2015 | 22 / 0 | PASS; 1000 requests per timing mode; three trace-disabled FLNK audits |
| `m4-conversion-diagnostics-a` | 1 | 401 / 401 | 1 / 0 | PASS; selected mixed case, 100 cycles |
| `m4-asan-protocol-b` | 5 | 10 / 0 | 5 / 0 | PASS; real native v1/v2c/v3 |
| `m4-asan-failures-a` | 10 | 17 / 15 | 10 / 0 | PASS; two requests abandoned by shutdown |
| `m4-asan-teardown-a` | 6 | 100 / 20 | 102 / 20 | PASS; shutdown abandons pending work; twenty recovery FLNK audits |
| `m4-asan-legacy-a` | 1 | 0 / 0 | 1 / 0 | PASS; actual db9ebf5 comparison |
| `m4-asan-wave-a` | 1 | 0 / 0 | 1 / 0 | PASS; selected waveform case, 100 cycles |
| `m4-legacy-baseline-a` | 1 | 0 / 0 | 1 / 0 | PASS; separate db9ebf5 IOC |
| `m4-wave-baseline-a` | 1 | 0 / 0 | 1 / 0 | PASS; separate db9ebf5 IOC, selected 100-cycle case |
| `m4-eof-baseline-d` | 1 | 0 / 0 | 2 / 0 | PASS; separate db9ebf5 IOC, two terminal routes |

Selected-case metadata remains partial. Graceful shutdown abandons pending
acquisitions without new FLNK callbacks; its persisted accepted-event/FLNK
counts do not claim completion equality. The trace counts omit three
trace-disabled accounting acquisitions and twenty forced-exit pending
acquisitions. Final accounting diagnostics record 2015 accepted acquisitions,
matching its 2015 FLNK audits; only 2012 accepts appear in the trace.
Intentional SIGKILL is crash evidence only. All accepted
runtime records have no cleanup error. Earlier `m4-teardown-full-b` passed
six cases against candidate-f, before the final atomic fields; it is not
final candidate-g evidence. Final-source teardown is covered by final ASan
and the independent fresh ordinary/ASan builds.

The 62 pressure samples span 61.756470277 s: FD count stays 8, threads stay 23,
RSS ranges 18284-18292 KiB. This passes the declared short-test bound, not a
one-hour plateau. For 1000 healthy requests alone, p99 is 0.044152264 s and
maximum 0.048467193 s. With a silent peer, p99 is 0.045753093 s and maximum
0.053442885 s. The p99 increase of 0.001600829 s is below 0.1 s and the maximum
is below 1 s. Value/alarm/wire/FLNK checks run independently of timing limits.
Blocking native discovery isolation remains M8 work.

The real committed M3 archive at `/tmp/snmp-m4-baseline-20260924-a` fails
`m4-deadline-baseline-b`: a response after the 400 ms record deadline yields
SEVR=0 instead of INVALID while the OS suspends the completion worker.
`m4-queued-baseline-a` observes requests `[[1], [2]]` instead of `[[1]]`:
expired queued OID 2 was transmitted. Both regressions pass on final source.
Pre-fix unsuppressed `m4-asan-development-b` reports 992 bytes leaked in twelve
allocations and IOC exit 1; final ASan runs report none. Sandbox process
inspection failures remain separate and do not count as defect evidence.

Final ASan legacy and six waveform STRING/CHAR/UCHAR x NELM 16/128 paths
compare equal to separate actual db9ebf5 executions. The legacy comparison
explicitly excludes timeout-input STAT/SEVR because Base active-scan alarm
timing varies. No broader equivalence is claimed. Waveform comparison covers
100 cycles without that exclusion.

The historical main's empty version-selected epicsExit shim does not itself
invoke Base hooks. On this POSIX build, osdThread registers
`atexit(epicsExitCallAtExits)`, so returning from main still invokes them.
`m4-eof-baseline-d` observes real PTY EOF and iocsh exit both reaching the
historical module shutdown hook. This resolves the EOF interpretation; it is
not a claim that historical EOF lacked cleanup. Candidate tests additionally
observe request-worker, callback and network shutdown order.

Independent third-person execution and second-person reader review passed
at 2026-09-24T06:15:35-07:00 with no new finding, report rev20260924_061535.
Fresh candidate, ASan and exact M3 builds are under
`/tmp/snmp-m4-review-lmpns1b8/`. Fresh ordinary and ASan teardown each passed
six cases over 122 owned PTY IOCs. Fresh pressure, accounting, native protocol,
ASan failures and actual legacy comparison passed; shorter lifecycle,
conversion and robustness repetitions remain explicitly partial.
The two M3 deadline cases failed for the intended behavior and current
candidate passed them. The complete author repetition profiles were
independently recounted against raw evidence, not described as new executions.
An additional actual Base HIHI/MAJOR test verifies acquisition-valid still
advances for successfully consumed values with a Base value alarm and does
not advance on transport failure. Its actual trace has 60 unique events and
ten FLNK audits. All twenty frozen file hashes remained unchanged.

No final platform matrix, one-hour soak, TSan/UBSan qualification, physical
pilot, firmware change, production deployment or remote landing is claimed.

##### Closure Evidence

- Local implementation, third-person and second-person reviews, and corrected
  handoff passed on 2026-09-24. Commit 30d8b81fb10ff1940d9ff29d46d6954679a1f5ba
  contains exactly the 21 reviewed paths. Committed SHA-256 identities and a
  clean worktree were verified after commit. Remote landing remains pending;
  no required check is waived.

#### M5 - Compatibility and candidate acceptance

Origin: db9ebf5 / M5
Identity History: none
GitHub Issue: none
Status: In progress

##### Summary

Verify the complete candidate against the accepted mode, record, protocol, and operating-system matrix.

##### Scope

Run the final built library/IOC, consolidate regression evidence, document the implemented API and diagnostics, and prepare identifiable deployable artifacts plus the legacy rollback pair.

Out of scope: Production changes, a release/tag action, or declaring hardware compatibility from an emulator alone.

##### Completion Criteria

- All required M2-M4 checks run on the final candidate; changed shared paths trigger the relevant reruns. All checks must pass except the explicitly retained Base callback admission limitation below, accepted for continued local development on 2026-09-24. This exception does not mark its failed tests as passing or authorize deployment.
- Legacy default and new mode pass the accepted input/protocol matrix; simulated output behavior remains compatible.
- Documentation examples load with the delivered DBD/IOC, including rejection of invalid configurations.
- The candidate and rollback binary/DB pairs are identified, rebuildable, and independently reviewed.

##### Dependencies And Decisions

- M2 supplies executable evidence; M3 and M4 supply behavior and failure coverage. G1 is Complete as of 2026-09-24; local implementation is authorized.
- Decision Date: 2026-09-24. Defer Base source/installation changes, review the proposed correction separately, document the demonstrated callback overflow limitation, and continue module milestones. The exception covers that known dependency limitation only; any other required failure remains blocking. M5 local handoff and subsequent implementation must carry the limitation explicitly; G2/G3 and hardware acceptance remain unchanged.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-09-24; current M5 plan plus the explicit decision to document the Base limitation and continue development
Implementation Authorization: 2026-09-24; document the limitation, review the Base correction proposal and proceed with module milestones; Base modification remains deferred and physical execution remains subject to G2/G3
Superseded Plan Artifacts: original M5 mapping is extended only for the dated dependency-limitation decision

1. Run a clean build and the real integration runner on declared Debian 12 and Rocky 9 targets; record Base, Net-SNMP, compiler, and architecture rather than relying on a latest container tag.
2. Exercise default legacy, all-new-mode, and mixed-mode fixtures, including supported SNMP versions and security contexts.
3. Measure request-to-completion latency, last-valid-sample age, batch occupancy, queue growth, CPU/memory/FDs, recovery, and cross-host delay against G1 limits.
4. Demonstrate that each claimed regression detects its target defect through the real path; use the baseline where applicable, and do not describe unsupported new syntax as a baseline behavioral failure.
5. Update documentation/devSnmp.html and relevant examples for the implemented API, units, timing, limitations, and rollback compatibility.
6. Review the final diff and state/lock contract. Package the exact candidate and old artifact pair for M6; do not publish or deploy under this work item.
7. Verify devSnmp.dbd device declarations, the matching exported dsets, expanded snmp.dbd, generated snmp_registerRecordDeviceDriver.cpp, linked library and actual IOC registration. Regenerate downstream DBD/registration before loading the new DTYP. Do not add DBDINC for existing Base record types.
8. Document the Base callback overflow limitation in the user guide, test guide and a durable decision. Independently review the proposed Base correction without applying it. Preserve matrix exit codes and failed assertions, identify the bounded development exception in the handoff, and rerun the required final matrix. No broader failure exemption is introduced.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Build matrix | Build the actual support library and IOC on both declared platform targets. | Debian 12 and Rocky 9 with recorded versions | Both builds succeed and load the intended device-support registrations. |
| T2 | Integration matrix | Run all required M2-M4 scenarios against the final candidate binaries. | Actual shipped fixtures and protocol peers | All required cells pass, subject to the dated Base callback limitation accepted for local development only. Its actual failure remains failed; skipped/unavailable cells and unrelated failures cannot count as accepted. |
| T3 | Backward compatibility | Compare legacy input/output/readback runs against the baseline using identical peer inputs. | Baseline and candidate actual IOCs | Existing defaults and accepted observable behavior are preserved. |
| T4 | Examples/documentation | Load delivered example DB/startup files and exercise valid and invalid mode syntax. | Candidate executable/DBD | Documented configuration works; invalid configuration fails visibly as specified. |
| T5 | Candidate traceability | Reproduce startup with candidate and rollback binary/DB pairs and compare recorded identifiers. | Isolated test IOC | The running module is the intended build, and the rollback pair is usable. |
| T6 | New DTYP registration | Inspect installed/expanded DBD and generated registration; load one actual record of each accepted new type and one legacy type, initialize and perform a peer read. Repeat with a deliberately mismatched old DBD/library pair. | Final built production and test IOC products | Matching artifacts resolve the intended dsets and complete real reads. The mismatched pair fails visibly and the runner rejects it; merely finding the DTYP name in source is insufficient. |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | 2026-09-24T17:46:12.026634+00:00 | Debian 13, Debian 12 image abcca0a934ef, Rocky 9 image 517e43ac402b; Base 7.0.10; recorded compiler/native/crypto inputs | PASS: all 15 final builds and matching production/test registration paths | /tmp/snmp-m5-matrix-20260924-c; five build manifests per platform and actual candidate-registration results |
| T2 | 2026-09-24T17:46:12.026634+00:00 | Final exact-source candidates and shipped default fixtures on all three OSes | Final required matrix PASS: 35 required steps per OS; earlier Base callback failures remain failed and unresolved under the dated local-development exception | Three complete matrix.json files, raw suite/IOC/peer/CA evidence and final pressure holds; the preserved failure observations below remain applicable |
| T3 | 2026-09-24T17:46:12.026634+00:00 | Original db9, selected M4 rollback, candidate and ASan candidate with identical comparison inputs | PASS: 18 actual legacy/waveform comparisons; both candidate native modes pass 5/5 per OS; three Debian 12 historical v3 shutdown failures remain failed | Per-platform baseline-comparison.json and protocol results; original protocol is a historical observation, not rollback acceptance |
| T4 | 2026-09-24T17:46:12.026634+00:00 | Final production and test IOCs, exact delivered example DB/loader and real peer | PASS: ordinary registration suite 5/5 per OS, including both examples and invalid configuration; the earlier extra ASan loader leak remains failed | candidate-registration/results.json and registration-inputs.json; additional dependency observation retained below |
| T5 | 2026-09-24T11:46:32.948593-07:00 | Four identified artifact roles per OS; final full matrix and independent source/runtime/dependency audit | PASS: actual identities match and selected M4 legacy/protocol/terminal runs pass; independent third-person/second-person review and handoff cross-check accepted | artifact-pairs.json; platform audits; /tmp/snmp-m5-final-review-20260924-reader/audit.json and external results; fup20260924_114632 |
| T6 | 2026-09-24T17:46:12.026634+00:00 | Final matching production/test DBD, generated registration and libraries; both deliberate mismatch directions on each OS | PASS: supported types complete actual reads; six mismatch startups show required binding errors without peer requests | candidate-registration results, exported symbols, generated registration identities, mismatch.json and actual IOC logs |

##### Final Local Qualification

The final public Matrix.run executions completed on 2026-09-24 using the
unreduced shipped profiles: 100 ordinary cycles, 1000 immediate responses,
the full 60-second pressure hold and 20 starts per declared teardown variant.
Evidence root: /tmp/snmp-m5-matrix-20260924-c. launch-specs.json,
`<platform>-launch.json` and `<platform>/matrix.json` preserve the exact public command,
environment and immutable image identity. No installed dependency was changed.

| Platform | Started UTC | Finished UTC | Required steps | Historical protocol | Matrix exit |
| --- | --- | --- | --- | --- | --- |
| Debian 13 | 16:35:22.482834 | 17:42:09.967270 | 35/35 PASS | PASS | 0 |
| Debian 12 | 16:35:20.547536 | 17:41:39.546212 | 35/35 PASS | Three v3 shutdown failures, IOC exit -11 | 0 |
| Rocky 9 | 16:35:21.894900 | 17:46:12.026634 | 35/35 PASS | PASS | 0 |

Each complete matrix has 36 steps and partial=false. The sole non-required
step is the original comparator's native protocol observation. Debian 12
therefore retains all_steps_passed=false and historical_failures containing
baseline-protocol. The six intended negative attempts per OS fail their real
assertions and are correctly detected; they are not successful positive tests.
Declared selected-case subcommands retain their individual partial=true.

Across all platforms, the executions contain 15 builds, 93 public suite
invocations, 396 test attempts and 1707 IOC startups: 1701 ordinary runtime
records plus six deliberate mismatch startups. There are 375 passing attempts,
18 intended failing attempts and three historical failing attempts. The
miswired control records two failure events for one attempt, so event counts
are not attempt counts. All 18 legacy/waveform comparisons are equal.

The exact original, M3 and M4 source archives, candidate/ASan copied inputs,
executables, libraries, expanded DBD, fixtures and actual startup files are
identified by the build manifests and artifact-pairs.json. The two C3 document
corrections made after launch affect only the canonical milestone and Base
limitation ADR; every runtime and fixture input remains the launched version.
Original snapshots and failed results are unchanged. The selected rollback
is exact M4 plus legacy DB/startup, with nine ordinary production IOC starts
per OS covering legacy, waveform, native protocol and both terminal exits.

| Platform | Pressure hold seconds | Initial/final FDs | RSS increase KiB | Observed CPU seconds | Healthy p99 alone / with silent peer, seconds | Loaded maximum seconds |
| --- | --- | --- | --- | --- | --- | --- |
| Debian 13 | 60.000727862 | 8/8 | 8 | 0.48 | 0.044216250 / 0.044833129 | 0.047792007 |
| Debian 12 | 60.001146026 | 8/8 | 4 | 0.46 | 0.043129065 / 0.042787989 | 0.045311771 |
| Rocky 9 | 60.002140725 | 8/8 | 4 | 0.49 | 0.046320842 / 0.045278899 | 0.048854983 |

Resource data comes from actual owned IOC samples. CPU has no selected site
threshold. Each healthy timing condition contains 1000 measured v2c reads;
these results do not qualify v3 discovery isolation or one-hour resources.
All three final pressure cases pass; they do not close the demonstrated Base
callback limitation or identify the original failed Rocky descriptor.

Independent final review completed at 2026-09-24T11:25:35.690358-07:00 with
third-person and second-person PASS and no new demonstrated in-scope defect.
Its new audits verify retained real executions, not newly executed IOC suites.
The audit rederives 843 accepted scenario directories and 285648 completed
generations from original IOC events, including one FLNK per accepted key and
PACT set during FLNK. This is the trace-bearing subset, not every startup.
It independently checks 4527 host-side file digests and 82 platform-local
dependency/client/compiler files with no identity error. Evidence:
/tmp/snmp-m5-final-review-20260924-reader/{audit.json,workloads.json,external-launches.json}
and the three external result files; official review fup20260924_112535.

The final source and completed matrix support local M5 handoff preparation
under D007/D008. F009, F011 and F012 are implemented and independently verified.
F010 remains deferred and unresolved; its natural and controlled failures
below stay failed. The additional ASan loader leak also remains failed and
outside any claim of passing ASan registration. Final handoff derivatives
passed fup20260924_114632; the local commit is 750ea26. Remote landing remains
pending. No Base repair,
M8 worker qualification, hardware acceptance or deployment follows.

##### Earlier Qualification Observations

Observed at 2026-09-24T07:30:35.605265-07:00. Full acceptance is pending; completed subset results
above do not waive unfinished matrix cases or the usable rollback condition.

The unmodified db9ebf5 archive on Debian 12 passes the v1/v2c native cases
but all three v3 security-level cases fail during EOF cleanup after successful
GET, SET and readback observations. The public runner reports IOC exit -11.
An independent reviewer reproduced all three failures three times; the
candidate passed both modes in that independent repetition. An additional
owned-PTY diagnostic with the same shipped protocol.db, IOC helper and real
snmpd/UDP proxy also fails all three v3 levels on explicit exit.

The preserved cores show native USM work in the module's send/read threads
reaching OpenSSL and pthread_rwlock_rdlock with a null lock. In the authPriv
core, the main thread is in C exit/library finalization, epicsExitCallAtExits
and snmpAtExit. The archived snmpMain.cpp selects its dummy epicsExit on
Base 7.0.10 and its executable has no epicsExit import. Commit e1878bc
already corrects that version condition in the candidate. These observations
identify the old shutdown path and actual fault location; they do not turn the
archive's failure into a passing rollback result.

Core stack evidence is under /tmp/snmp-m5-debugger-os92sr1c/, with matching
Debian 12 libraries copied from the recorded immutable image. Original cores
remain in /tmp/snmp-m5-matrix-20260924-b/debian12/rollback/. The separate explicit-exit diagnostic
is /tmp/snmp-m5-matrix-20260924-b/debian12-rollback-explicit/results.json, with its source and launch
record retained at the matrix root. No original binary or core was modified.

An additional independent ASan registration run observed a 129-byte,
one-allocation leak in each loader example. The full observed stack is
malloc -> macParseDefns -> iocshBody -> iocshLoadCallFunc -> iocshBody ->
snmpMain.cpp; the selected Base 7.0.10 source allocates the defines array
and does not free it. Evidence:
 /tmp/snmp-m5-review-j3e481_k/asan-registration/results.json and
 /tmp/snmp-m5-review-j3e481_k/asan-example-stack/.
This extra run failed and is retained as a Base dependency observation;
it is not part of a passing ASan-registration claim. No Base patch or broad
sanitizer suppression is applied.

The archived comparison baseline remains db9ebf5. Selection of a separately
qualified operational rollback pair remains open after the archive failures;
the candidate matrix continues without substituting a new baseline.

Additional observation at 2026-09-24T08:05:29.923216-07:00: the Rocky 9 full pressure case fails its
single final FD equality check (initial 8, final 9); the sixty-second held
interval remains at 8. The original run remains failed. Three unchanged
public repetitions by the Implementer and three independent repetitions by
the Reviewer pass with 8 initially and finally. External observations show
temporary additional UDP sockets near completion, but the original failed
run did not record descriptor targets/inodes, so its additional FD is not
identified. No leak-free or resolved-failure conclusion is drawn.

The original failure is under
/tmp/snmp-m5-matrix-20260924-b/rocky9-runtime/candidate-pressure/.
Additional public results and partial FD observations are under
/tmp/snmp-m5-matrix-20260924-b/rocky9-pressure-fd-observer/;
its public runner exits zero, but the separate external observer records one
PermissionError and its wrapper exits one. The observation is not a complete
passing observer run. Independent results are under
/tmp/snmp-m5-pressure-review-a72905s0/public-repeat/.
This unresolved measurement requires disposition before T2 acceptance.

The unchanged M4 commit 30d8b81fb10ff1940d9ff29d46d6954679a1f5ba was separately
archived and built on all three platforms as a concrete optional rollback
pair. Each actual production IOC with legacy fixtures passes one legacy
comparison case, fifteen native protocol cases (three repetitions), the
selected legacy EOF/explicit-exit observer case, and three explicit v3
security-level exit diagnostics. The selected terminal run remains marked
partial; it is not the complete teardown suite. All actual IOC exits are
zero. The build artifacts and 21 runtime identity records per OS were
rehashed and associated with the matching executable/DBD/module.

Evidence: /tmp/snmp-m5-rollback-option-20260924-a/qualification.json, original
per-suite results, execution records and launch identities. This prepares an
owner-reviewable option; it does not select or replace the original comparison
baseline, waive F009, or close M5/T5.

Additional completed evidence at 2026-09-24T08:27:22.748402-07:00: all original full matrices
finished with exit 1. Debian 13 failed the miswired-FLNK and trace-loss
negative-control classifications because their expected message patterns
did not match the actual intended assertion failures. Debian 12 had the same
two classification failures plus the archived v3 shutdown failures. Rocky 9
had the same two classification failures plus the original FD 8-to-9 result.
Required ordinary candidate and ASan suites otherwise passed. The full run
manifests retain exact default counts, commands, source/build identities,
raw results and failure records.

The two message patterns now identify the actual assertion failures. Fresh
targeted executions of the shipped Matrix methods and public runner pass
wrong-value, miswired-FLNK and trace-loss controls on all three OSes.
Those manifests are explicitly partial method qualifications. The original
full matrices were built from the original eleven frozen source hashes;
the three changed test/documentation files are separately identified.
No production source or original result was changed.

Resource observations now record FD targets and require an unchanged initial
count for 100 ms, then return to that count for 100 ms within the existing
10-second action timeout after record completion. All intermediate samples
and the immediate post-completion count remain retained. Three full pressure
repetitions pass on Debian 13 and Rocky 9. One Debian 13 repetition observes
8 initially, 9 at record completion, and 8 after a 0.126-second settling
observation. This new observation does not identify the original Rocky FD.

A temporary OS-close fault retains real UDP descriptors in the owned Rocky
test IOC. The unmodified public pressure case fails with
Wait expired: stable final FD count, and the shipped matrix correctly
classifies that intended failure. Native APIs, record callbacks and protocol
fixtures are not substituted. Evidence is under
/tmp/snmp-m5-matrix-20260924-b/rocky9-runtime-retained-udp/.

Debian 12 corrected pressure repetitions produce PASS, FAIL, PASS. The failed
repetition stops in the initial ordinary warmup, before the new resource
sampler or sustained callback blocker runs. Actual wire and driver traces
show all 21 generation-6 responses; ten records apply and complete, while
eleven remain Ready with PACT 1. Final diagnostics show callbackPending false
and more than 1000 callback admission retries for each unfinished record.
The runner expires after ten seconds and the IOC subsequently exits zero.
This is an unresolved completion failure, not a resource-sampler failure
or a passed repetition. Evidence is under
/tmp/snmp-m5-matrix-20260924-b/debian12-correction/pressure/
test_callback_queue_sixty_seconds-vj8wfw7u/sustained-acq1k102/.
No load-only explanation or Base root cause is established by this record.

All corrected-method raw results are under the platform-correction directories
at the same root. The retained identity audit
audit-full-matrix-corrected.json verifies the original frozen charter hashes,
build artifacts, logs, suite associations and pair inputs without mismatch.
The earlier audit-full-matrix.json is preserved: its one counting error per OS
assumed one unittest outcome event per test attempt, whereas the miswired case
records separate body and cleanup failures for one attempt. The corrected
audit separates attempt count from outcome events and changes no test verdict.

Operational rollback decision, 2026-09-24: use the verified M4 source
30d8b81fb10ff1940d9ff29d46d6954679a1f5ba with legacy DB/startup. The unmodified
db9ebf51bc81d6f63d9395513d94d60b3b7eda83 remains the comparison baseline.
This supersedes the pending-selection statements above. The selected pair's
actual three-platform qualification is retained in the cited qualification.json.
The current matrix and public instructions now implement separate candidate,
operational rollback, historical comparator and ASan candidate identities.
The actual db9 native protocol outcome is retained as a non-acceptance
historical observation; its failed rows are never changed to passing rows.
All other steps remain required, including db9 legacy/waveform comparisons,
old/new registration mismatch and the selected M4 legacy/protocol/terminal
checks. Independent affected-path verification remains in progress; no fresh
complete matrix acceptance is claimed. The callback failure still blocks T2.

Independent method review finalized at 2026-09-24T08:42:31.684370-07:00:
the corrected assertion matching and bounded FD observation pass both the
execution and maintainer-reading checks. Six actual public invocations contain
eight test attempts, including intended negative failures and one new natural
Debian 12 warmup failure. That failure has 189 actual results but only 170
applications/completions/FLNK audits; generation 9 leaves nineteen records
Ready with PACT 1 and more than 1000 admission retries. All three full original
matrices remain failed. The independent identity audit covers their 1680 IOC
records. Evidence: /tmp/snmp-m5-correction-review-w2cl_z3v/.

Bounded cause diagnostic executed from 2026-09-24T15:52:57.480344+00:00 to
15:53:09.544637+00:00 using the actual Debian 12 candidate and shipped pressure
fixture. A hardware execution breakpoint stops only its owned snmpComplete
thread before callbackRequest stores queueOverflow after a failed ring push.
Other IOC threads continue. The queue is already empty and overflow is clear
at the stop and after a 200 ms scheduling delay. Debug registers are restored
and the unchanged instruction resumes. Every one of 1003 subsequent raw
memory samples over 10.20 seconds shows used=0 and overflow=1. The actual public
runner fails the original warmup completion assertion, exit 1; the diagnostic
wrapper exits 0 and records no diagnostic error. No source instruction, queue
data or internal function was replaced.

Base R7.0.10 callbackRequest rejects a set overflow flag before attempting a
push; the consumer clears the flag only after a successful pop. The observed
empty-queue/overflow condition therefore prevents subsequent callback
admission. This demonstrates that interleaving in the actual dependency and
matches the module's repeated-rejection symptom. The two prior natural
failures did not capture queue memory, so their exact interleaving remains
unobserved. Three preceding read-only queue-observer runs passed and do not
waive the failures. No production-size failure rate or indefinite runtime
duration is inferred from this bounded test.

Diagnostic evidence is /tmp/snmp-m5-matrix-20260924-b/debian12-queue-schedule/,
with schedule_base_queue.py and the exact container launch JSON at its parent.
The verified Debian 12 libdbCore SHA-256 is
9f2fc56ba76e7ac72019c301f1cc138cc31c6eb0ccdd94bb8e1ffe921c51d3b6.
Dependency repair is outside the current M5 implementation boundary. The
proposed remedy is to make admission depend on the actual synchronized ring
push, retaining overflow reporting separately. Decision Date: 2026-09-24;
defer that repair, review the proposal, document the limitation and continue
module development. This supersedes the pending repair-scope question and
the earlier assertion that this specific limitation blocks all subsequent
implementation. It does not establish an all-tests-pass result, a completed
repair or a production acceptance. No Base patch, installed-tree change or
completion workaround is applied; the known failed observations remain failed.

Independent selected-pair review finalized at 2026-09-24T09:25:37.643694-07:00.
Its 33 public invocations contain 72 attempts: 66 passes, three retained
Debian 12 original-baseline v3 failures and three intended wrong-baseline
rejections. All required positive affected paths pass on Debian 13, Debian 12
and Rocky 9. The audit covers 90 normal runtime records and six old/new
registration mismatch startups with no identity errors. These are fresh
executions of the shipped Matrix methods, not a fresh complete Matrix.run.
Evidence: /tmp/snmp-m5-selected-review-32eqly78/, including final-audit.json.
This supersedes the pending affected-path verification statement above.

That reviewer also independently reran the original scheduling diagnostic:
1008 post-resume samples over 10.238178212 seconds show the empty ring with
overflow set. The actual pressure test fails with 21 results, two completions
and nineteen records still Ready with PACT set. This adds one diagnostic IOC;
it does not supply a completed sixty-second pressure phase. Evidence:
/tmp/snmp-m5-selected-review-32eqly78/diagnosis/ and diagnosis-audit.json.

Independent Base proposal review finalized at 2026-09-24T09:31:49.554565-07:00.
Source and retained raw-evidence checks find no demonstrated contradiction
in making admission depend on the locked ring push and keeping callback
ownership unchanged. This is a static conclusion; no corrected Base was
built or executed. The proposed overflow counter counts reported diagnostics
after suppression; suppressed diagnostics and the total number of rejected
requests are different quantities. Consumer progress resets suppression;
it is not a time limit. Existing Base callback tests each make 169 initial
submissions and expect 338 callback invocations with a 2000-entry default
queue; separate actual full-queue,
concurrent ownership and diagnostic tests are required before adoption.
Atomic/interrupt behavior requires target-specific verification; Linux
process observations do not qualify other interrupt environments.

The durable [Base callback limitation decision](decisions/ADR-20260924-base-callback-limitation.md)
and public guides record these operating and verification limits. The
unapplied proposal remains separate from the implemented module. The static
and maintainer reviews do not claim corrected runtime behavior or remove
the retained failures. The final complete M5 matrix and source review are
recorded above; fup20260924_114632 accepted the handoff derivative cross-check.

##### Closure Evidence

- Final local source and matrix review: fup20260924_112535, 2026-09-24,
  third-person and second-person PASS under D007/D008. F010 remains deferred
  and unresolved; original failed observations are retained.
- Final handoff cross-check: fup20260924_114632, third-person and second-person
  PASS. Local commit: 750ea26243614ec4402994959e21bd970b0a6856; fourteen
  committed paths and hashes verified against the accepted inventory, with a
  clean post-commit tree at 2026-09-24T11:49:10.968465-07:00.
- No remote landing or production acceptance; Status remains In progress.

#### G2 - Pilot environment and IOC change authority

Origin: db9ebf5 / G2
GitHub Issue: none
Status: Open

##### Summary

The downstream IOC owner/operator provides an accessible pilot environment, the allowed read subset, and authority to prepare/apply the IOC change. This gate affects M6.

Named condition: Pilot environment and IOC change authority.
Prerequisite evidence: M5.

##### Completion Criteria

- The exact IOC/PDU subset, safe access path, module/IOC revisions, and rollback pair are known.
- The pilot duration, numeric acceptance limits, allowed operations, and service procedure are approved.
- Laboratory fault injection and production monitoring are distinguished; no live outlet switching is implicit.

##### Verification Results

| Observed At | Result | Evidence |
| --- | --- | --- |
| Not run | Pending | none |

##### Closure Evidence

- None.

#### M6 - Downstream IOC migration and pilot

Origin: db9ebf5 / M6
Identity History: none
GitHub Issue: none
Status: Blocked

##### Summary

Apply the accepted mode to the selected PDU read path and verify the actual downstream database before production rollout.

##### Scope

Prepare an authorized downstream IOC change, preserve PV names/conversions/output controls/PVA mapping, run its delivered DB against the external peer, and conduct a first approved single-device read pilot followed by approved individual and combined checks of the three selected devices.

Out of scope: Changing unrelated IOCs, live outlet switching, arbitrary production disconnects, or treating a pilot as fleet approval.

##### Completion Criteria

- The exact module artifact and downstream IOC commit/DB/DBD pair are recorded.
- Every selected input's acquisition owner and any remaining legacy polling of shared OIDs are documented.
- Actual downstream processing, alarms, and client values pass laboratory and approved device checks.
- Pilot timing/resource/error observations meet agreed limits for the full observation window.

##### Dependencies And Decisions

- M5 supplies the accepted candidate. G2 is Open; resume as Not started when it completes. Downstream repository changes require that repository's own authorization.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-09-24; current plans accepted by the instruction to implement every milestone sequentially
Implementation Authorization: 2026-09-24; implement the current plan, obtain third-person and second-person reviews and apply findings; physical execution remains subject to G2/G3
Superseded Plan Artifacts: none

1. Inventory apcpduApp/Db/load_pdu3ev.db and all selected PDU templates, iocsh loading, command readbacks, and shared OIDs at the current downstream revision.
2. Add explicit mode selection only to the accepted input subset; inspect PINI/fanout/derived-record sequencing and eliminate duplicate acquisition ownership where required by the accepted contract.
3. Keep SCAN, the established session timeout/retry settings, batch limit, and MDEL unchanged for the first controlled comparison unless a separately recorded design decision requires a change.
4. Build/relink the downstream IOC against the candidate module and regenerate the DBD as required. Run the actual installed DB in the laboratory with isolated PV names.
5. Verify startup does not generate unintended SETs. Test output/readback coexistence only against the external peer unless a separate safe hardware operation is authorized.
6. Run one approved device pilot with timestamped start/end measurements. A proposed initial normal-operation window is 30 minutes; G2 must accept the duration and limits before execution.
7. Apply the laboratory per-record sequencing checks to each selected hardware/DB pair from the three-device inventory, within G2 authority. Run each approved device for the agreed window before the combined three-device observation; retain per-device results and do not generalize one APC result to NMC3 or Tripp Lite.
8. Publish the observed results and exact migration/rollback pair here; promote to G3 only after all required individual and combined checks pass. Any unapproved hardware coverage remains pending, not inferred from the first pilot.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Installed DB path | Run the actual expanded/installed downstream DB with the candidate IOC against the external peer. | Isolated laboratory IOC | All selected inputs request and complete correctly with actual fanout/conversion/derived-record behavior. |
| T2 | Startup/control separation | Capture the peer's real operations through cold start, read completion, and shared-OID readback. | Laboratory peer with simulated outlets | No unintended SET, command replay, or changed output value ownership. |
| T3 | CA/PVA data path | Run the downstream data-path checker against the actual DB and existing published groups; use changing peer values. | Laboratory downstream IOC | Expected channels and values remain correct; acquisition evidence is measured separately from monitor cadence. |
| T4 | Hardware pilot | Observe the approved read subset using request/completion diagnostics, valid-sample age, client/alarm checks, and resource deltas. | One G2-approved PDU and IOC | Agreed timing/error/resource limits hold for the full window; parser errors remain separately counted and investigated. |
| T5 | Recovery rehearsal | Use the laboratory fault peer and restore the retained old module/IOC/DB pair. | Same downstream deployment layout in a safe environment | Both error recovery and rollback work without control writes or stale new-mode configuration. |
| T6 | Three-device coverage | Observe approved read subsets separately on T000398, T000525 and T001374, then concurrently. Record actual protocol/firmware/IOC/DB and correlate request/result/FLNK traces; physical values need not change on demand. | G2-approved devices and test IOC | Each device preserves per-record sequencing and meets accepted timing/resource limits. A combined run cannot hide an individual failure. No production fault injection or outlet SET is used. |

##### Configuration Discovery

Read-only observation at 2026-09-24T08:59:49.209142-07:00: the apcpdu checkout is clean on
refactor/snmp-db-processing at 6bedd223117f55b253c5834bdc50c013df1a9010,
matching its fetched tracking branch. The active iocar08-pdu startup has three
PDU loaders, but iocBoot/iocar08-pdu/ver3.txt is absent. The iocap7800b-apcpdu,
ioctestLab-apcpdu and iocarrf-apcpdu directories each contain ver3.txt with
SNMPv3 identity/authentication/privacy fields. Credential values are neither
copied into this record nor supplied to a device by this inspection.
The pdu_ap7800b.iocsh and pdu_pdu3ev.iocsh loaders default to SNMPv3 and resolve
ver3.txt relative to IOC working directory. The active AR08 native timeout is
2000000 microseconds. The Tripp Lite loader enables its write DB unless
WRITE_EN disables that load; an approved read-only subset must therefore be
prepared before running a physical pilot.

The checkout does not establish the three asset-to-address associations.
The same-session normal-token AMS network lookups for the three inventory IDs
returned HTTP 401, so no asset mapping was inferred. This is configuration
inspection only: no IOC startup, device GET/SET, installed-tree change or G2
acceptance occurred. The T1-T6 verification rows remain unexecuted.

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | Not run | Isolated laboratory IOC | Pending | none |
| T2 | Not run | Laboratory peer with simulated outlets | Pending | none |
| T3 | Not run | Laboratory downstream IOC | Pending | none |
| T4 | Not run | One G2-approved PDU and IOC | Pending | none |
| T5 | Not run | Same downstream deployment layout in a safe environment | Pending | none |
| T6 | Not run | G2-approved devices and test IOC | Pending | none |

##### Closure Evidence

- None.

#### G3 - Production deployment window and acceptance limits

Origin: db9ebf5 / G3
GitHub Issue: none
Status: Open

##### Summary

The production operator accepts M6 evidence and authorizes the exact deployment scope, interruption window, observation period, and rollback. This gate affects M7.

Named condition: Production deployment window and acceptance limits.
Prerequisite evidence: M6.

##### Completion Criteria

- The exact candidate module/IOC/DB pair and initial target are approved.
- Numeric limits for completion latency, valid age, queue depth, errors, healthy-host delay, and resources are fixed before deployment.
- Rollback triggers include stuck PACT, invalid/stale data beyond the accepted bound, unexpected SET/control activity, repeated new parser errors, and resource growth.
- The responsible operator, restart method, observation duration, old artifact location, and rollback actions are available.

##### Verification Results

| Observed At | Result | Evidence |
| --- | --- | --- |
| Not run | Pending | none |

##### Closure Evidence

- None.

#### M7 - Controlled deployment and rollback

Origin: db9ebf5 / M7
Identity History: none
GitHub Issue: none
Status: Blocked

##### Summary

Deploy the verified module/IOC pair within the approved production scope and prove operational acceptance and recovery.

##### Scope

Stage the candidate, verify the installed dependency path, replace the approved IOC instance during its window, validate read behavior, and retain or exercise the known-good rollback pair.

Out of scope: An unapproved restart, device power cycling, live outlet commands, widening the approved scope, or a release/tag/push action.

##### Completion Criteria

- The running executable, linked module, DBD, DB, and startup configuration match the approved candidate.
- Startup, acquisition, alarms, required client paths, and resources satisfy G3 limits over the approved window.
- Rollback has been rehearsed in M6 and can restore the recorded old binary/configuration pair; a rollback outcome is recorded instead of marking deployment successful.
- Every additional IOC has its own recorded rollout decision and observed acceptance.

##### Dependencies And Decisions

- M6 supplies device and downstream evidence. G3 is Open; resume as Not started when it completes.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-09-24; current plans accepted by the instruction to implement every milestone sequentially
Implementation Authorization: 2026-09-24; implement the current plan, obtain third-person and second-person reviews and apply findings; physical execution remains subject to G2/G3
Superseded Plan Artifacts: none

1. Record the current executable/module checksum, dependencies, startup file, installed DB/DBD, runtime settings, and normal diagnostics; retain the complete known-good pair.
2. Install the candidate in a distinct versioned location. Build or relink the IOC when the module linkage requires it; copying a shared library alone does not prove the IOC uses it.
3. At the approved window, stop the old IOC through the site's service/console procedure and confirm it has stopped before starting the replacement on the same device/PV namespace. Do not run duplicate pollers.
4. Start the candidate with the approved opt-in configuration. Check its actual library/dependency resolution, loaded DBD, startup errors, record states, and absence of unintended control activity.
5. Observe valid completion, PACT, alarms, last valid age, queue/latency/resource deltas, CA connectivity, and the unchanged PVA publication path for the approved window.
6. If a rollback trigger occurs, stop the candidate, restore the old executable/module/DBD/DB/startup pair, and start the old IOC. Remove new-mode configuration from the restored configuration; do not pair it with an unsupported old DBD.
7. Verify restored connectivity, values, alarms, and operational polling. Record the reason and evidence; a successful rollback is not a successful new-mode deployment.
8. Record production acceptance and retained rollback location before proposing any additional target. Version/release publication remains a separate request.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Installation identity | Inspect the running process and actual dependency resolution against staged checksums and configuration identifiers. | G3-approved production IOC | The intended candidate is running, including the correct DBD and DB. |
| T2 | Startup/read behavior | Check initialization, PACT completion, alarms, values/conversions, and required client connections. | Approved production read subset | Healthy reads complete within accepted limits; no new startup/control regression. |
| T3 | Operational observation | Measure per-interval diagnostics, last-valid age, latency, errors, memory/FDs, and healthy peer behavior for the approved window. | Approved production scope | All G3 limits hold; no comparison based only on cumulative polls/sec or camonitor event intervals. |
| T4 | Rollback readiness/outcome | Verify the M6 rehearsal evidence and restore the old pair if an approved trigger occurs. | Recorded deployment layout and operator procedure | The old configuration can be restored and verified; actual rollback results, if any, remain explicit. |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | Not run | G3-approved production IOC | Pending | none |
| T2 | Not run | Approved production read subset | Pending | none |
| T3 | Not run | Approved production scope | Pending | none |
| T4 | Not run | Recorded deployment layout and operator procedure | Pending | none |

##### Closure Evidence

- None.

#### M8 - Extensible SNMPv3 architecture

Origin: db9ebf5 / M8
Identity History: none
GitHub Issue: none
Status: In progress

##### Summary

Make SNMPv3 security and session evolution independent of EPICS record
completion, while preserving legacy behavior and the request-driven contract.
The structural proposal is `docs/snmp-architecture.md`. This detail owns the
implementation sequence, tests, status, and evidence; the proposal is not a
claim that its components already exist.

##### Scope

Typed request/result boundaries, immutable security profiles, native-library
capability validation, algorithm extensibility, startup credential loading and
restart activation, explicit engine identity, reusable sessions, discovery/recovery
isolation, scheduling, diagnostics, and staged compatibility. The proposed
Linux worker runtime includes a matching helper product, private IPC, bounded
supervision and process-loss semantics; adopting it requires design acceptance.

Out of scope: new output semantics, fanout-wide completion, automatic protocol
or security downgrade, a new cryptographic implementation, firmware changes,
production deployment, live credential/profile replacement, and deletion of the
tested candidate. Session recovery does not reload configuration or credentials.

##### Completion Criteria

- Record processing and request ownership do not depend on Net-SNMP session
  pointers, USM structures, or algorithm selection.
- Real v3 tests establish algorithm support, security identity isolation,
  automatic and explicit engine identity handling, bounded discovery/recovery,
  and credential activation only after IOC process restart.
- Session reuse preserves exactly-once record completion, stale-response
  rejection, healthy-device progress, and the existing output contract.
- The real module/IOC/peer/client path passes the compatibility, lifecycle,
  platform, and resource checks below; unsupported cells remain explicit.
- Legacy SET behavior matches a separately executed baseline, including packet
  values/order, retry counts, failure recovery and readback interaction.
- Inherited native defaults work without a watchdog override after helper setup;
  automatic bounds preserve retry behavior, and explicitly undersized bounds
  fail before application traffic. Record deadlines remain independent.
- Independent design/code review and downstream laboratory verification are
  complete. Production and firmware checks remain under M6/M7 and their gates.

##### Dependencies And Decisions

- D6 authorizes preparation of the modernization design. D3/D4 remain the
  compatibility and sequencing requirements.
- D7 requires the native-library reuse contract in `docs/snmp-architecture.md`.
  Separate protocol/discovery/key caches and packet retry implementations are
  not work items. Library-backed behavior must be tested rather than inferred
  from exported symbols or from the phrase Single Session API.
- D8 excludes live replacement. T9 verifies startup loading, rejection of
  runtime configuration changes and activation after process restart; it does
  not require a reload API or in-process USM user replacement.
- D9 finalizes the automatic watchdog calculation at 150000 ms for inherited
  native settings. The architecture defines the interval budget, selected
  allowance, worker maximum, checked arithmetic and absolute deadline lifetime.
  The former proposed 10-second default and 600000 ms ceiling are not accepted
  bounds. The native Debian 13 evidence supports timer accounting; T5/T17/T18
  must still verify actual admission, timeout/retry preservation and retirement.
- Carry-forward to step 6: devSnmp_host deletes a session that stays sent
  and incomplete for 60 s without the manager session mutex, and the
  destructor completes its requests while the read thread may still process
  a late reply for that session. The race predates M8; since step 2 both
  paths also write the per-OID scratch result. With the inherited 10 s
  timeout and five retries the native expiry is about 60 s, at the stale
  boundary. Step 6 replaces this session lifetime and must close the race
  with a reproducing test before its verification passes. Observed by code
  reading on 2026-09-24; not reproduced.
- Step 3 adds the Single Session adapter only; the record transport keeps the
  traditional API until it moves with the worker in steps 5 and 6. The
  adapter's service() waits on session sockets only, so the worker loop in
  step 5 must provide its own wake path. Decision Date: 2026-09-24.
- D10 selects Debian 13 and Rocky 8 as the M8 qualification platforms. T12 and
  the step regressions use those two; the Debian 12 and Rocky 9 native
  observations below stay as retained evidence and are not rerun.
- The current 19 request and two 12-case APC results are a regression baseline,
  not proof of the proposed v3 architecture. M8 can be designed without waiting
  for the unrelated hardware/deployment gates.
- Those 43 tests do not establish successful SET behavior. T17 supplies a real
  output baseline before transport migration and compares the final candidate.
- Native discovery and USM state isolation are evidence dependencies before
  runtime adoption. The preliminary native experiment below observed blocking
  in first send, not session open. A single shared library owner is therefore
  unsuitable for the required healthy-device progress under that fault. Review
  the concrete worker-process proposal, including IPC, startup credential
  snapshots, crash recovery and deployment, before adopting it. Do not weaken T8,
  add unverified v3 concurrency, or implement another discovery protocol.
- Algorithm/device combinations and production timing limits require measured
  capability and site policy. No firmware capability is inferred from AMS.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-09-24; current plans accepted by the instruction to implement every milestone sequentially
Implementation Authorization: 2026-09-24; implement the current plan, obtain third-person and second-person reviews and apply findings; physical execution remains subject to G2/G3
Superseded Plan Artifacts: none

The 2026-09-23 directions authorize design preparation, D8/D9 document
amendments, native-library feasibility and timeout/retry measurements,
finalization of D9's numeric contract, and this milestone elaboration from the
completed full-plan review. Those were design-only instructions. The 2026-09-24 instruction recorded above
now accepts and authorizes this current implementation plan. T14 still requires
review of the final implementation.

The [full-plan convergence report](../work/review_sessions/20260923_104501_snmp-architecture/convergence/conv20260923_140435_codex_gpt6_root_full_plan.md),
finalized at 2026-09-23T14:04:35-07:00, records three independent PASS verdicts
and zero new demonstrated plan defects. Every reviewer read the complete
milestone, architecture, request contract and watchdog ADR. Their depth lanes
were EPICS sequencing/compatibility, Net-SNMP/security/worker ownership, and
implementation order/tests/build/install. This supports the plan; it does not
verify the proposed runtime or replace final candidate acceptance.

The reviewed milestone had SHA-256
`e4e15d37455ef36fa985f79207c41c18b7c65edb558ec098d634da9e928bb8d4`.
The report records all four frozen target identities. This amendment maps that
reviewed sequence to deliverables and records the review evidence; it is not
the frozen document itself. D3/D4 and D7-D9 remain the contracts: per-record
request/result/FLNK ordering, native Net-SNMP protocol and retry ownership,
automatic or explicit engine identity, startup-only credential activation,
and a compatible absolute worker deadline independent of record deadlines.

1. Inventory the target library's documented APIs, installed headers and
   exported symbols; record exact Debian/Rocky packages and build capabilities.
   Establish the v3 baseline using the actual test IOC and real snmpd. Record
   cold/warm requests, discovery packets, latency and healthy-peer progress.
   Preserve the current source and 43-case evidence. Establish T17's SET
   baseline with the shipped output support before moving legacy transport.
   Include omitted timeout/retry defaults and real packet loss. Inspect the
   supported native retry/discovery/recovery paths and measure packet counts
   and terminal timing; qualify D9's specified watchdog calculation and native
   control-operation accounting on each target library before platform acceptance.
   Keep the selected operating allowance distinct from measured evidence and
   the watchdog separate from record acquisition deadlines; a sample does not
   establish a hard wall-clock upper bound.
   Close T1/T2 before claiming an IOC performance problem or gain; symbol availability
   alone is not v3 evidence. T17 remains partial until candidate comparison.
2. Introduce typed request/result and opaque transaction identities, separating
   `snmpRequest.cpp/.h` from `devSnmp_session` and Net-SNMP varbind types. Extract
   the EPICS adapter and keep existing conversion/FLNK behavior. Run T3 and the
   existing-endpoint/OID-order/20-and-21-OID subset of T4 against the unchanged
   transport. Record T4 as partial; profile/context isolation is exercised only
   after its real configuration and binding path exists in step 4.
3. Add a thin Net-SNMP adapter using the documented Single Session API and
   native PDU, OID, error and timeout handling. Keep default library discovery
   and USM handling. Test native opening/recovery with a failed and a healthy
   endpoint, PDU ownership, callback operation mapping and retry accounting.
   Run T15's implemented API ownership/retry cases. Retain the native experiment
   as the architecture premise, but do not label adapter-only results as T8 IOC
   acceptance. Until the reviewed worker runtime exists, discovery isolation and
   worker lifecycle cases remain pending.
4. Route existing iocsh configuration through validated profiles. Use
   usm_lookup_auth_type/priv_type and sc_get_auth_oid/priv_oid through the
   version adapter, generate_Ku for passphrase-derived session input, and
   library-managed localization. Keep only policy/alias validation and credential
   revisions in module code. Add the securityEngineID/contextEngineID endpoint
   settings defined in the architecture through the existing host setter and
   file parser, mapping validated bytes into native session fields. Implement
   the reviewed LoadV3Profile/DefineEndpoint/SetEndpointParam commands and
   explicit endpoint link grammar in `snmpRegister.cpp` and a separate validated
   configuration component; no new syntax is inferred from the community field. Run initial
   configuration cases from T5, profile/context cases from T4, T6/T7 and T16's
   parsing/initial exchange cases. Runtime-change rejection and restart/recovery
   cases remain pending until steps 5 through 7.
5. Add the reviewed snmpWorker host executable, explicit helper-path setup,
   worker supervisor and private framed protocol. Place Net-SNMP initialization,
   MIB/algorithm/key operations and session calls only in the child. Use real
   posix_spawn/socketpair paths, bounded startup, resource limits, worker epochs
   and restart from the parent's frozen credential snapshot. Change
   `snmpApp/src/Makefile` and the independent consumer startup fixture to locate
   the matching helper. Apply D9's evidence-backed automatic bounds and explicit
   override validation without changing native timeout/retries. Run T5's real
   no-override/default and undersized-override startup cases, T18's
   startup/framing/crash cases and T8 through the
   real IOC. No adoption from the preliminary native-only latency result.
6. Separate transaction lifetime from reusable session lifetime. Implement
   bounded admission, batching, fair dispatch, completion handoff and shutdown;
   library timeout/retries remain the sole wire retry mechanism. Move legacy
   GET/SET and text-format compatibility through the same worker path before
   mixed operation. Close T3/T4/T8/T10/T11/T15/T17 and T18's load/shutdown cases,
   including exhausted waiters, pending native retries, no SET replay after
   worker loss and baseline-versus-candidate output behavior. Run T16's engine
   recovery/isolation cases; its configuration-freeze cases remain pending.
7. Finalize startup-only credential/profile loading and reject changes after
   configuration is frozen. Credential-file edits do not affect a running IOC;
   apply them through a full IOC process stop/start. Close T5/T9/T16 using real
   agents, invalid startup inputs, runtime-change rejection and restart tests.
   Do not implement reload, in-process credential cutover, USM user deletion or
   a module-side USM cache.
8. Run the final compatibility and resource matrix on the exact candidate,
   then the downstream APC laboratory suite. Rerun all implemented functional
   cases on this exact source-identified candidate; earlier subset results are
   not final acceptance. Close T12/T13/T14/T18 and reconcile every T1-T18 result.
   Review the design and final implementation through the convergence workflow required
   by `milestone-tracking`; record findings and acceptance without treating a
   source inspection as runtime verification.
9. Carry the accepted module/helper/DB/DBD/configuration pair into the existing M6
   pilot and later per-device firmware comparison. Do not replace M6/M7 gates
   with laboratory success.

The following table maps the same nine steps to implementation targets and
observable advancement conditions. It is part of this plan, not a second work
register. Step 1 fixtures, the step 2 extraction and the step 3 adapter are
delivered; later components remain planned. Run each step's available checks before migration
depends on that step; record partial coverage explicitly. Step 8 reruns the complete acceptance matrix on the final
candidate even when an earlier implementation passed its subset.

| Step | Deliverable | Files or subsystem | Verification before advancing |
| --- | --- | --- | --- |
| 1 | Source/binary identities, input baseline, real v3 measurements and pre-migration SET behavior | `tests/test_request.py`, `tests/sequence.db`, APC scratch consumer suites; real-agent support in `tests/snmp_agent.py`, `tests/test_snmpv3.py`, `tests/legacy_set.db`, `tests/test_legacy_set.py`; target-library inventory | T1/T2 baseline evidence and T17 baseline subset; retain packet counts, values, timing and exact native settings before transport changes. |
| 2 | Typed requests/results and EPICS completion adapter | `snmpApp/src/snmpRequest.cpp`, `snmpRequest.h`, `devSnmp.cpp`, `devSnmp.h`; `tests/sequence.db`, `tests/src/sequenceProbe.cpp`, `tests/test_request.py` | T3 and the existing-endpoint/OID/batch subset of T4 through the unchanged transport; one terminal completion with value/alarm application before FLNK and PACT clearing afterward. |
| 3 | Thin native session adapter with explicit ownership | New Net-SNMP adapter component; `snmpApp/src/Makefile`; real-library fixtures | Implemented T15 ownership/callback/retry cases; no module retransmission or discovery implementation. Adapter-only measurements do not close T8. |
| 4 | Validated profiles, endpoint bindings and engine identity | `snmpApp/src/snmpRegister.cpp`; new configuration component and adapter bindings; proposed v3 fixtures | Initial T5 configuration, T4 profile/context, T6/T7 and T16 parsing/exchange cases; invalid configuration fails explicitly and advertised algorithms complete real exchanges. |
| 5 | Matching helper product, private IPC and supervised workers | New `snmpWorker` product, supervisor and protocol components; `snmpApp/src/Makefile`; independent IOC startup fixtures | T5 automatic/default/override checks, T18 startup/framing/crash subset and actual IOC T8 isolation; the new worker path keeps Net-SNMP operations in the child and D9 admission preserves native settings. Legacy transport migration follows in step 6. |
| 6 | Reusable sessions and bounded mixed legacy/request operation | Scheduler, worker adapter and supervisor; `snmpApp/src/devSnmp.cpp`, `devSnmp.h`, `snmpRequest.cpp`, `snmpRequest.h`; input and proposed SET fixtures | T3/T4/T8/T10/T11/T15/T17, T18 load/shutdown and T16 recovery subsets; preserve output behavior against step 1 and prevent module SET replay after worker loss. |
| 7 | Immutable startup configuration across child recovery | Configuration loader, iocsh setters and worker startup snapshot; proposed v3 fixtures | Complete T5/T9/T16: reject runtime changes, reuse the snapshot on child restart and activate file changes only after a full IOC restart. |
| 8 | Identified module/helper candidate and complete acceptance evidence | Module/helper build products, all test fixtures, independent APC consumer, this Verification Results table | Final-candidate T1-T18 reconciliation, including T12 platform/resources, T13 APC integration, T14 independent implementation/evidence review and full T18 lifecycle; classify unsupported or failed cells explicitly before acceptance. |
| 9 | Exact candidate and recovery procedure for the downstream pilot | M6/M7 details; module/helper/IOC/DB/DBD/configuration identities and per-device evidence | M6 laboratory/device checks and later firmware comparison under G2; production work remains under G3/M7. M8 laboratory success grants neither hardware nor deployment authority. |

##### Test Plan

Acceptance methods use shipped IOC/DB/device support and real Net-SNMP. The existing
v2c peer remains the outer boundary for packet-order/error tests.
`tests/snmp_agent.py` supervises a real snmpd, and
`tests/test_snmpv3.py` drives CA and records the pre-migration observations.
The public runner provides the `v3-baseline` and `legacy-set` suites described
in `tests/README.md`. A loopback UDP proxy may delay/drop/replay genuine v3 packets;
it must not stand in for authentication, encryption, or the module backend.
Test credentials are disposable and never copied from hardware configuration.
`tests/legacy_set.db` and `tests/test_legacy_set.py` exercise the shipped
ao, longout and stringout device support against an external writable laboratory
agent through native snmpd's pass_persist interface; `tests/agent_values.py`
implements only that external disposable device. The read-only peers do not
serve as SET success fixtures. Capture the pre-migration source/binary identity, output PVs,
agent values and packet sequence before comparing the candidate under the same
inputs. Modifying an internal driver function is not a permitted fixture.

A stage may run only the cases whose actual configuration and implementation
exist. Record such results as partial, with the executed cases named; do not
close an entire T label from a subset. Final acceptance uses the complete matrix
against the final candidate, including restart-only T9, SET comparison T17 and
worker lifecycle T18. Native-library feasibility measurements are recorded
separately and cannot close an IOC test label.

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Baseline | Run the existing 19 request tests and both unchanged 12-case APC suites against a source-identified build. | Selected Debian 13/Base 7.0.10 tree | Same input values, alarms, FLNK counts, read-only/no-unintended-SET behavior and shutdown outcome; differences classified before migration. Actual SET behavior is covered separately by T17. |
| T2 | V3 baseline | Run 100 cold opens and 1000 warm reads with real snmpd; record discovery/request packets, session opens, CPU, FD/RSS, queue/result/FLNK latency. | Loopback, exact Net-SNMP package and crypto capabilities recorded | Machine-readable baseline; no claimed speedup from code inspection. |
| T3 | Record contract | Reuse `sequence.db` and `test_request.py`; add a three-input FLNK chain and a fanout of two delayed inputs. Inspect final converted values and alarm at each FLNK. | Actual IOC with external peer | Each accepted request has one terminal result and one completion; PACT clears after FLNK. Chain waits for predecessors; fanout only orders initial calls. |
| T4 | Identity and batch | Reorder, duplicate, omit and delay varbinds; use identical OIDs across endpoints, contexts and profiles; exercise 20/21 OIDs with limit 20. | Actual IOC and external peers | Only compatible requests batch; membership is frozen at handoff; no late or wrong-profile result completes a newer request; no packet exceeds limits. |
| T5 | Configuration | Exercise old setters/files and all named commands/link syntax: duplicate names/keys, unknown profile, incorrect placeholder, missing fields, invalid levels, unknown options, oversized values, unavailable algorithms and derivation failures. After helper setup, start legacy and named bindings without SessionTimeout, SessionRetries or WorkerProgressLimitMSec overrides; also bind both published read/write example endpoints. Verify automatic 150000 ms, reject explicit 149999 ms and accept 150000 ms for default bindings. Exercise the architecture's 20000/7600/900000 ms examples, fractional-millisecond rounding, a legacy proportional-allowance case, native retry-increment limits and all checked arithmetic/deadline boundaries. Check file ownership/mode/symlink rejection and unchanged legacy links. Attempt profile/credential/engine/worker-setting changes after freeze. Search logs for disposable secret sentinels. | Actual IOC and real config loader | Default bindings and both example endpoints succeed with D9's exact derived bound and unchanged native settings. Invalid startup configuration, including an undersized watchdog, fails before application traffic; no fallback, silent truncation or retry reduction. Runtime changes leave active state intact. Credentials remain absent from diagnostics. Engine-specific cases are in T16. |
| T6 | Algorithm support | Use real authenticated/encrypted GETs for every advertised SHA-2 algorithm with AES-128; test explicit noAuthNoPriv/authNoPriv/authPriv, permitted legacy combinations, v1/v2c compatibility and unavailable-policy cases. | Real snmpd and candidate linked library on each OS | Exact protocol identity reported; unsupported combinations fail explicitly; no silent fallback and no claim based on header symbols alone. |
| T7 | Security failures | Wrong user/auth secret/privacy secret, wrong context and access denial; restart the IOC with corrected test configuration. Use known-valid snmpget as the external oracle. | Real snmpd with controlled users/access rules | No false success or fresh timestamp; exactly one terminal record error, successful operation after corrected startup; silent drops are reported as timeout rather than an invented diagnosis. |
| T8 | Discovery isolation | Blackhole one v3 endpoint during initial discovery and restart while a healthy endpoint is read at 100 ms intervals. Use a 400 ms acquisition deadline and 4 s transport timeout. | Two real agents, loopback fault proxy, 1000 healthy reads | Faulted requests complete within 1 s locally; healthy p99 no more than baseline plus 100 ms, maximum below 1 s, zero false INVALID samples. Limits are laboratory criteria, not field promises. |
| T9 | Startup and restart credentials | Edit the credential file while requests are queued, in flight and callback-pending; confirm the running IOC retains its startup snapshot, including after child loss/restart. Reject runtime setters. Stop/start the IOC with coordinated agent credentials; test invalid files, delayed packets, identical usernames with different keys at distinct engines/workers and conflicting same-user profiles in one worker. | Real snmpd, actual startup loader, IOC/child lifecycle and native USM state | Only full IOC restart activates file changes. A child restart uses the existing snapshot. Invalid startup inputs fail without old-secret fallback; conflicting credentials/protocols for one worker/user fail before discovery/application traffic. Distinct workers do not share USM state. No false success, double completion or secret leak. |
| T10 | Recovery and reuse | Repeat reads on one session, restart agent with same engineID/new boots and then with a changed engineID; drop replies and force tooBig. | Real snmpd plus external proxy | Bounded retry/recovery within the original deadline; no reuse of wrong localized keys; valid-sample age advances only on success; stable warm session avoids repeated discovery. |
| T11 | Load and shutdown | Flood bounded request admission, saturate callback queue, mix legacy reads/SETs, stop during discovery/recovery/response; run 20 EOF and explicit shutdown cycles. | Actual IOC; SETs only against disposable laboratory agent | Bounded queue/session counts, no GET/SET starvation under accepted load, no deadlock/UAF, every normal cycle reports drained shutdown; no synthetic shutdown FLNK. SET semantics are compared separately in T17. |
| T12 | Platform/resources | Run functional suite and one-hour steady-load test; record ASan/UBSan and separately TSan results where supported, FD/RSS/CPU and queue metrics. | Debian 13 and Rocky 8 under D10; Base/compiler/crypto identities recorded | No sanitizer findings accepted without disposition; descriptors return to baseline, retained state stays within configured bounds, no growing memory trend after warmup. |
| T13 | APC integration | Build independent module/IOC pairs via the EPICS-env runbook; run original and input-converted APC DB/PVA/CA fixtures using v2c and a real v3 agent exposing the required OIDs. | Selected dependency tree, scratch consumer builds | Preserved DB/DBD/INP/DTYP and input/PVA/CA behavior, no unintended SET, correct library identity, no installed-tree writes; v3 fixture is actual snmpd instrumentation, not a v2c decoder. Actual output semantics require T17. |
| T14 | Architecture review | Inspect component dependencies, generation/lock/shutdown rules, v3 evidence and compatibility results through independent convergence review. | Final source-identified candidate and evidence | No unresolved functional, preservation or verification defects against the accepted design; owner decisions remain explicit. |
| T15 | Native API ownership | Exercise actual adapter send success/failure, response copy, close with pending work, retries 0/1/3, intermediate callbacks, mixed-deadline waiters and high FD numbers. Compare callback/packet counts with snmpget using identical retry settings; inspect direct library calls. | Real module/IOC/Net-SNMP and external peers; target package per OS | Correct PDU/callback lifetime, one terminal completion, no duplicate module retransmission, no mixed API families, no custom USM/discovery/crypto cache; large-FD path works. |
| T16 | Engine identity | Use both real host-setter and file configuration paths. Test omitted IDs, matching explicit securityEngineID, omitted/matching explicit contextEngineID, a distinct context ID against the same snmpget oracle, hex case/prefix variants, valid 5/32-byte boundaries, empty/odd/non-hex/short/long/all-zero/all-FF inputs, wrong security ID, agent reboot and changed engine identity. Repeat cold/warm authenticated exchanges and the T8 fault scenario in automatic and explicit modes. | Real IOC, real snmpd with controlled identities/contexts, loopback fault proxy and native Net-SNMP client | Invalid inputs fail before session opening. Automatic mode discovers the agent; explicit mode passes the configured bytes and never silently rebinds to a different security ID. Context ID stays independent. Authentication/timeliness and recovery still use native handling; errors complete once with no false fresh value. Valid boundary fixtures must complete real exchanges; runtime setting changes are rejected. |
| T17 | Legacy SET compatibility | Before transport migration and on the final candidate, run identical ao/longout/stringout command sequences against writable laboratory OIDs. Exercise success, agent error, request loss, reply loss after application, timeout/recovery, retries 0/1/3 and omitted timeout/retry defaults. Use the automatic watchdog policy on the candidate. Include repeated writes to one OID while another transaction blocks dispatch, mixed GET load and shared-OID readback around SetSkipReadbackMSec. Observe recovery after retry exhaustion without issuing another command; record packets and terminal timing for the inherited default policy. | Source-identified baseline and candidate IOCs, proposed legacy_set.db/test_legacy_set.py, real writable agent and external packet-loss proxy | Match commanded and observed values, types, queued-write coalescing/order, wire retry counts, output processing/alarm behavior and readback suppression/recovery, including the default native policy. The watchdog does not truncate allowed native retries. No additional module SET replay after exhaustion/reopen; library retransmissions are measured, not called exactly-once device execution. No unintended SET at startup or from input completion. Differences require disposition before acceptance. |
| T18 | Worker boundary | Build and launch the actual helper from the actual IOC. Test missing/wrong helper, protocol/build mismatch, process/queue/byte/frame bounds, partial IPC and EOF, late/duplicate identities, child loss during discovery/GET/SET, parent death during blocking send, restart backoff and startup-snapshot reuse. Exercise the 150000 ms default and shared-worker maxima with differing endpoint settings. Use real loss and OS suspension to distinguish allowed native work from a child exceeding its absolute deadline, measured from the first IPC write attempt; verify retries/REPORTs/partial frames/read splits/waiter expiration cannot reset it. Use an external IPC fault proxy on the real channel for fragmentation/corruption, and OS signals for process faults; do not replace either endpoint's code. Check same-address/different-profile serialization, different-address progress, inherited descriptors, missing helper rollback, shutdown and process/FD cleanup. | Linux candidate module/helper pair on Debian 13/12 and Rocky 9; real snmpd, actual IPC and disposable SET targets | One terminal record outcome, bounded memory/process counts, no stale-epoch completion, no credential output or automatic SET replay, no orphan worker after parent death, graceful shutdown or explicit bounded failure. Allowed native retries fit D9's derived bound; an over-limit child is retired without extending its deadline. Longer transport bounds do not extend record deadlines or relax T8. The IOC contains no Net-SNMP call path. Unsupported platforms and failed cells remain explicit. |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | 2026-09-24T19:54:39.429552+00:00; review 2026-09-24T13:14:37-07:00 | Independently archived 750ea26 module; APC 6bedd223 original and fully input-converted consumers; Debian 13/Base 7.0.10 | Baseline execution and bounded correction review PASS; final replacement comparison pending | 19 request and 12 original APC cases pass; a separately rebuilt 63/63-input-converted APC consumer passes 12 cases. The earlier 15/63 mixed-input run remains separately identified below. |
| T2 | 2026-09-24T19:28:06.264006+00:00 | Archived 750ea26 test IOC, actual Net-SNMP 5.9.4.pre2 snmpd and native client, SHA/AES authPriv; Debian 13 x86-64 | Baseline collection PASS; no replacement performance claim | 100 cold IOC starts and 1000 warm reads with native call observation, plus 1000 warm reads without it; real packet, completion, CPU/FD/RSS observations retained below. |
| T3 | 2026-09-24T20:11:32.646493+00:00 to 2026-09-24T22:17:39.619337+00:00 | Step 2 extraction candidate built in isolation from the working tree on 750ea26; Debian 13/Base 7.0.10/Net-SNMP 5.9.4.pre2 and Rocky 8.10/Base 7.0.10/Net-SNMP 5.8; actual test IOC, external peer and CA clients | PASS on both platforms; independent third-person and maintainer review passed on 2026-09-24; the final candidate rerun remains pending | sequencing 9, lifecycle 15, conversion 2 and accounting 3 cases per platform against the db9ebf5 waveform baseline; see Step 2 Extraction Regressions below. |
| T4 | 2026-09-24T20:11:32.646493+00:00 to 2026-09-24T22:17:39.619337+00:00 | Same candidate builds, IOCs and peers as T3 | Existing-endpoint/OID/batch subset PASS on both platforms; profile and context bindings remain pending until real bindings exist | failures 10, batch 10 with 20/21 OIDs at limits 1 and 20, and robustness 16 cases per platform; see Step 2 Extraction Regressions below. |
| T5 | 2026-09-23T12:33:06-07:00 | Native API only; configuration/profile implementation not run | Pending | The native timeout/retry experiment below measures inherited settings; no startup admission or undersized-watchdog rejection was exercised. |
| T6 | Not run | V3 algorithm matrix | Pending | none |
| T7 | Not run | Real v3 agents | Pending | none |
| T8 | 2026-09-24T19:28:06.264006+00:00 | Actual pre-migration IOC and two native agents; 400 ms record deadline, 4 s transport timeout, 100 ms requested read interval | Baseline fails the proposed isolation criteria; worker candidate and restart qualification pending | Control: 0/1000 INVALID, p99 46.649 ms; blackholed discovery: 80/1000 INVALID, p99 408.889 ms. This is an actual IOC observation, distinct from the earlier native-only experiment. |
| T9 | Not run | Startup/restart credential implementation | Pending | none |
| T10 | Not run | Reusable-session implementation | Pending | none |
| T11 | Not run | Load/shutdown matrix | Pending | none |
| T12 | Not run | Platform/resource matrix | Pending | none |
| T13 | Not run for M8 | APC laboratory integration | Pending | none |
| T14 | 2026-09-23T14:04:35-07:00 | Four frozen plan/contract documents and source/evidence review; no replacement candidate | Partial; final implementation/evidence review pending | Full-plan convergence conv20260923_140435 records three independent PASS verdicts and zero new demonstrated plan defects. The prior watchdog correction remains represented by D9 and conv20260923_130832. Review basis and frozen identity are recorded above; final implementation/runtime acceptance remains unverified. |
| T15 | 2026-09-25T04:08:56.389399+00:00 to 2026-09-25T04:10:30.522120+00:00 | Module adapter snmpNative.cpp in the test IOC through nativeProbe; real snmpd and UDP observer; Debian 13 Net-SNMP 5.9.4.pre2 and Rocky 8 5.8 | Adapter subset PASS 19/19 on both platforms; record-path, worker and platform-resource cases pending | Send success and immediate send failure, response copy, close with pending work, retries 0/1/3 compared with snmpget, RESEND callbacks, USM rejections, recovery after an agent restart, a foreign report ID, a failed SNMPv3 retransmission, re-entrant get, mixed deadlines and a socket at descriptor 1100; see Step 3 Native Session Adapter below. The 2026-09-23 native C probe runs remain separate retained evidence. |
| T16 | Not run | Explicit/automatic engine identity implementation | Pending | none |
| T17 | 2026-09-24T19:46:42.217277+00:00 | Archived 750ea26 IOC; actual ao/longout/stringout, native writable snmpd and external UDP fault proxy; Debian 13/Base 7.0.10 | Baseline 12/12 PASS; final candidate comparison pending | Success, agent error, queued coalescing, readback suppression and request/reply loss at retries 0/1/3/defaults passed. Native retransmissions and default-policy 60-second session retirement are recorded separately below. No worker or exactly-once device guarantee follows. |
| T18 | 2026-09-23T12:33:06-07:00 | Native experiments only; worker/IPC/IOC implementation not run | Pending | Process separation and native timer measurements are preliminary evidence, not verification of the proposed watchdog, supervisor or IPC path. |

##### Pre-Migration IOC Baseline

The independently archived module is
750ea26243614ec4402994959e21bd970b0a6856. Its build and fresh 43-case
compatibility evidence are retained under /tmp/snmp-m8-baseline-20260924-b.
Both APC copies use 6bedd223117f55b253c5834bdc50c013df1a9010 and the unchanged
shipped test_pva.py. The second copy changes only 15 of the 63 inputs in the
sensor-enabled configuration: the 48 template-generated outlet inputs remain
Snmp. Its twelve passes qualify that mixed configuration only.
The actual builds, selected module RUNPATH/ldd observations, source hashes and
all suite outcomes are retained. Both 12-case APC suites passed, in 40.424 s
and 40.583 s respectively. The installed-tree change check was empty.
The preceding attempt under /tmp/snmp-m8-baseline-20260924-a retains its
sandbox interface-enumeration/PVA failure and does not count as passing APC
coverage.

The corrected conversion uses the same archives and existing module build in
/tmp/snmp-m8-apc-converted-20260924-a. It converts supported inputs in both
.db and .template sources before the real consumer build. The expanded loaded
DB inventory contains 63/63 SnmpRequest inputs, including all 48 outlet
inputs; output support and the shipped test_pva.py are unchanged. The actual
build, selected-module ldd check and twelve tests pass, the latter in
42.807 s. The installed-tree change check is empty. The current 43-case
baseline uses the original 19 request and 12 original APC cases plus this
corrected twelve-case run. The earlier mixed run is additional evidence.
inputs.json SHA-256 is
c99036a606773b7ea3c4465d161b2a8ab3874921a5d827d8e699a8a518245c96;
expanded-inputs.json is
6fad9676422d67e4cc87cc150546be6151763b8c8fe4f990823f38e880c09905.
Recheck using work/run-m8-apc-converted.py with a new output directory.

The v3 run is /tmp/snmp-m8-v3-baseline-20260924-c, public suite v3-baseline:
five observation cases passed in 557.191 s. All 104 actual IOC processes
exited zero with the required shutdown sequence; all seven owned native
agents exited zero without forced termination. The loaded module SHA-256 is
e007bcb843d29767dc1a32ca29965526d89779629dc7a2c6a4d976dc7a08a759;
snmpRequestTest is
7bd7ad1ac1e9141d109749854e64e3b5c99d37ca19e538441b8ebeadbe3bd56a.
The build manifest SHA-256 is
0e7e20a53e9cb8208576a5044740107b5c24a3fc3ff1a62db232f3490716d2ad.
run.json, actual loaded-library records and the retained fixture-snapshot
identify the separate module and harness inputs.

Each cold IOC completed one authenticated read, one FLNK and one observed
session open/close. The warm observed run completed 1000 reads with 1000 native
snmp_open returns, 1000 snmp_close returns and 1000 actual discovery requests.
The separate run without LD_AUDIT also observed 1000 discovery requests.
The observer records actual dynamic calls without replacing their targets;
its measured timing is distinct from the run without observation.
Warm request acceptance-to-completion p99/max were 48.712/51.564 ms with
observation and 48.951/50.966 ms without it. At each successful FLNK the
actual value was applied and PACT remained set; completion followed.

The warm resource snapshots retained 8 FDs and 23 threads at both endpoints.
RSS increased from 15020 to 26808 KiB with observation and from 13740 to
25676 KiB without it. CPU counters, intermediate samples, queue/result/FLNK
times and packet headers remain in the raw evidence. These measurements do
not identify a memory-growth cause or qualify the one-hour resource test.

The two-address control and discovery-loss observations each processed 1000
healthy-record requests and ten other-endpoint requests. Control p99/max were
46.649/49.728 ms with zero INVALID samples. With the other address blackholed,
p99/max were 408.889/410.172 ms and 80 healthy-record completions were INVALID.
The faulted measurement does not meet zero INVALID or the permitted 100 ms
p99 increase. The observation suite passes collection and per-record ordering;
that outcome is not T8 acceptance. Process-restart isolation and the final
worker implementation remain unverified.

Earlier v3 runs -a and -b remain failed: -a's native-call parser missed the
first line after the IOC prompt; -b's multi-field CA reader removed a final
empty string value. Their raw observations are preserved. The -c run uses the
corrected real-path readers; no earlier failed case is relabeled as passed.

The completed SET baseline is /tmp/snmp-m8-legacy-set-20260924-d:
12/12 tests pass in 508.057 s, with partial=false and no cleanup errors.
Its run.json and fixture-snapshot retain the exact 59 fixture files. The
queued-write case uses a 4 s native timeout for a genuine held GET; all five
CA commands precede release and no SET precedes release. The resulting three
writes carry 333, 444 and queued in order. Native snmpget, device write logs
and CA record samples provide separate value observations.

For each of three outputs, request and reply loss at retries 0/1/3/defaults
produce 1/2/4/6 packets with the same native request ID. Recovery requires no
new command and creates no extra module SET transaction. Short policies
finish by native timeout; the inherited policy uses the old module's
60-second stale-session retirement. Wire transport-continuation timestamps
are separate from later buffered-log observations; neither is presented as
an exact callback timestamp. Reply loss can follow real device application,
so library retry counts are not an exactly-once execution guarantee.
The earlier SET -a/-b failures and weaker queued condition in -c remain
identified by their own fixture versions. This establishes comparison inputs
for T17; the replacement transport has not passed that comparison.

Installed API inventory at /tmp/snmp-m8-native-inventory-20260924-a records
16 declarations and exports on each target: seven Single Session calls,
four large-FD helpers, two USM algorithm lookups, two protocol-OID lookups and
generate_Ku. Exact headers, shared-library hashes, native build options,
compiler/crypto output and invocation/image identities are retained.

| Target | Net-SNMP package | Reported native version | OpenSSL package |
| --- | --- | --- | --- |
| Debian 13 | 5.9.4+dfsg-2+deb13u1 | 5.9.4.pre2 | 3.5.7-1~deb13u2 |
| Debian 12 | 5.9.3+dfsg-2+deb12u1 | 5.9.3 | 3.0.20-1~deb12u2 |
| Rocky 9 | 5.9.1-21.el9.x86_64 | 5.9.1 | 3.5.5-4.el9_8.x86_64 |

Observed on 2026-09-24; recheck with work/inventory-m8-native.py in each
identified environment. Availability does not establish runtime ownership,
algorithm interoperability, blocking limits or platform acceptance. Those
remain the actual adapter/IOC tests in the later steps.

The bounded baseline correction review completed at
2026-09-24T13:14:37.359267-07:00. Independent third-person and maintainer
passes accepted the delivered fixture descriptions and corrected APC input
coverage. The audit independently compared 87 archived source files, derived
the 63 input bindings and 25 unchanged outputs, checked the four actual IOC
record inventories, and reread the retained twelve-case APC/SET results.
It also repeated header/export/package inspection in all three native
environments. Its 625 recorded evidence hashes match the retained artifacts
in /tmp/snmp-p801-correction-reader-20260924-a. This review ran no new IOC
suite and does not qualify step 2, a replacement worker, final T1/T17, T8
isolation or the deferred Base correction. The reviewed canonical snapshot
has SHA-256 d9f2272658681ef77d25b70c68534f32d1d61b81ed3aae843683b39efd038ad5;
session follow-up fup20260924_131437 records the two corrected findings as
implemented and verified.

##### Step 2 Extraction Regressions

The step 2 candidate is the working tree on 750ea26 with the typed
request/result boundary: `snmpTypes.h`, `snmpEpics.cpp`, `snmpEpics.h`,
`snmpRequest.cpp`, `snmpRequest.h`, `devSnmp.cpp`, `devSnmp.h` and the module
Makefile. Both platforms build it in isolation with `tests/build_fixture.py`
from the working copy and run the public `tests/run_snmp.py` suites with the
shipped `tests/profiles/loopback.json`.

Debian 13 build /tmp/snmp-m8-extraction-20260924-b has dirty diff SHA-256
b0334d0d9a6fe9de0f0b91b48a2c0748e58b9733bf564835eacd1de39a37b437, module
71328c7a0a3808eb4461b7c144ec08c7c1bd61bdc11a0f10fff7c41a7d3a8813 and test IOC
ea9109f7e60ad5b3c5d186c1003b2925e89c323b3d0a06075dcc8f8f65b0d699. The run
/tmp/snmp-m8-extraction-tests-20260924-a (2026-09-24T20:11:32 to 20:55:36
UTC, 240 IOC starts) passes sequencing 9/9, failures 10/10, lifecycle 15/15,
batch 10/10 and conversion 2/2 against the M5 db9ebf5 baseline waveforms.
Its robustness run reports two ERROR cases: `tests/owned_thread.py` received
EPERM from PTRACE_SEIZE because that run executed inside a process sandbox
that denies ptrace; the host ptrace_scope is 0. The run is retained as failed.
The rerun /tmp/snmp-m8-extraction-tests-20260924-b (2026-09-24T21:18:55 to
21:36:39 UTC, outside the sandbox) passes robustness 16/16 in 848 s and
accounting 3/3 in 216 s; its IOC hash matches the build manifest. The
robustness rerun recorded the profile before D10 and accounting the profile
after it; the Debian version is declared in both.

Rocky 8 uses image
sha256:5a172c75815f7053900dfec586912834e84d2eb8ea9a504e75fbd4de0e9ccff0
(Rocky Linux 8.10, net-snmp 5.8-33.el8_10, openssl-libs 1.1.1k-12.el8_9,
gcc-c++ 8.5.0-28.el8_10, glibc 2.28-251.el8_10.2, EPICS base
/opt/epics/1.3.0/rocky-8.10/7.0.10/base) in a container without network,
with a read-only root, SYS_PTRACE and uid 1000. The evidence directory
/tmp/snmp-m8-rocky8-20260924-b holds the candidate build (dirty diff SHA-256
36e89b15a590146a6c753061563acbb5eb9db618d70e4a2d5821369f59a68fae, equal to
the working tree including the profile change; module
50e979243877fbf0279bb4141d2ed2703feab221695e4d1461a312def1e23564; test IOC
3855fa47f7280fa3ea2c91ce586e6d840ee33e1a37854b30e58c749024703728) and the
db9ebf5 git-archive baseline `snmp` IOC. Between 2026-09-24T21:25:30 and
22:17:39 UTC it passes sequencing 9/9, failures 10/10, lifecycle 15/15
(1010 s), batch 10/10 (393 s), robustness 16/16 (885 s), accounting 3/3
(234 s), baseline waveforms 1/1 (181 s, `baseline-waveforms-b`) and
conversion 2/2 (269 s, `conversion-b`). Retained failed runs:
/tmp/snmp-m8-rocky8-20260924-a, where every suite failed runtime verification
because the shipped profiles did not yet declare Net-SNMP 5.8; the first
`baseline-waveforms` invocation in -b, which named a test IOC the baseline
build does not produce; and the first `conversion` run in -b, which had no
baseline evidence. None is relabeled.

The in-container scripts `driver.sh`, `driver-waveforms.sh` and
`driver-conversion.sh` record the argv of each build and suite, and the
`executions*.json` files record labels, timestamps and exit codes. The
container command is recorded only here; each script ran as:

```bash
docker run --rm --network none --read-only --cap-add SYS_PTRACE --user 1000:1000 --tmpfs /tmp:rw,nosuid,nodev,size=2g,exec --mount type=bind,src=/home/jeonglee/gitsrc/snmp,dst=/home/jeonglee/gitsrc/snmp,readonly --mount type=bind,src=$OUT,dst=$OUT --workdir /home/jeonglee/gitsrc/snmp --env HOME=/tmp --env PYTHONDONTWRITEBYTECODE=1 --entrypoint bash sha256:5a172c75815f7053900dfec586912834e84d2eb8ea9a504e75fbd4de0e9ccff0 $OUT/driver.sh
```

with `$OUT` set to /tmp/snmp-m8-rocky8-20260924-b. The scripts hardcode that
directory; to recheck, copy them, change `OUT` to a new directory and run
the same command. No ASan run, one-hour resource test, native
API inventory on Rocky 8 or T12 acceptance is claimed by this section.

Independent review on 2026-09-24 against the same frozen sources: the
third-person pass re-derived every evidence root above from its raw files
and reran sequencing, failures, batch, accounting and robustness on the
Debian 13 build, 48/48 cases, in /tmp/snmp-p802-third-*; the maintainer
pass confirmed that snmpRequest and snmpTypes include no EPICS database or
Net-SNMP header and that ownership and release order follow from the code
and docs/snmp-architecture.md. Both passed. Their accepted findings were
missing ownership, call-order, identity and invariant comments; the added
comments were rechecked by a fresh reader, which found the scratch-writer
comment wrong on the stale path; that comment now states the race above.
One startup error text changed with the same S_db_badField status and is
left as is.

The commented tree was rebuilt on Debian 13 as
/tmp/snmp-m8-extraction-20260924-e (module
05dff72ed83cb00fcf806c8b5678f984f6c3b03ba4a280124e18c8a711f7337b, test IOC
f8b72b27bcd176331bd4084fbca29f37cd920edd98137f3c8b9d023e828b97e8); its
build-inputs.json source hashes equal the committed module sources, and its
dirty diff differs from the committed one only in this document. Every
object has the same disassembly, .rodata and .data as build -b except one
instruction in devSnmp.o: the source line that epicsMutexCreate() records
for the session mutex moves from 3800 to 3810. Sequencing 9/9 and failures
10/10 pass on it in /tmp/snmp-m8-comments-tests-20260924-c, and the Rocky 8
image compiles the same tree in /tmp/snmp-m8-rocky8-comments-20260924-c.
Recheck by rebuilding and comparing `objdump -d` output per object.

##### Step 3 Native Session Adapter

snmpApp/src/snmpNative.cpp and snmpNative.h add SnmpNativeSession, the owner
of one Net-SNMP Single Session handle and of the state of every request sent
through it; the library frees each accepted PDU. The native value copy moved unchanged from devSnmp.cpp into
the adapter as snmpNativeCopyValue; the record transport calls it and is
otherwise unchanged. The test IOC drives the adapter through the nativeProbe
and nativeProbeMixed commands in tests/src/nativeProbe.cpp, and
tests/test_native.py is the public `native` suite described in
tests/README.md.

Every snmp_sess_*, PDU and large descriptor-set function the adapter calls is
declared and exported by the installed Net-SNMP on Debian 13 (5.9.4.pre2) and
Rocky 8 (5.8), checked on 2026-09-24. `nm -u` of snmpNative.o lists only the
snmp_sess_* family, the large descriptor-set helpers and PDU, OID, value and
error helpers; no traditional global session function. A new PDU carries a
nonzero request ID before sending on both platforms. The library matches
SNMPv3 messages to requests by message ID, and a report's request ID is zero
or foreign. For a rejected SNMPv3 request both libraries deliver SEC_ERROR and
the report message: 5.9.4 SEC_ERROR first, 5.8 the report first. After an
agent restart raises engineBoots, 5.8 delivers the notInTimeWindow report and
then retransmits and delivers the response; 5.9.4 retransmits without a report
callback. The library also gives a retransmission a new message ID before
sending it and, if that send fails, reports SEND_FAILED with the request's own
PDU and no RESEND. The adapter therefore finds callbacks that carry the
request's own PDU by request ID and received SNMPv3 responses and reports by
the message ID of the latest sent attempt, treats a report message as
intermediate and SEC_ERROR as the terminal security failure, and ignores
callbacks after the recorded outcome.

The first review failed both lanes (rev20260924_184555, rev20260924_184000):
freed callback data after SEC_ERROR crashed the IOC, a send failed inside
snmp_sess_async_send leaked its PDU, a completion re-entering get() during
that failure deleted an exchange twice, and the suite lacked those cases.
The corrected adapter keys requests by ID, frees the PDU and returns false
for a send the library failed, never completes inside get(), and zeroes the
descriptor set. The suite grew from twelve to sixteen cases. The bounded
recheck (fup20260924_195837, fup20260924_195027) confirmed those corrections
and found that treating every report as final failed recovery on 5.8 after an
agent restart, that a report with a foreign nonzero request ID left its
request pending until close, and two text errors. Those were corrected, and
agent-restart and foreign-report cases bring the suite to eighteen. The second
recheck (fup20260924_202048, fup20260924_201206) found that an SNMPv3
retransmission that failed to send stayed pending until close, because
callbacks carrying the request's own PDU were matched by message ID. They are
now matched by request ID, and a case that fails the retransmission at the
libc socket boundary with the existing socket_fault fixture brings the suite
to nineteen. The third recheck (fup20260924_212921) passed: every callback
path completed exactly once on both versions, and a message-ID mutant fails
the new case. The Rocky 5.8 package removed a request after a failed
retransmission, so a retry after that failure was not reproduced; the adapter
covers it through the same request-ID match, a conclusion from source
reading.

Final build /tmp/snmp-m8-native-20260924-l (module
8ce4d6d08094ef0cad279ff208771f459fae838327e6bba0e7bebf274f593dc2, test IOC
fc047b1bdf195b5d2b5c3a740774cf3691e580322d87e7cde7d29402799bf44a) passes
native 19/19 in /tmp/snmp-m8-native-tests-20260924-i. The Rocky 8 build of the
same sources passes native 19/19 in /tmp/snmp-m8-rocky8-native-20260924-e
(test IOC 6b70929ab8f7c61622cc8fbc2f80c21a23f4a06d79bca00e221fd2789facbd32;
container-command.txt holds the exact container invocation). Observed: twenty
6000-varbind GETs are rejected with no completion and 8212 KiB (Debian) and
8148 KiB (Rocky) resident growth, against about 6.9 MB per leaked PDU before
the correction; USM rejections complete once as security errors, including a
report with a foreign request ID; after the agent restarts with engineBoots
7 the next GET receives notInTimeWindow, is retransmitted once and completes
as a response on both platforms; an SNMPv3 retransmission failed by one
sendmsg EIO at the socket boundary completes once as send_failed 1.5 s after
the first attempt, before close; the three pending requests at close complete
as Closed through library callbacks during snmp_sess_close.

The transport objects devSnmp.o, snmpRequest.o, snmpEpics.o, snmpRegister.o
and snmpSessShow.o of build -l disassemble identically to build
/tmp/snmp-m8-native-20260924-h. On build -h, Debian 13 passes sequencing 9,
failures 10, lifecycle 15, batch 10, robustness 16, accounting 3 and
conversion 2 in /tmp/snmp-m8-native-tests-20260924-e, against a db9ebf5
waveform baseline recollected with the current profile in
/tmp/snmp-m8-native-tests-20260924-b/baseline-waveforms-b. Rocky 8 passes the
same seven suites and its own db9ebf5 baseline in
/tmp/snmp-m8-rocky8-native-20260924-b from the same sources.

Retained failures: the first Debian conversion run in
/tmp/snmp-m8-native-tests-20260924-b, whose waveform baseline predated the
5.8 profile declaration; native runs -c on Debian, where the security-error
cases timed out before reports were matched by message ID; native in the
Rocky -b run, where 5.8 security reports were classified as protocol errors
and one IOC stopped at startup in rsrv_init before the adapter ran; and the
sixteen-case passes on builds -i and Rocky -c and the eighteen-case passes on
build -j and Rocky -d, whose report and message matching the rechecks later
found wrong; and the first nineteen-case run -h, whose new assertion expected
sendto where the library called sendmsg. None is relabeled. These results do not qualify record-path discovery isolation,
worker processes, profiles or T12.

##### Full-Plan Review Evidence

The 2026-09-23 review reports distinguish new execution from retained evidence:

- [EPICS report](../work/review_sessions/20260923_104501_snmp-architecture/reviews/rev20260923_135841_subagent_gpt6_plan_epics_full_plan.md):
  the real retained candidate ran all 19 request tests successfully in 49.842 s,
  exit 0. Its 18 source inputs and four binary identities matched the retained
  manifest; no rebuild was claimed. The report names all 19 new evidence
  directories, each with startup, IOC, peer and client logs and graceful
  shutdown. Its legacy negative control observed an unsolicited GET and failed
  the idle assertion, with an additional cleanup KeyError; it is not a clean
  single-failure control or a passing suite.
- [Transport report](../work/review_sessions/20260923_104501_snmp-architecture/reviews/rev20260923_135535_subagent_gpt6_plan_transport_full_plan.md):
  the byte-identical native probe/runner and real snmpd completed 26 short cases
  with expected success/timeout outcomes, one terminal callback per case, no
  proxy/reader errors and five zero agent exit codes. The top-level runner exit
  was unavailable. Combined evidence is
  `/tmp/snmp-review-transport-yuym15s7/evidence/20260923_134258-short/results.json`,
  SHA-256 `b75012c22982521896338b47377bc4b1b7a300124b10618d5e3d21e9bc5dae5b`.
  Recheck with `python3 /tmp/snmp-review-transport-yuym15s7/run_budget.py --stage short`;
  this creates new native evidence, not an IOC/helper verification result.
- [Verification/build report](../work/review_sessions/20260923_104501_snmp-architecture/reviews/rev20260923_140116_subagent_gpt6_plan_verification_initial.md):
  static and retained-evidence review; no new runtime execution. The existing
  19+12+12 results and 32-case native experiment remain separate evidence sets.
  Neither APC suite was rerun in this review round.

These local review and scratch paths must be preserved before cleanup or
transfer; `work/` is not a portable committed evidence store. The design result
and evidence limits are recorded here so plan status does not depend on chat
history. No M8 runtime test label is closed by these reports.

Design preparation observations on 2026-09-23: the module's v3 parser accepts
MD5/SHA and DES/AES aliases; key derivation occurs in the group constructor;
each transaction opens/closes a session; the read worker holds the session
mutex through select/read/timeout. The installed `pkg-config --modversion
netsnmp` reports `5.9.4.pre2`. Installed headers declare SHA-2 OIDs, which is not
proof of usable crypto or device interoperability. The architecture's sources
and explicit feasibility checks distinguish these facts from proposed behavior.

The D7 API audit on 2026-09-23 read the installed session API manuals and
`session_api.h`, `library/{snmp_api,keytools,scapi,snmpusm}.h`, plus the official
sources cited in `docs/snmp-architecture.md`. `dpkg-query -W libsnmp-dev
libsnmp40t64` reports `5.9.4+dfsg-2+deb13u1`; its API/pkg-config version string
is `5.9.4.pre2`. Both identifiers are retained rather than treated as different
installations. `nm -D --defined-only /usr/lib/x86_64-linux-gnu/libnetsnmp.so`
confirmed the selected Single Session API, large-FD functions, algorithm
lookup/OID helpers, generate_Ku/generate_kul, PDU, OID and error symbols. This
is source/header/ABI evidence, not an executed authentication or recovery test.

##### Native Discovery Feasibility Evidence

Observed at 2026-09-23T10:19:43-07:00 on Debian 13, using installed
libsnmp40t64/libsnmp-dev 5.9.4+dfsg-2+deb13u1 and matching snmpd/snmp packages
extracted under `/tmp/snmp-design-20260923/runtime`. No system package installation
or hardware access was used. The real snmpd and real snmpget used disposable
SHA-256/AES-128 authPriv credentials on loopback; the GET target was sysUpTime.0.

The native C probe uses the real Single Session API, generate_Ku and callback
path. A real UDP socket receives and drops discovery traffic for the failed
endpoint. timeout is 4 s and retries is zero. Each mode runs three samples with
a warmed healthy session. In the process mode, the parent submits the measured
healthy GET only after the external UDP receiver observes the failed endpoint's
discovery packet; monotonic timestamps verify completion before that native
send returns. There is no internal library mock or fabricated response.

| Mode | Healthy result latency, ms | Observed blocking |
| --- | --- | --- |
| Healthy control | 0.208, 0.044, 0.128 | None introduced. |
| One serialized owner | 4006.476, 4015.113, 4017.590 | First snmp_sess_async_send consumed 4000.441-4004.080 ms; healthy response service waited. |
| Independent processes | 0.195, 0.150, 0.100 | Faulted child first send consumed 4003.485-4004.134 ms; healthy callbacks completed during that wait. |

All nine measured healthy callbacks contained one valid sysUpTime response;
each C run exited zero and the real agent exited zero on shutdown. The blocked
session open returned in 5.605-13.303 ms across the six fault samples. This
establishes a blocking first-send path in this installed build, not a universal
claim that session open never blocks. Three observations per mode do not
establish p99, resource stability, reboot behavior, the 400 ms IOC completion
deadline, explicit-engine operation, or any full T8/T18 acceptance result.

Local evidence directory:
`/tmp/snmp-design-20260923/evidence/3007941163549235/` contains results.json,
agent.log and the independent client oracle.txt. Sources and runner are
`/tmp/snmp-design-20260923/discovery_probe.c` and `run_probe.py`; recheck with
`python3 /tmp/snmp-design-20260923/run_probe.py`. The runner recompiles the real
probe and writes a new evidence directory. This path is local scratch evidence,
not a portable committed test fixture; preserve it before relying on it from
another machine or after cleanup.

| Artifact | SHA-256 |
| --- | --- |
| discovery_probe.c | 121ff42e760e4da8eb7d0947e64af8922717bc483b4f754b88fb9f063b00fcb1 |
| discovery_probe executable | ba3bf93468e193b99d542b97650eb86ea7abaa3333170689c79ed955c88da311 |
| run_probe.py | fd80e1e402282caba61d39c4f84961a4142b4a3a23f056251b81c6c44a97b1f0 |
| Linked libnetsnmp.so.40 | c85574a4ab075956e487bdf831bb3484680311b1865084ad4e30206179b333d1 |

The audit classified the draft's separate derivation/cache ownership and
mandatory asynchronous discovery as unnecessary module responsibilities under
D7. Native discovery delay is now observed in the bounded experiment above;
full IOC isolation and same-engine/user state behavior remain unverified under
T8/T9/T15/T18. D8 removes live replacement from the current
scope; T9 now covers startup snapshots and process restart. Independent design
review is recorded under T14; final implementation review remains pending.
Reference-format checks use IEEE guide T for
architecture entries 1, 2, 7, 8, 9, 10 and 11, and P (Standard Online) for entries
3, 4, 5 and 6.

##### Native Timeout And Retry Evidence

Observed from 2026-09-23T12:25:21-07:00 through
2026-09-23T12:33:06-07:00 on Debian 13 with
libsnmp40t64/libsnmp-dev 5.9.4+dfsg-2+deb13u1 and matching extracted
snmpd/snmp tools. The linked library digest matches the earlier discovery
experiment. This is native API behavior evidence, not an IOC, adapter or
worker implementation acceptance result.

The C probe calls the real Single Session API with SHA-256/AES-128 authPriv
and disposable credentials. A loopback UDP proxy only forwards, drops or
delays original datagrams between the probe and real snmpd. It does not
construct replies or replace internal library functions. The GET target is
sysUpTime.0; SET uses writable sysContact.0 on the disposable agent.
Each SET case first resets and reads the target using real snmpset/snmpget,
then verifies the changed value after the measured request times out.

Elapsed time starts before the measured snmp_sess_async_send call and ends
after terminal handling. It includes blocking first-send discovery when
needed, but excludes key generation, session opening and optional warm-up.
The caller services asynchronous requests with a maximum 10 ms select slice;
native timeout/retry settings are unchanged. Native synchronous discovery
uses the library's own service loop. The harness guard is a test abort limit,
not a proposed production watchdog.

The short run passed 26/26 cases: healthy cold/warm controls and the six fault
scenarios below at timeout 200000 us and retries 0, 1, 3 and 5. The default run
passed 6/6 cases with timeout 10000000 us and retries 5, read directly from
the current devSnmp.cpp defaults. Every measured request produced exactly one
terminal callback; intermediate RESEND callbacks were retained separately.
Both runners exited zero, all seven agent lifetimes ended with exit code zero,
and no probe/agent process remained. Source/binary snapshots match the result
digests, and each per-case result matches its combined report.

| Default-setting scenario | Elapsed, ms | Outgoing packets |
| --- | --- | --- |
| Cold discovery: all requests dropped | 60054.169 | 6 discovery |
| Warm GET: requests dropped | 60001.543 | 6 application |
| Warm GET: replies dropped | 60001.535 | 6 application |
| Late discovery, then application requests dropped | 118056.532 | 6 discovery + 6 application |
| Late timeliness REPORT after agent restart, then reply dropped | 68009.912 | 7 application |
| Warm SET: replies dropped after application | 60001.639 | 6 application |

For late discovery, the proxy drops the first R discovery requests and delays
the real response to the final attempt by 0.8 times the native timeout.
It then drops application requests. For late timeliness recovery, the actual
agent restarts using its saved persistent state, preserving engineID and
increasing engineBoots. The proxy drops the first R real REPORTs, delays the
next by the same fraction, and drops the subsequent application response.
Packet metadata confirms the stable identity and increased boots value.

Ordinary loss emitted R+1 packets at approximately constant timeout intervals.
The delayed REPORT scenario emitted R+2 application packets: even retries=0
produced one native recovery resend before terminal timeout. All five SET
reply-loss cases confirmed that the agent value changed despite client
failure. These observations establish neither exactly-once device execution
nor the baseline module's output-record semantics.

The exact Debian source package was extracted with its distribution patches
under `/tmp/snmp-native-budget-20260923/source/net-snmp-5.9.4+dfsg/`.
The inspected paths explain the measurements:

- `snmplib/snmp_api.c:5095` invokes engine discovery on first send when the
  security engine ID is absent; `snmplib/snmpusm.c:3691` performs that discovery
  through snmp_sess_synch_response.
- `snmplib/snmp_api.c:5414` initializes the request retry count and timeout;
  snmp_resend_request at line 6732 retains that timeout and resets expiry.
  The ordinary timeout path at line 6868 stops at retries >= configured retries.
- The recoverable REPORT path at `snmplib/snmp_api.c:5786` instead permits a
  resend while retries <= configured retries. That distinction accounts for
  the additional native resend observed above.
- `snmplib/snmp_client.c:1127` services synchronous discovery through its own
  select/read/timeout loop. Timers depend on scheduling and service progress;
  their interval sum is not a strict wall-clock completion guarantee.

For this inspected UDP/USM path, let T be the effective per-attempt timeout
and R the configured retry count. Ordinary loss uses (R+1) times T in timer
intervals; application timeliness recovery can use (R+2) times T. Allowing one
normal engine discovery followed by such an application exchange gives the
conditional interval sum (2R+3) times T, or 130 s at the inherited defaults.
This is source-derived accounting, not an executed combined 130 s scenario,
an accepted watchdog value, or a bound for every native path. The separate
numeric decision below selects the operating allowance and checked limits;
it does not turn that allowance into measured evidence. The Debian 12 and Rocky 9
native-only extensions are recorded below; explicit engine IDs, other security
settings and the actual worker path remain unverified.
No native settings or record deadlines were changed by this experiment.

Evidence root: `/tmp/snmp-native-budget-20260923/evidence/`.
The complete runs are `20260923_122521-short/` and
`20260923_122559-defaults/`; each retains results.json, per-case packet/event
metadata, source/binary/runner snapshots, agent state/logs and the client oracle.
Recheck with `python3 /tmp/snmp-native-budget-20260923/run_budget.py --stage short`
or the same command with `--stage defaults`; each creates a new evidence
directory. These are local scratch artifacts and must be preserved before
cleanup or transfer to another machine.

The excluded `20260923_122311-short/` run retains a failed restart fixture:
engineBoots did not increase because snmpd started with -C without explicitly
loading its saved persistent file. That run does not verify timeliness
recovery. Both complete runs above explicitly load the agent's saved state
on restart and verify the boots increase from real packets.

| Artifact | SHA-256 |
| --- | --- |
| native_budget_probe.c | bc90d70b538293627f7153881c8c7db431955751d293edc14e804c7f1a70a177 |
| native_budget_probe executable | 5a41f9d43454a0f4d6d0d3163e6cd65e26994df402b3bd1257e39ff5182cf379 |
| run_budget.py | 967f81d258e02756d608abd7531b4bce6698a727f66371ca4b8e1922b0ea2493 |
| Short-run results.json | be5065dc1189d74fd2c310bb83c4b8c7f9acb94ed05c2fcd786c3080d0c77f04 |
| Default-run results.json | 3c8cbaf9757804b9b59c9d8ba7d6c501b6a7361e8c4d09a48ffc3450931e1f9f |
| Patched snmplib/snmp_api.c | 9e3f9931b84575b75365429cf18f114fe47a1bbd6852f5379514ff922cd3bf1e |
| Patched snmplib/snmpusm.c | 797860e7df485a0a82ffe5127fe19d9bc19b149eb43fdf90bb65ccd6484bd154 |
| Patched snmplib/snmp_client.c | 88819c4157b726c4d2f345b801093540ed29aa2fd70c5664a86fe135aae13f2b |

##### Additional Native Platform Observations

Observed from 2026-09-24T07:45:02-07:00 through
2026-09-24T07:53:29.152947-07:00. The same native C probe was compiled and
executed in the immutable Debian 12 and Rocky 9 images used by M5. Debian 12
uses Net-SNMP 5.9.3/GCC 12.2.0; Rocky 9 uses Net-SNMP 5.9.1/GCC 11.5.0.
Each platform passes all 26 short cases and all six default-setting cases
against real native snmpd and the external UDP proxy. Each platform's seven
agent lifetimes exit zero. This is native API evidence, not IOC, adapter,
large-FD, persistent-worker or hardware acceptance.

| Default-setting scenario | Debian 12 elapsed, ms | Rocky 9 elapsed, ms | Outgoing packets |
| --- | ---: | ---: | ---: |
| Cold discovery: all requests dropped | 60053.814 | 60049.395 | 6 |
| Warm GET: requests dropped | 60001.197 | 60001.193 | 6 |
| Warm GET: replies dropped | 60001.455 | 60001.136 | 6 |
| Late discovery, then application requests dropped | 118054.313 | 118052.145 | 12 |
| Late timeliness REPORT after agent restart | 68003.063 | 68003.532 | 7 |
| Warm SET: replies dropped after application | 60001.457 | 60001.246 | 6 |

Source SHA-256 remains
bc90d70b538293627f7153881c8c7db431955751d293edc14e804c7f1a70a177.
The Debian runner is unchanged; the Rocky runner changes only the native
library path used for artifact identity. Native logic and assertions are
unchanged. Rocky compilation requires -fPIE with its native RPM linker specs;
the initial failed non-PIE build is retained and does not count as a run.

Evidence root: /tmp/snmp-native-platform-20260924-a/. verified-results.json
records all four result hashes, source/runner/binary identities and exact
result paths. Each combined result was compared with its per-case file, and
retained source/runner/binary snapshots were rehashed. Launch records identify
the immutable images and mounts; build/loaded-library/version records and
per-case native packets/callbacks are preserved. The observed late-discovery
duration does not prove a universal 150 s wall-clock guarantee. No M8 runtime
test label or watchdog implementation is accepted by these observations.

##### Finalized Watchdog Contract

Decision Date: 2026-09-23. D9's numeric policy is finalized at **150000 ms**
for inherited timeout/retries. The normative calculation and lifetime rules
are in `docs/snmp-architecture.md`, Worker Watchdog Policy, and the watchdog ADR.
The default comprises 130 s of native timer intervals and a selected 20 s
operating allowance. Timeout/retry changes recalculate the bound; a worker
uses the largest endpoint requirement. Explicit overrides must cover that
requirement. The deadline starts before the first transaction frame byte and
never resets on progress or native recovery. Record acquisition deadlines stay
independent. This resolves the numeric policy decision, not T5/T17/T18 runtime
acceptance or the unexecuted platform matrix.

##### Closure Evidence

- None. The concrete design draft and native feasibility/retry evidence are prepared;
  D9 records the accepted watchdog policy and T14 records the completed
  three-reviewer full-plan assessment with no new demonstrated plan defect.
  The numeric policy is finalized; replacement implementation,
  full v3 IOC verification and final implementation review remain pending.
  Decision Date: 2026-09-24. The overall plan is accepted and replacement
  implementation is authorized; physical execution remains subject to G2/G3.

## Backlog

### Work

| ID | Work unit | Type | Status | Ready | Deps | Done when / Evidence |
| --- | --- | --- | --- | --- | --- | --- |

No unassigned work is recorded in this initial generation. Out-of-scope ideas
are not approved work items.

### Backlog Details

None.
