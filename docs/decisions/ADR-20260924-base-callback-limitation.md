# ADR: Continue Development With A Documented Base Callback Limitation

Date: 2026-09-24
Status: accepted
Source Session: `work/review_sessions/20260923_104501_snmp-architecture`
Source Decisions: session D008; canonical M5 dependency-limitation decision

## Context

The request path publishes an owned terminal acquisition result before asking
EPICS Base to execute its completion callback. A rejected callback registration
leaves the result Ready and retries admission. It does not consume the result,
clear PACT or run FLNK before Base executes the callback.

The observed Debian 12 Base 7.0.10 library has an overflow flag that can
remain set after the callback ring becomes empty. A producer observes a full
ring, the consumer drains it, and the producer then sets the flag. Subsequent
callbackRequest calls reject that flag before attempting a ring push. The
consumer only clears it after popping an item, so ordinary retries cannot
recover admission in that state.

Actual unchanged IOC executions with a two-entry callback queue showed
completed acquisitions remaining Ready during the ten-second test wait.
Two independent hardware-breakpoint executions reproduced the interleaving
by delaying only the owned producer thread. Actual public pressure tests
failed while repeated raw samples showed an empty ring and a set overflow
flag. The earlier natural failures did not capture that internal state;
their exact interleavings remain unobserved. The canonical M5 evidence owns
the exact binary identities, measurements and results.

## Decision

Continue local module development with this dependency limitation documented.
Defer Base modification and review its proposed correction separately. Keep
the current module completion ownership, actual queue-pressure assertions and
all original failure records unchanged.

This is an explicit local development exception for the identified limitation.
It does not make a failed test pass, qualify an untested platform, approve a
dependency patch or authorize deployment. Other required failures still block
the milestone. Every final matrix must execute and report actual outcomes;
a handoff using the exception must name it explicitly.

## Consequences

An SNMP result or expired acquisition deadline does not guarantee record
completion while Base callback admission is stuck. PACT may remain set and
FLNK may not execute. The retained VAL and successful-generation diagnostics
must not be interpreted as a fresh completed sample merely because the
transport received another response.

The demonstrated platform is the recorded Debian 12 Base 7.0.10 build and the
two-entry pressure fixture. Passing Debian 13/Rocky 9 runs do not prove their
queues immune. Failure probability at ordinary production queue sizes was
not measured. Increasing the queue size can change exposure but is not a
verified correction. Neither a transport-worker change nor its watchdog
removes this Base-side completion dependency.

Physical and production acceptance remain separate. A future handoff must
carry this limitation into the operating review; local continuation does not
waive device timing, recovery or deployment criteria.

## Alternatives Considered

- Repair Base before continuing: deferred by the current development decision.
  A candidate correction would derive admission from the synchronized ring
  push and retain overflow reporting independently. It is not implemented or
  verified by this decision.
- Increase queue size or relax the completion assertion: not selected as a
  correction; neither demonstrates recovery from the observed stuck state.
- Change the module's completion mechanism: not selected. This would change
  the reviewed ownership and shutdown contract and require its own design
  and real-path qualification.

## Verification Or Enforcement

The shipped pressure test and matrix keep their actual failure/exit semantics.
Record the identified dependency failure separately from unrelated failures;
do not add a blanket timeout waiver or an automatic expected-failure match.

Before adopting any Base correction, independently review its concurrency,
overflow reporting and interrupt-context constraints, build the exact changed
dependency in isolation, and run Base callback tests plus the unchanged SNMP
pressure, sequencing, shutdown and complete platform matrices. Demonstrate
recovery under the actual failing schedule and retained full-queue rejection.
No mock or replacement of an internal callback/ring function qualifies that
path. Installation or deployment requires its own scoped authority.

The existing Base callbackTest and callbackParallelTest each make 169 initial
submissions, each scheduling a second callback, for 338 expected invocations
against the default 2000-entry queue. They do not assert full-queue
rejection or overflow statistics. They are regression checks, not sufficient
overload qualification. Additional real-path tests must hold actual consumers,
fill the queue, verify rejection without callback ownership, release consumers
and verify exactly one invocation per accepted entry. Repeat with multiple
producers/consumers and every priority, including the demonstrated delayed
failed-producer schedule.

For the proposed correction, the overflow flag controls diagnostic suppression
only. The counter would record reported overflow diagnostic events after
suppression, not suppressed diagnostics, every rejected request or an exact
number of full episodes; suppression resets with consumer
progress and is not a time-based rate limit. A stale diagnostic flag would be
allowed while admission follows the actual ring result. Verify that distinction
with actual concurrent overload tests before adoption. Check each platform's
selected atomic/interrupt implementation; Linux process tests do not qualify
interrupt-context behavior. Genuine queue saturation or stopped consumers
still prevent a finite completion guarantee even if the false admission gate
is removed.
