"""Acceptance of actual Base processing with delayed and immediate SNMP replies."""

import time

from diagnostics import verify as verify_diagnostics
from request_cases import ScenarioTest


CASES = ("idle_and_held_values", "immediate_responses", "late_waiter", "serial_chain",
         "active_put", "active_ten_puts", "put_completion", "five_active_scans",
         "extended_scan_alarm", "two_host_fanout", "invalid_fanout_link", "pini",
         "disable", "terminal_errors", "transport_failures")


class LifecycleTest(ScenarioTest):
    def test_idle_and_held_values(self):
        with self.scenario("idle", hold=True) as s:
            started = time.monotonic()
            while time.monotonic() - started < s.runtime.config["profile"]["idle_seconds"]:
                self.assertIsNone(s.runtime.process.poll())
                self.assertEqual(s.peer.requests, [])
                time.sleep(0.05)
            for cycle in range(self.cycles()):
                value = (101, 202, 202, 202)[cycle % 4]
                s.peer.values[1] = 909 if s.runtime.config.get("negative_control") == "wrong-value" else value
                s.put("A.PROC")
                s.wait(lambda: len(s.peer.held) == 1, "held response")
                self.assertEqual(s.get("A.PACT"), "1")
                self.assertEqual(s.get("AuditA"), str(cycle))
                s.peer.release()
                s.done("A", cycle + 1, value)
                self.assertEqual(len(s.peer.requests), cycle + 1)

    def test_immediate_responses(self):
        with self.scenario("immediate") as s:
            for cycle in range(self.cycles(immediate=True)):
                value = 1000 + cycle
                s.peer.values[1] = value
                s.put("A.PROC")
                s.done("A", cycle + 1, value)
            self.assertEqual(len(s.peer.requests), self.cycles(immediate=True))

    def test_late_waiter(self):
        with self.scenario("late", hold=True) as s:
            for cycle in range(self.cycles()):
                first, second = 1000 + cycle, 2000 + cycle
                s.peer.values[1] = first
                s.put("A.PROC")
                s.wait(lambda: len(s.peer.held) == 1)
                s.peer.values[1] = second
                s.put("Shared.PROC")
                self.assertEqual(s.get("Shared.PACT"), "1")
                self.assertEqual(s.get("AuditShared"), str(cycle))
                s.peer.release()
                s.done("A", cycle + 1, first)
                s.wait(lambda: len(s.peer.held) == 1)
                self.assertEqual(s.get("AuditShared"), str(cycle))
                s.peer.release()
                s.done("Shared", cycle + 1, second)
                self.assertEqual(len(s.peer.requests), 2 * (cycle + 1))
        for left, right in zip(s.events("A", "dispatch"), s.events("Shared", "dispatch")):
            self.assertNotEqual(left["extra"], right["extra"])

    def test_serial_chain(self):
        with self.scenario("serial", hold=True) as s:
            s.put("AuditA.FLNK", s.runtime.prefix + "B")
            s.put("AuditB.FLNK", s.runtime.prefix + "C")
            for cycle in range(self.cycles()):
                values = {n: 1000 * (cycle + 1) + n for n in (1, 2, 3)}
                s.peer.values.update(values)
                s.put("A.PROC")
                for offset, name in enumerate(("A", "B", "C")):
                    s.wait(lambda: len(s.peer.held) == 1)
                    self.assertEqual(len(s.peer.requests), 3 * cycle + offset + 1)
                    self.assertEqual(s.peer.requests[-1]["oids"], [offset + 1])
                    self.assertEqual(s.get("Audit" + name), str(cycle))
                    s.peer.release()
                    s.done(name, cycle + 1, values[offset + 1])
        for source, target in (("A", "B"), ("B", "C")):
            audits = [row for row in s.audits if row["record"].endswith("Audit" + source)]
            for audit, accepted in zip(audits, s.events(target, "accepted")):
                self.assertLess(audit["time"], accepted["time"])

    def active_puts(self, puts):
        with self.scenario("active-puts", hold=True) as s:
            for cycle in range(self.cycles()):
                first, second = 1000 + cycle, 2000 + cycle
                s.peer.values[1] = first
                s.put("A.PROC")
                s.wait(lambda: len(s.peer.held) == 1)
                for _ in range(puts):
                    s.put("A.PROC")
                self.assertEqual(s.state("A")["rpro"], 1)
                self.assertEqual(len(s.peer.requests), 2 * cycle + 1)
                self.assertEqual(s.get("AuditA"), str(2 * cycle))
                s.peer.values[1] = second
                s.peer.release()
                s.wait(lambda: len(s.peer.requests) == 2 * cycle + 2 and len(s.peer.held) == 1)
                self.assertEqual(s.get("AuditA"), str(2 * cycle + 1))
                s.expect("A", 2 * cycle + 1, first)
                s.peer.release()
                s.done("A", 2 * cycle + 2, second)
                self.assertEqual(s.state("A")["rpro"], 0)
            self.assertEqual(len(s.peer.requests), 2 * self.cycles())

    def test_active_put(self):
        self.active_puts(1)

    def test_active_ten_puts(self):
        self.active_puts(10)

    def test_put_completion(self):
        with self.scenario("put-notify", hold=True) as s:
            for cycle in range(self.cycles()):
                first, second = 1000 + cycle, 2000 + cycle
                s.peer.values[1] = first
                s.put("A.PROC")
                s.wait(lambda: len(s.peer.held) == 1)
                with s.completion_put("A") as client:
                    s.wait(lambda: s.state("A")["notify"] == 1, "Base put-notify registration")
                    self.assertIsNone(client.poll())
                    self.assertEqual(len(s.peer.requests), 2 * cycle + 1)
                    self.assertEqual(s.get("AuditA"), str(2 * cycle))
                    s.peer.values[1] = second
                    s.peer.release()
                    s.wait(lambda: len(s.peer.requests) == 2 * cycle + 2 and len(s.peer.held) == 1)
                    self.assertIsNone(client.poll(), "Put notify ended before its own acquisition")
                    s.expect("A", 2 * cycle + 1, first)
                    s.peer.release()
                s.done("A", 2 * cycle + 2, second)
                self.assertEqual(s.state("A")["notify"], 0)

    def periodic(self, scans):
        with self.scenario("scan") as s:
            s.put("A.PROC")
            s.done("A", 1, 101)
            s.peer.hold = True
            for cycle in range(self.cycles()):
                first, second = 1000 + cycle, 2000 + cycle
                before = len(s.peer.requests)
                s.peer.values[1] = first
                s.put("A.SCAN", ".1 second")
                s.wait(lambda: len(s.peer.held) == 1)
                s.wait(lambda: s.state("A")["lcnt"] >= scans, "observed active periodic scans")
                self.assertEqual(len(s.peer.requests), before + 1)
                self.assertEqual(s.get("AuditA"), str(2 * cycle + 1))
                if scans > 10:
                    self.assertEqual(s.get("A.STAT"), "13")
                    self.assertEqual(s.get("A.SEVR"), "3")
                s.peer.values[1] = second
                s.peer.release()
                s.wait(lambda: len(s.peer.requests) == before + 2 and len(s.peer.held) == 1,
                       "next idle periodic scan starts another acquisition")
                s.put("A.SCAN", "Passive")
                s.expect("A", 2 * cycle + 2, first)
                s.peer.release()
                s.done("A", 2 * cycle + 3, second)

    def test_five_active_scans(self):
        self.periodic(5)

    def test_extended_scan_alarm(self):
        self.periodic(11)

    def fanout(self, trigger):
        with self.scenario("fanout", peers=2) as s:
            s.peer.hold = True
            for cycle in range(self.cycles()):
                first, second = 1000 + cycle, 2000 + cycle
                s.peer.values[1] = first
                s.peers[1].values[2] = second
                s.put(trigger + ".PROC")
                s.wait(lambda: len(s.peer.held) == 1)
                s.done("B", cycle + 1, second)
                self.assertEqual(s.get("A.PACT"), "1")
                self.assertEqual(s.get("AuditA"), str(cycle))
                self.assertEqual(s.get(trigger + ".PACT"), "0")
                s.peer.release()
                s.done("A", cycle + 1, first)
        for left, right in zip(s.events("A", "accepted"), s.events("B", "accepted")):
            self.assertLess(left["sequence"], right["sequence"])
        for left, right in zip(s.events("B", "complete"), s.events("A", "result")):
            self.assertLess(left["time"], right["time"])

    def test_two_host_fanout(self):
        self.fanout("Both")

    def test_invalid_fanout_link(self):
        self.fanout("Invalid")

    def test_pini(self):
        for cycle in range(self.cycles()):
            with self.scenario(f"startup-{cycle}", hold=True, macros=",START=YES") as s:
                s.wait(lambda: len(s.peer.held) == 1)
                self.assertEqual(s.get("AuditA"), "0")
                self.assertEqual(s.get("AuditB"), "0")
                self.assertEqual(s.get("A.PACT"), "1")
                self.assertEqual(s.get("B.PACT"), "1")
                s.peer.hold = False
                s.peer.release()
                s.done("A", 1, 101)
                s.done("B", 1, 102)

    def test_disable(self):
        with self.scenario("disable", hold=True) as s:
            for cycle in range(self.cycles()):
                s.put("A.DISA", 1)
                s.put("A.PROC")
                self.assertEqual(len(s.peer.requests), cycle)
                self.assertEqual(s.get("AuditA"), str(cycle))
                self.assertEqual(s.get("A.STAT"), "18")
                s.put("A.DISA", 0)
                value = 1000 + cycle
                s.peer.values[1] = value
                s.put("A.PROC")
                s.wait(lambda: len(s.peer.held) == 1)
                s.put("A.DISA", 1)
                self.assertEqual(s.get("AuditA"), str(cycle))
                s.peer.release()
                s.done("A", cycle + 1, value)

    def test_terminal_errors(self):
        with self.scenario("errors", timeout_us=200000) as s:
            count = 0
            for mode in ("drop", "missing", "wrong-type"):
                for cycle in range(self.cycles()):
                    value = 1000 + cycle
                    s.peer.mode = "normal"
                    s.peer.values[1] = value
                    s.put("A.PROC")
                    count += 1
                    s.done("A", count, value)
                    if mode == "wrong-type":
                        s.peer.values[1] = "not-a-number"
                    else:
                        s.peer.mode = mode
                    s.put("A.PROC")
                    count += 1
                    s.done("A", count, value, severity=3, status=1)
                    s.peer.mode = "normal"
                    s.peer.values[1] = value + 5000
                    s.put("A.PROC")
                    count += 1
                    s.done("A", count, value + 5000)
        verify_diagnostics(s)

    def test_transport_failures(self):
        from socket_fault import SocketFault
        fault = SocketFault(self.work)
        with self.scenario("transport", transport_fault=fault) as s:
            count = 0
            for stage in ("open", "send"):
                for cycle in range(self.cycles()):
                    value = 1000 + cycle
                    s.peer.values[1] = value
                    s.put("A.PROC")
                    count += 1
                    s.done("A", count, value)
                    wire_count = len(s.peer.requests)
                    fault.arm(stage)
                    s.put("A.PROC")
                    count += 1
                    s.done("A", count, value, severity=3, status=1, failure=stage)
                    self.assertFalse(fault.control.exists(), "Socket fault was not consumed")
                    self.assertEqual(len(s.peer.requests), wire_count)
                    s.peer.values[1] = value + 5000
                    s.put("A.PROC")
                    count += 1
                    s.done("A", count, value + 5000)
        verify_diagnostics(s)
