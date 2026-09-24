# ADR: Preserve Native Retry Policy In Worker Watchdog Bounds

Date: 2026-09-23
Status: accepted
Source Session: `work/review_sessions/20260923_104501_snmp-architecture`
Source Decisions: session D001/D002; canonical milestone D9

## Context

The worker supervisor needs a finite lifetime bound while the SNMP module
preserves effective native timeout and retry settings. A fixed watchdog default
that cannot contain those settings would reject a compatible configuration or
interrupt its intended retry behavior. The record acquisition deadline is a
separate limit and must remain responsive during native transport work.

## Decision

Preserve native timeout/retry settings, including inherited defaults and valid
legacy overrides. When WorkerProgressLimitMSec is omitted, derive a finite
watchdog bound that covers admitted native transport budgets and separately
bounded discovery/recovery and local handling allowances. Every endpoint sharing
a worker must fit that worker's effective bound.

An explicitly configured bound must cover the same required budget. Reject an
undersized, nonpositive or unrepresentable value before application traffic;
never clamp the bound or reduce native timeout/retries to make it fit. Native
Net-SNMP remains the only source of wire retransmissions.

The numeric contract was finalized on 2026-09-23 after the Debian 13 native
source audit and 32 executed cases recorded in M8. Let T_us be the finite
effective per-attempt timeout in microseconds and R the effective retry count:

```text
B_us = (2 * R + 3) * T_us
A_us = max(5000000, 2 * T_us, ceil(B_us / 10))
RequiredMSec = ceil((B_us + A_us) / 1000)
WorkerMSec = max(RequiredMSec for every endpoint assigned to the worker)
```

The inherited T_us=10000000 and R=5 give **150000 ms (150 s)**: 130 s of
native timer intervals plus a selected 20 s operating allowance. B_us includes
normal discovery and application timeliness recovery. A_us provides a 5 s
floor, two timeout intervals and a proportional floor for larger legacy retry
budgets. It is policy, not a measured upper bound or additional wire retries.
Warm sessions, explicit engine IDs and v1/v2c use the same conservative rule.

Use checked uint64 arithmetic through microseconds, millisecond ceiling and
nanosecond interval/deadline conversion. Reject unrepresentable intermediate
or final values, invalid native timeout values and retry counts above
INT_MAX-1. Explicit overrides use the existing positive int API range; automatic
calculation is not capped at INT_MAX milliseconds. The architecture's Worker
Watchdog Policy defines admission, rounding and dispatch checks.
A validated explicit override replaces WorkerMSec as the effective interval;
without an override, use WorkerMSec.

Arm once before the first transaction frame byte and retain that absolute
deadline through IPC, opening, discovery, native retries/recovery and validated
result receipt. Progress notifications, partial frames and sub-operations never
reset it. Bootstrap/binding and shutdown retain their separate bounds.

## Consequences

Normal startup does not require an additional watchdog override merely to keep
the existing transport defaults. Automatic calculation and deadline arithmetic
must be finite and checked. The former proposed 10-second default and 600000 ms
ceiling do not constrain the derived policy.

Long native retry budgets do not extend record acquisition deadlines, allow
extra module retries or SET replay, or relax progress for other devices. A
worker may retain transport context after a record has completed with an error.
Profile and credential changes still require a full IOC process restart.

## Alternatives Considered

Retaining the fixed 10-second default and requiring a startup override would
introduce a configuration migration. The selected policy preserves inherited
transport settings without that requirement. Silently shortening native timeout
or retry settings would violate the existing compatibility contract.

## Verification Or Enforcement

The number is a finalized design contract, not a verified worker implementation
or a hard wall-clock guarantee. The allowance is selected policy. Supported
packages beyond the inspected Debian 13 build require their own source and
real-path qualification before a platform is declared supported.

The canonical M8 plan owns implementation ordering and results. Its T5/T17/T18
checks require real IOC startup with omitted settings, both published example
endpoints, rejection of an explicitly undersized override before application
traffic, and baseline-versus-candidate native retry/SET behavior under packet
loss. These tests must exercise the actual IOC, helper, Net-SNMP and external
agent path. This accepted policy is not evidence that the calculation or runtime
has been implemented or verified.
