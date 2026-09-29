"""Additional output lifecycle coverage using the real IOC and UDP boundary."""

import subprocess

from ioc import ROOT, trace_evidence, write_json
from owned_thread import paused_thread
from request_cases import PREFIX, Scenario
from test_request_set import RequestSetTest


CASES = ("pini", "active_notify", "serial_writes", "database_put_chain",
         "scan_chain", "failure_ivoa", "delayed_simulation", "oopt_recovery",
         "first_pass_notify", "pending_exit")
TRIGGERS = str(ROOT / "tests/request_set_triggers.db")


class RequestSetExtraTest(RequestSetTest):
    def test_pini(self):
        with self.scenario("pini", fixture="request_set.db", writable=True, hold=True,
                           extra=(f'dbLoadRecords("{TRIGGERS}", "P={PREFIX},PINI=YES")',)) as s:
            s.wait(lambda: len(s.peer.held) == 1, "PINI SET response held")
            self.assertEqual(s.get("IntegerSet.PACT"), "1")
            self.assertEqual(s.get("AuditIntegerSet"), "0")
            self.assertEqual([row["sets"][0]["value"] for row in self.sets(s)], [17])
            s.peer.release()
            s.done("IntegerSet", 1, 17)

    def test_active_notify(self):
        with self.scenario("notify", fixture="request_set.db", writable=True, hold=True) as s:
            for cycle in range(self.cycles()):
                value = 100 + cycle
                s.put("IntegerSet", value)
                s.wait(lambda: len(s.peer.held) == 1, "first SET held")
                with s.completion_put("IntegerSet") as client:
                    s.wait(lambda: s.state("IntegerSet")["notify"] == 1, "Base put-notify registration")
                    self.assertIsNone(client.poll())
                    self.assertEqual(s.get("AuditIntegerSet"), str(2 * cycle))
                    s.peer.release()
                    s.wait(lambda: len(s.peer.held) == 1, "callback SET held")
                    self.assertIsNone(client.poll(), "callback returned before its own SET response")
                    s.expect("IntegerSet", 2 * cycle + 1, value)
                    s.peer.release()
                    s.done("IntegerSet", 2 * cycle + 2, value)
                self.assertEqual(s.state("IntegerSet")["notify"], 0)
                self.assertEqual(len(self.sets(s)), 2 * cycle + 2)

    def test_serial_writes(self):
        with self.scenario("serial", fixture="request_set.db", writable=True, hold=True) as s:
            s.put("AuditIntegerSet.FLNK", PREFIX + "EngineeringSet")
            for cycle in range(self.cycles()):
                s.put("IntegerSet", 200 + cycle)
                s.wait(lambda: len(s.peer.held) == 1, "A SET held")
                self.assertEqual(s.get("AuditEngineeringSet"), str(cycle))
                self.assertEqual([row["sets"][0]["key"] for row in self.sets(s)][-1], 6)
                s.peer.release()
                s.wait(lambda: len(s.peer.held) == 1, "B SET held after A FLNK")
                s.done("IntegerSet", cycle + 1, 200 + cycle)
                self.assertEqual(self.sets(s)[-1]["sets"][0]["key"], 8)
                s.peer.release()
                s.done("EngineeringSet", cycle + 1, 0, raw=0)
        for a, b in zip(s.events("IntegerSet", "applied"), s.events("EngineeringSet", "accepted")):
            self.assertLessEqual(a["time"], b["time"])

    def test_database_put_chain(self):
        with self.scenario("database", fixture="request_set.db", writable=True, hold=True,
                           extra=(f'dbLoadRecords("{TRIGGERS}", "P={PREFIX}")',)) as s:
            for cycle in range(self.cycles()):
                s.put("IntegerSet", 10 + cycle)
                s.wait(lambda: len(s.peer.held) == 1, "initial SET held")
                s.put("Source", 500 + cycle)
                state = s.state("IntegerSet")
                self.assertEqual((state["rpro"], state["lcnt"]), (1, 1))
                s.peer.release()
                s.wait(lambda: len(s.peer.held) == 1, "database-chain SET held")
                s.expect("IntegerSet", 2 * cycle + 1, 500 + cycle)
                s.peer.release()
                s.done("IntegerSet", 2 * cycle + 2, 500 + cycle)
                self.assertEqual([r["sets"][0]["value"] for r in self.sets(s)[-2:]],
                                 [10 + cycle, 500 + cycle])

    def test_scan_chain(self):
        with self.scenario("scan", fixture="request_set.db", writable=True, hold=True,
                           timeout_us=10000000,
                           extra=(f'dbLoadRecords("{TRIGGERS}", "P={PREFIX}")',
                                  'devSnmpSetParam("RequestTimeoutMSec", 10000)')) as s:
            s.put("Source.DISA", 1)
            s.put("Source", 700)
            s.put("Source.SCAN", ".1 second")
            s.put("IntegerSet", 10)
            s.wait(lambda: len(s.peer.held) == 1, "SET held during scans")
            s.put("Source.DISA", 0)
            s.wait(lambda: s.state("IntegerSet")["lcnt"] >= 11, "eleven dropped scan-chain requests")
            s.put("Source.DISA", 1)
            s.put("Source.SCAN", "Passive")
            state = s.state("IntegerSet")
            self.assertEqual(state["rpro"], 0)
            self.assertEqual(s.get("IntegerSet"), "700")
            self.assertEqual(s.get("IntegerSet.STAT"), "13")
            self.assertEqual(s.get("IntegerSet.SEVR"), "3")
            self.assertEqual(len(self.sets(s)), 1)
            s.peer.release()
            s.done("IntegerSet", 1, 700)
            self.assertEqual(len(self.sets(s)), 1, "scan chain unexpectedly scheduled another SET")
            s.put("IntegerSet.PROC")
            s.wait(lambda: len(s.peer.held) == 1, "next explicit processing sends latest value")
            s.peer.release()
            s.done("IntegerSet", 2, 700)

    def test_failure_ivoa(self):
        for action in (0, 1, 2):
            with self.scenario(f"ivoa-{action}", fixture="request_set.db", writable=True, hold=True) as s:
                s.put("EngineeringSet.IVOA", action)
                s.put("EngineeringSet.IVOV", 91)
                for cycle in range(self.cycles()):
                    s.peer.mode = "error"
                    s.put("EngineeringSet", 20 + cycle)
                    s.wait(lambda: len(s.peer.held) == 1, "failed SET response held")
                    self.assertEqual(s.get("AuditEngineeringSet"), str(2 * cycle))
                    s.peer.release()
                    s.done("EngineeringSet", 2 * cycle + 1, 20 + cycle, severity=3, status=2,
                           raw=0 if cycle == 0 else 29 + cycle,
                           failure="simulated" if action == 1 else None)
                    s.peer.mode = "normal"
                    s.put("EngineeringSet", 30 + cycle)
                    s.wait(lambda: len(s.peer.held) == 1, "recovery SET held")
                    s.peer.release()
                    s.done("EngineeringSet", 2 * cycle + 2, 30 + cycle, raw=30 + cycle)
                    self.assertEqual(len(self.sets(s)), 2 * cycle + 2)

    def test_delayed_simulation(self):
        for record, key in (("IntegerSet", 6), ("EngineeringSet", 8), ("TextSet", 7)):
            with self.subTest(record=record):
                s = Scenario(self, "sdly-" + record, fixture="request_set.db", writable=True)
                try:
                    for cycle in range(2):
                        s.put(record + ".SDLY", 1)
                        s.put(record + ".SIMM", "YES")
                        s.put(record, 23)
                        s.wait(lambda: s.get(record + ".PACT") == "1", "delayed simulation active")
                        s.put(record + ".SIMM", "NO")
                        s.wait(lambda: s.get("Audit" + record) == str(2 * cycle + 1) and
                               s.get(record + ".PACT") == "0", "simulation callback without a request")
                        self.assertEqual((s.get(record + ".STAT"), s.get(record + ".SEVR")), ("2", "3"))
                        self.assertEqual(len(self.sets(s)), cycle)
                        s.put(record, 24)
                        s.wait(lambda: s.get("Audit" + record) == str(2 * cycle + 2) and
                               s.get(record + ".PACT") == "0", "recovery")
                        self.assertEqual(s.get(record + ".SEVR"), "0")
                        self.assertEqual(s.peer.values[key], "24" if record == "TextSet" else 24)
                finally:
                    s.close(verify=False)
                self.assertEqual([a["count"] for a in s.audits], [1, 2, 3, 4])
                self.assertEqual([(a["status"], a["severity"]) for a in s.audits],
                                 [(2, 3), (0, 0), (2, 3), (0, 0)])
                self.assertEqual([r["event"] for r in s.driver],
                                 ["accepted", "claimed", "dispatch", "result", "applied", "complete"] * 2)

    def test_oopt_recovery(self):
        for action in (0, 1, 2):
            with self.scenario(f"oopt-ivoa-{action}", fixture="request_set.db", writable=True) as s:
                s.put("IntegerSet.IVOA", action)
                s.put("IntegerSet.IVOV", 99)
                for cycle in range(self.cycles()):
                    s.put("IntegerSet.OOPT", "On Change")
                    s.wait(lambda: s.get("IntegerSet.OOPT") == "0", "OOPT monitor restored")
                    self.assertEqual((s.get("IntegerSet.STAT"), s.get("IntegerSet.SEVR")), ("2", "3"))
                    self.assertEqual(s.get("AuditIntegerSet"), str(cycle))
                    s.put("IntegerSet", 7)
                    s.done("IntegerSet", cycle + 1, 7)
                    self.assertEqual(s.peer.values[6], 7)
                    self.assertEqual(len(self.sets(s)), cycle + 1)

    def test_first_pass_notify(self):
        s = Scenario(self, "first-pass-notify", fixture="request_set.db", writable=True)
        try:
            with paused_thread(s.runtime, "snmpOopt"):
                s.put("IntegerSet.OOPT", "On Change")
                args = ["caput", "-c", "-w", str(s.runtime.deadline), "-t", PREFIX + "IntegerSet", "4"]
                client = subprocess.run(args, env=s.runtime.env, capture_output=True, text=True,
                                        timeout=s.runtime.deadline + 1)
                write_json(s.work / "notify.json", dict(args=args, status=client.returncode,
                           stdout=client.stdout, stderr=client.stderr))
                self.assertEqual(client.returncode, 0)
                self.assertNotIn("timed out", client.stderr.lower())
                self.assertNotIn("write request failed", (client.stdout + client.stderr).lower())
                self.assertEqual(s.get("AuditIntegerSet"), "1")
                self.assertEqual((s.get("IntegerSet.PACT"), s.get("IntegerSet.STAT"),
                                  s.get("IntegerSet.SEVR")), ("0", "2", "3"))
            self.assertEqual(self.sets(s), [])
        finally:
            s.close(verify=False)
        self.assertEqual(s.driver, [])
        self.assertEqual(len(s.audits), 1)
        self.assertEqual((s.audits[0]["status"], s.audits[0]["severity"]), (2, 3))

    def test_pending_exit(self):
        for mode in ("explicit", "eof"):
            s = Scenario(self, "exit-" + mode, fixture="request_set.db", writable=True, hold=True)
            try:
                s.put("IntegerSet", 31)
                s.wait(lambda: len(s.peer.held) == 1, "in-flight SET held")
                s.put("EngineeringSet", 32)
                s.wait(lambda: s.get("EngineeringSet.PACT") == "1", "queued SET active")
                self.assertEqual(s.get("AuditIntegerSet"), "0")
                self.assertEqual(s.get("AuditEngineeringSet"), "0")
                s.runtime.close(mode=mode)
                driver, audits = trace_evidence(s.work)
                self.assertEqual(audits, [], "shutdown fabricated FLNK completion")
                self.assertEqual([r["record"] for r in driver if r["event"] == "accepted"],
                                 [PREFIX + "IntegerSet", PREFIX + "EngineeringSet"])
                self.assertFalse(any(r["event"] in ("result", "applied", "complete") for r in driver))
                self.assertEqual(len(self.sets(s)), 1, "queued SET was transmitted at shutdown")
            finally:
                s.close(verify=False)
