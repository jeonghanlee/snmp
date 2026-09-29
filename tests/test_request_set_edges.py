"""Uncovered request-output contract edges through real CA and IOC processing."""

import subprocess
import time

from ioc import ROOT, write_json
from request_cases import PREFIX, Scenario
from test_request_set import RequestSetTest


CASES = ("cp_chain", "cpp_chain", "callback_value", "periodic_output",
         "scan_threshold", "response_limits", "invalid_values", "ivov", "binding_pairs",
         "legacy_window", "poll_order")
EDGE_DB = ("request_set_edges.db",)
LONG_TIMEOUT_US = 10000000


class RequestSetEdgesTest(RequestSetTest):
    def cp_chain(self, link):
        with self.scenario(link, fixture="request_set.db", writable=True,
                           overrides=EDGE_DB, macros=",LINK=" + link) as s:
            s.put("Source.DISA", 0)
            # Establish the actual CA monitor connection by observing its value.
            s.put("Command", 2)
            s.wait(lambda: s.get("Source") == "2" and s.get("AuditIntegerSet") == "1",
                   "initial CA link update")
            s.done("IntegerSet", 1, 2)
            s.peer.hold = True
            for cycle in range(self.cycles()):
                s.put("IntegerSet", 100 + cycle)
                s.wait(lambda: len(s.peer.held) == 1, "first SET held")
                s.put("Command", 500 + cycle)
                s.wait(lambda: s.get("Source") == str(500 + cycle), "CA monitor drives PP chain")
                state = s.state("IntegerSet")
                self.assertEqual(state["rpro"], 1)
                self.assertEqual(state["lcnt"], 1)
                s.peer.release()
                s.wait(lambda: len(s.peer.held) == 1, "reprocessed SET held")
                s.expect("IntegerSet", 2 * cycle + 2, 500 + cycle)
                s.peer.release()
                s.done("IntegerSet", 2 * cycle + 3, 500 + cycle)
                self.assertEqual([r["sets"][0]["value"] for r in self.sets(s)[-2:]],
                                 [100 + cycle, 500 + cycle])

    def test_cp_chain(self):
        self.cp_chain("CP")

    def test_cpp_chain(self):
        self.cp_chain("CPP")

    def test_callback_value(self):
        with self.scenario("callback-value", fixture="request_set.db", writable=True, hold=True) as s:
            for cycle in range(self.cycles()):
                s.put("IntegerSet", 100 + cycle)
                s.wait(lambda: len(s.peer.held) == 1, "first SET held")
                args = ["caput", "-c", "-w", str(s.runtime.deadline), "-t",
                        PREFIX + "IntegerSet", str(200 + cycle)]
                client = subprocess.Popen(args, env=s.runtime.env, text=True,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    s.wait(lambda: s.state("IntegerSet")["notify"] == 1, "put callback waiting")
                    self.assertIsNone(client.poll())
                    self.assertEqual(s.get("IntegerSet"), str(100 + cycle))
                    s.peer.release()
                    s.wait(lambda: len(s.peer.held) == 1, "callback's own SET held")
                    self.assertIsNone(client.poll())
                    s.expect("IntegerSet", 2 * cycle + 1, 100 + cycle)
                    self.assertEqual(self.sets(s)[-1]["sets"][0]["value"], 200 + cycle)
                    s.peer.release()
                    s.done("IntegerSet", 2 * cycle + 2, 200 + cycle)
                    out, err = client.communicate(timeout=s.runtime.deadline)
                    write_json(s.work / f"notify-{cycle}.json", dict(args=args, status=client.returncode,
                               stdout=out, stderr=err))
                    self.assertEqual(client.returncode, 0, err)
                    self.assertNotIn("timed out", err)
                finally:
                    if client.poll() is None:
                        client.kill()
                        client.communicate()

    def test_periodic_output(self):
        with self.scenario("periodic", fixture="request_set.db", writable=True, hold=True,
                           overrides=EDGE_DB,
                           timeout_us=LONG_TIMEOUT_US,
                           extra=('devSnmpSetParam("RequestTimeoutMSec", 10000)',)) as s:
            s.put("IntegerSet.SCAN", ".1 second")
            s.wait(lambda: len(s.peer.held) == 1, "periodic SET held")
            s.wait(lambda: s.state("IntegerSet")["lcnt"] >= 5, "five direct scans")
            s.put("IntegerSet.SCAN", "Passive")
            self.assertLessEqual(s.state("IntegerSet")["lcnt"], 10)
            self.assertNotEqual(s.get("IntegerSet.STAT"), "13")
            self.assertEqual(len(self.sets(s)), 1)
            s.peer.release()
            s.done("IntegerSet", 1, 0)

    def test_scan_threshold(self):
        with self.scenario("threshold", fixture="request_set.db", writable=True, hold=True,
                           overrides=EDGE_DB, timeout_us=LONG_TIMEOUT_US,
                           extra=('devSnmpSetParam("RequestTimeoutMSec", 10000)',)) as s:
            s.put("IntegerSet", 10)
            s.wait(lambda: len(s.peer.held) == 1, "SET held")
            # The idle fanout reaches the active output through dbProcess.
            for dropped in range(1, 12):
                s.runtime.process.stdin.write(f'dbtr("{PREFIX}ScanTrigger")\n')
                s.runtime.process.stdin.flush()
                s.wait(lambda: s.state("IntegerSet")["lcnt"] == dropped, "counted dropped processing")
                self.assertEqual(s.get("IntegerSet.STAT") == "13", dropped > 10)
            self.assertEqual(s.state("IntegerSet")["rpro"], 0)
            s.peer.release()
            s.done("IntegerSet", 1, 10)

    def test_response_limits(self):
        with self.scenario("reply-limits", fixture="request_set.db", writable=True,
                           overrides=EDGE_DB) as s:
            for record, wire in (("AnalogSet", 200), ("EngineeringSet", 20)):
                s.peer.mode = "normal"
                s.put(record, 20)
                s.done(record, 1, 20, raw=wire)
                s.peer.mode = "set_large_integer"
                s.put(record, 21)
                s.done(record, 2, 21, raw=wire)
            s.peer.mode = "set_long_string"
            s.put("TextSet", "abc")
            s.done("TextSet", 1, 0, text="abc")

    def test_invalid_values(self):
        s = Scenario(self, "invalid-values", fixture="request_set.db", writable=True, overrides=EDGE_DB)
        observations = []
        try:
            for record, values in (("EngineeringSet", ("nan", "inf", "-inf")),
                                   ("FloatSet", ("nan", "inf", "-inf")),
                                   ("TextSet", ("123456789",))):
                for count, value in enumerate(values, 1):
                    s.put(record, value)
                    s.wait(lambda: s.get("Audit" + record) == str(count), "failed first pass")
                    self.assertEqual(s.get(record + ".PACT"), "0")
                    observations.append(dict(record=record, value=value,
                                             status=int(s.get(record + ".STAT")),
                                             severity=int(s.get(record + ".SEVR"))))
                    self.assertEqual(self.sets(s), [])
        finally:
            s.close(verify=False)
            write_json(s.work / "invalid-values.json", observations)
        self.assertEqual(s.driver, [])
        self.assertEqual(len(s.audits), 7)
        expected = [(17 if r["value"] == "nan" else 2, 3) for r in observations]
        self.assertEqual([(r["status"], r["severity"]) for r in observations], expected)
        self.assertEqual([(a["status"], a["severity"]) for a in s.audits], expected)

    def test_ivov(self):
        s = Scenario(self, "ivov", fixture="request_set.db", writable=True)
        try:
            s.put("GuardedSet.IVOA", "Set output to IVOV")
            s.put("GuardedSet.IVOV", 23)
            s.put("GuardedSet", 1000)
            s.done("GuardedSet", 1, 23, raw=23, severity=3, status=3)
            self.assertEqual(self.sets(s)[0]["sets"][0]["value"], 23)
        finally:
            s.close(verify=False)
        self.assertEqual([r["event"] for r in s.driver],
                         ["accepted", "claimed", "dispatch", "result", "applied", "complete"])
        audit, = s.audits
        self.assertEqual((float(audit["value"]), audit["raw"], audit["status"], audit["severity"]), (23, 23, 3, 3))
        self.assertTrue(s.driver[-2]["success"], "The agent accepted IVOV despite the record's limit alarm")
        self.assertLessEqual(s.driver[-2]["time"], audit["time"])
        self.assertLessEqual(audit["time"], s.driver[-1]["time"])

    def test_binding_pairs(self):
        # Each rejected record is loaded through the normal database parser.
        s = Scenario(self, "bindings", fixture="request_set_rejects.db", writable=True)
        try:
            log = (s.work / "ioc.log").read_text()
            records = ("RejectRawFlag", "RejectFloatRaw", "RejectStringType", "RejectOtherFlag",
                       "RejectAnalogString", "RejectIntegerFloat", "RejectIntegerString",
                       "RejectStringFloat", "RejectStringRaw")
            for record in records:
                self.assertRegex(log, r"SnmpRequest: invalid output configuration.*PV: " + PREFIX + record)
                try:
                    s.put(record, 1)
                except RuntimeError:
                    pass
            self.assertRegex(log, r"SnmpRequest: OOPT must be Every Time.*PV: " + PREFIX + "RejectOopt")
            self.assertRegex(log, r"SnmpRequest: invalid OUT or SCAN.*PV: " + PREFIX + "RejectScan")
            self.assertEqual(self.sets(s), [])
        finally:
            s.close(verify=False)

    def test_legacy_window(self):
        with self.scenario("legacy-window", fixture="request_set_shared.db", writable=True,
                           extra=('devSnmpSetParam("PassivePollMSec", 100)',
                                  'devSnmpSetParam("SetSkipReadbackMSec", 4000)')) as s:
            s.wait(lambda: s.get("LegacySet") == "111", "initial legacy readback")
            s.put("SharedSet", 200)
            s.done("SharedSet", 1, 200)
            s.wait(lambda: s.get("LegacySet") == "200", "request SET does not start legacy window", timeout=2)
            started = time.monotonic()
            s.put("LegacySet", 300)
            s.wait(lambda: s.peer.values[11] == 300, "legacy setting applied")
            time.sleep(2)
            s.put("SharedSet", 400)
            s.done("SharedSet", 2, 400)
            s.wait(lambda: s.get("SharedRead") == "400", "poll cache contains the newer value")
            self.assertEqual(s.get("LegacySet"), "300", "request SET cleared the legacy window")
            s.wait(lambda: s.get("LegacySet") == "400", "original legacy window ends", timeout=3)
            elapsed = time.monotonic() - started
            write_json(s.work / "legacy-window.json", dict(elapsed_seconds=elapsed))
            self.assertGreaterEqual(elapsed, 3.8)
            self.assertLess(elapsed, 5.5, "request SET extended the legacy window")

    def test_poll_order(self):
        with self.scenario("poll-order", fixture="request_set.db", writable=True,
                           overrides=("request_set_shared.db", *EDGE_DB), timeout_us=LONG_TIMEOUT_US,
                           extra=('devSnmpSetParam("PassivePollMSec", 100)',
                                  'devSnmpSetParam("ReadStarvationMSec", 200)')) as s:
            s.wait(lambda: s.get("SharedRead") == "111", "legacy polling active")
            s.peer.hold = True
            s.wait(lambda: len(s.peer.held) == 1 and s.peer.held[0][2]["pdu"] == 0xA0,
                   "older legacy poll held")
            before = len(s.peer.requests)
            s.put("IntegerSet", 90)
            s.wait(lambda: s.get("IntegerSet.PACT") == "1", "write queued behind poll")
            s.put("IntegerRead.FLNK", PREFIX + "AuditIntegerRead")
            s.put("IntegerRead.PROC")
            self.assertEqual(s.get("AuditIntegerSet"), "0")
            s.peer.release()
            s.wait(lambda: len(s.peer.held) == 1, "next transaction held")
            self.assertEqual(s.peer.requests[before]["pdu"], 0xA3, "later GET overtook SET")
            self.assertEqual(s.peer.requests[before]["oids"], [6])
            s.peer.hold = False
            s.peer.release()
            s.done("IntegerSet", 1, 90)
            s.done("IntegerRead", 1, 90)
