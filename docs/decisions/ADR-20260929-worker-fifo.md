# ADR: Admission-Order FIFO Per Worker

Date: 2026-09-29
Status: accepted
Source Session: `work/review_sessions/20260923_104501_snmp-architecture`
Source Decisions: D22, D23, D24

## Context

One worker serializes native transactions for one configured address. Legacy
polling, request reads, legacy SETs and request SETs must share bounded
admission while preserving each request's completion and original deadline.
The traditional transport gives SETs priority, with aging for waiting reads.

## Decision

Use one FIFO in admission order across all traffic classes at an address.
Different addresses retain independent workers. A later write cannot overtake
an earlier read. Batch only contiguous compatible GETs at the queue head;
neither a SET nor an incompatible GET may be skipped to fill a batch.

A repeated legacy SET to an OID with an unsent queued setting replaces that
setting's value without changing its position. Each request SET remains a
separate immutable command. Handoff freezes membership and values. Expiration
removes queued requests without transmission; record expiration cannot release
the worker while a native transaction is still active. Native retransmissions
remain the library's responsibility, and child loss never replays a SET.

## Consequences

FIFO removes traffic-class starvation among admitted work. A long native
transaction can delay later work at its address, including SETs; record
deadlines and the worker watchdog retain their distinct purposes. Polls enter
the queue when due, rather than reserving future positions. Batching does not
wait for additional members. Queue bounds default to 1024 pending commands and
1 MiB of encoded queued data per worker. `devSnmpSetQueueSize(address, count)`
changes only the selected address worker's count bound at startup or runtime. A decrease
retains existing tickets, FIFO positions and deadlines, rejecting new tickets
while count is at or above the new bound. In-place legacy SET replacement
remains eligible because it adds no ticket. The byte bound stays fixed.
The traditional transport remains a
comparison baseline until migration is qualified.

## Alternatives Considered

SET priority with read aging would preserve the earlier scheduling policy,
but would allow a later command to overtake an already queued read. Global
serialization across addresses would remove the required fault isolation.

## Verification Or Enforcement

Use the actual IOC/helper and packet observer to hold an active transaction,
admit GET/SET/GET, and verify wire order after release. Include queued legacy
SET replacement, immutable request writes, contiguous GET batching, mixed
profiles, queue exhaustion, expired generations and progress at another
address. Run on the supported Debian 13 and Rocky 8 builds. These are planned
checks; this decision does not claim that the implementation or tests passed.
