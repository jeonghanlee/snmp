"""Verify diagnostic meaning and actual healthy-host acquisition latency."""

import math
import re
import time

from diagnostics import observations, sample, verify as verify_diagnostics
from ioc import settings, write_json
from request_cases import Scenario, ScenarioTest


CASES = ("queued_age_and_totals", "trace_disabled", "healthy_with_silent_peer")
LATENCY_CYCLES = 1000
CHUNK_CYCLES = 100


class AccountingTest(ScenarioTest):
    def test_queued_age_and_totals(self):
        with self.scenario("queue-age", hold=True) as s:
            s.put("A.PROC")
            s.wait(lambda: bool(s.peer.held), "real active request")
            s.put("B.PROC")
            first = sample(s)
            self.assertEqual((first["A"]["state"], first["B"]["state"]), ("inflight", "queued"))
            self.assertEqual((first["B"]["claimed_ns"], first["B"]["dispatched_ns"]), (0, 0))
            time.sleep(0.1)
            second = sample(s)
            self.assertGreater(second["B"]["queue_age_ms"], first["B"]["queue_age_ms"])
            for record in ("A", "B"):
                self.assertEqual((second[record]["valid"], second[record]["last_valid_age_ms"]), (0, -1))
            self.assert_totals(s, queued=1, active=2, accepted=2, valid=0, completed=0)
            s.peer.hold = False
            s.peer.release()
            s.done("A", 1, 101)
            s.done("B", 1, 102)
            sample(s)
            self.assert_totals(s, queued=0, active=0, accepted=2, valid=2, completed=2)
        verify_diagnostics(s)

    def assert_totals(self, scenario, **expected):
        lines = re.findall(r"SNMPDIAG_TOTAL ([^\n]+)", (scenario.work / "ioc.log").read_text())
        self.assertTrue(lines, "Missing actual request totals")
        observed = {key: int(value) for key, value in (field.split("=") for field in lines[-1].split())}
        self.assertEqual(observed, dict(records=4, rejected=0, failed=0, callback_retries=0, **expected))

    def test_trace_disabled(self):
        s = Scenario(self, "trace-disabled", timeout_us=200000, extra=('devSnmpSetParam("RequestTrace", 0)',))
        try:
            for count, mode in enumerate(("normal", "drop", "normal"), 1):
                s.peer.mode = mode
                s.put("A.PROC")
                s.done("A", count, 101, severity=3 if mode == "drop" else 0, status=1 if mode == "drop" else 0)
                row = sample(s)["A"]
                self.assertEqual((row["accepted"], row["completed"]), (count, count))
                self.assertEqual(row["last_valid_generation"], 1 if count == 2 else count)
                self.assertEqual((row["valid"], row["failed"]), ((1, 0), (1, 1), (2, 1))[count - 1])
                self.assertGreaterEqual(row["total_ms"], 0)
        finally:
            s.close(verify=False)
        self.assertEqual(s.driver, [])
        self.assertEqual(len(s.audits), 3)
        self.assertEqual(len(s.peer.requests), 3)
        self.assertEqual(s.peer.errors, [])
        self.assertTrue(all(r["pact"] == 1 for r in s.audits))
        self.assertEqual([r["severity"] for r in s.audits], [0, 3, 0])
        write_json(s.work / "diagnostics.json", observations(s.work))

    def test_healthy_with_silent_peer(self):
        timings = {}
        for loaded in (False, True):
            timings[str(loaded)] = []
            for offset in range(0, LATENCY_CYCLES, CHUNK_CYCLES):
                with self.scenario(f"timing-{loaded}-{offset}", peers=2, timeout_us=60000000,
                                   extra=('devSnmpSetParam("RequestTimeoutMSec", 60000)',)) as s:
                    if loaded:
                        s.peer.hold = True
                        s.put("A.PROC")
                        s.wait(lambda: bool(s.peer.held), "silent host has a real outstanding request")
                    for count in range(1, CHUNK_CYCLES + 1):
                        s.put("B.PROC")
                        s.done("B", count, 102)
                    if loaded:
                        self.assertEqual(s.get("A.PACT"), "1", "Silent-host precondition ended early")
                        self.assertEqual(s.get("AuditA"), "0")
                        s.peer.release()
                        s.done("A", 1, 101)
                verify_diagnostics(s)
                timings[str(loaded)] += [(end["time"] - begin["time"]) / 1e9
                                         for begin, end in zip(s.events("B", "accepted"), s.events("B", "complete"))]
        summaries = {key: dict(count=len(values), maximum=max(values),
                               p99=sorted(values)[math.ceil(0.99 * len(values)) - 1])
                     for key, values in timings.items()}
        write_json(self.work / "timing.json", dict(samples=timings, summary=summaries))
        limits = settings()["profile"]["limits"]
        self.assertEqual({r["count"] for r in summaries.values()}, {LATENCY_CYCLES})
        self.assertLess(summaries["True"]["maximum"], limits["healthy_max_seconds"])
        self.assertLessEqual(summaries["True"]["p99"], summaries["False"]["p99"] + limits["healthy_p99_delta_seconds"])
