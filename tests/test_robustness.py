"""Real request deadline and response validation through the public IOC path."""

import time

from diagnostics import verify as verify_diagnostics
from owned_thread import paused_thread
from request_cases import ScenarioTest


MODES = ("reverse", "missing", "duplicate", "extra", "wrong_oid", "exception", "no_instance",
         "end_view", "wrong_type", "oversized", "malformed", "mixed")
CASES = ("late_result_without_service_tick", "queued_expiry_without_service_tick",
         "old_and_duplicate_replies", "retry_exhaustion") + tuple("response_" + mode for mode in MODES)
DEADLINE_MS = 400
LATE_SECONDS = 0.6
RECEIVE_SECONDS = 0.1


class RobustnessTest(ScenarioTest):
    def test_late_result_without_service_tick(self):
        with self.scenario("late-deadline", extra=(
                f'devSnmpSetParam("RequestTimeoutMSec", {DEADLINE_MS})',)) as s:
            s.put("A.PROC")
            s.done("A", 1, 101)
            s.peer.values[1] = 909
            s.peer.hold = True
            with paused_thread(s.runtime, "snmpComplete") as suspension:
                s.put("A.PROC")
                s.wait(lambda: bool(s.peer.held), "actual held request")
                self.assertEqual(s.get("A.PACT"), "1")
                time.sleep(LATE_SECONDS)
                s.peer.release()
                time.sleep(RECEIVE_SECONDS)
            s.done("A", 2, 101, severity=3, status=1)
            s.peer.hold = False
            s.peer.values[1] = 202
            s.put("A.PROC")
            s.done("A", 3, 202)
        accepted = s.events("A", "accepted")[1]
        result = s.events("A", "result")[1]
        self.assertGreaterEqual(result["time"] - accepted["time"], DEADLINE_MS * 1000000)
        self.assertLess(result["time"], suspension["resume_requested"],
                        "Late result must be handled before the service thread resumes")
        self.assertFalse(result["success"])

    def test_queued_expiry_without_service_tick(self):
        with self.scenario("queued-deadline", extra=(
                f'devSnmpSetParam("RequestTimeoutMSec", {DEADLINE_MS})',)) as s:
            s.put("Both.PROC")
            s.done("A", 1, 101)
            s.done("B", 1, 102)
            first = len(s.peer.requests)
            s.peer.values.update({1: 909, 2: 808})
            s.peer.hold = True
            with paused_thread(s.runtime, "snmpComplete") as suspension:
                s.put("A.PROC")
                s.wait(lambda: bool(s.peer.held), "blocking request transmitted")
                s.put("B.PROC")
                self.assertEqual(s.get("B.PACT"), "1")
                time.sleep(LATE_SECONDS)
                s.peer.hold = False
                s.peer.release()
                time.sleep(RECEIVE_SECONDS)
                self.assertEqual([r["oids"] for r in s.peer.requests[first:]], [[1]],
                                 "Expired queued record emitted an application GET")
            s.done("A", 2, 101, severity=3, status=1)
            s.done("B", 2, 102, severity=3, status=1, failure="queued")
            s.put("Both.PROC")
            s.done("A", 3, 909)
            s.done("B", 3, 808)
        result = s.events("B", "result")[1]
        self.assertLess(result["time"], suspension["resume_requested"])

    def response_matrix(self, mode):
        for offset in range(0, self.cycles(), 20):
            with self.scenario("response-" + mode, fixture="batch.db", timeout_us=200000) as s:
                for cycle in range(min(20, self.cycles() - offset)):
                    number = 3 * cycle
                    s.peer.mode = "normal"
                    s.peer.faults.clear()
                    s.peer.values.update({n: 100 + n for n in range(1, 22)})
                    s.put("Many21.PROC")
                    s.done_many({"R" + str(n): 100 + n for n in range(1, 22)}, number + 1)
                    s.peer.hold = True
                    s.put("Block.PROC")
                    s.wait(lambda: bool(s.peer.held), "blocker holds the host")
                    s.put("Many21.PROC")
                    s.peer.values.update({n: 200 + n for n in range(1, 22)})
                    s.peer.mode = "normal" if mode == "mixed" else mode
                    if mode == "mixed":
                        s.peer.faults.update({1: "wrong_type", 2: "exception", 3: "oversized", 21: "no_instance"})
                    first = len(s.peer.requests)
                    s.peer.hold = False
                    s.peer.release()
                    s.done("Block", cycle + 1, 199)
                    s.wait(lambda: sum(len(r["oids"]) for r in s.peer.requests[first:]) == 21,
                           "all response matrix requests transmitted")
                    requests = s.peer.requests[first:]
                    if mode in ("missing", "duplicate", "wrong_oid"):
                        bad = {r["oids"][0] for r in requests}
                    elif mode == "mixed":
                        bad = set(s.peer.faults)
                    elif mode in ("reverse", "extra"):
                        bad = set()
                    else:
                        bad = set(range(1, 22))
                    s.done_results({"R" + str(n): (100 if n in bad else 200) + n for n in range(1, 22)},
                                   number + 2, {"R" + str(n) for n in bad})
                    s.peer.mode = "normal"
                    s.peer.faults.clear()
                    s.put("Many21.PROC")
                    s.done_many({"R" + str(n): 200 + n for n in range(1, 22)}, number + 3)
            verify_diagnostics(s)

    def test_old_and_duplicate_replies(self):
        with self.scenario("old-replies", timeout_us=200000) as s:
            for cycle in range(self.cycles()):
                number = cycle * 4
                s.peer.values[1] = 101
                s.peer.hold = False
                s.put("A.PROC")
                s.done("A", number + 1, 101)
                old_success = s.peer.sent[-1]
                s.peer.hold = True
                s.peer.values[1] = 909
                s.put("A.PROC")
                s.wait(lambda: len(s.peer.held) == 1, "old request held")
                s.done("A", number + 2, 101, severity=3, status=1)
                s.peer.values[1] = 202
                s.put("A.PROC")
                s.wait(lambda: len(s.peer.held) == 2, "fresh request held")
                s.peer.release()
                s.peer.resend(s.peer.sent[-1])
                s.peer.resend(old_success)
                self.assertEqual(s.get("A.PACT"), "1")
                self.assertEqual(s.get("AuditA"), str(number + 2))
                s.peer.release()
                s.done("A", number + 3, 202)
                s.peer.resend(old_success)
                s.peer.hold = False
                s.peer.values[1] = 303
                s.put("A.PROC")
                s.done("A", number + 4, 303)
        verify_diagnostics(s)

    def test_retry_exhaustion(self):
        with self.scenario("retry-exhaustion", timeout_us=100000,
                           extra=('devSnmpSetParam("SessionRetries", 2)',)) as s:
            for cycle in range(self.cycles()):
                s.peer.mode = "normal"
                s.put("A.PROC")
                s.done("A", 3 * cycle + 1, 101)
                first = len(s.peer.requests)
                s.peer.mode = "drop"
                s.put("A.PROC")
                s.done("A", 3 * cycle + 2, 101, severity=3, status=1)
                wire = s.peer.requests[first:]
                self.assertEqual(len(wire), 3, "Native retry count differs from initial plus two retries")
                self.assertEqual(len({r["id"] for r in wire}), 1)
                s.peer.mode = "normal"
                s.put("A.PROC")
                s.done("A", 3 * cycle + 3, 101)
        verify_diagnostics(s)


for _mode in MODES:
    def _case(self, mode=_mode):
        self.response_matrix(mode)
    setattr(RobustnessTest, "test_response_" + _mode, _case)
