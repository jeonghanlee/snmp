#!/usr/bin/env python3
"""Exercise real device support, Base record processing, CA, and UDP SNMP."""

import os
from pathlib import Path
import tempfile
import time
import unittest

from snmp_peer import Peer
from ioc import IOC, settings, trace_evidence


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "SNMPTEST:"


class RequestTest(unittest.TestCase):
    def setUp(self):
        config = settings()
        profile = config["profile"]
        parent = config.get("output")
        self.work = Path(tempfile.mkdtemp(prefix=f"snmp-{self._testMethodName}-", dir=parent))
        print(f"Evidence: {self.work}", flush=True)
        self.peer = Peer(self.work)
        self.addCleanup(self.peer.close)
        host = f"127.0.0.1:{self.peer.server_address[1]}"
        dtype = os.environ.get("SNMP_TEST_DTYP", config.get("dtyp", "SnmpRequest"))
        deadline_test = self._testMethodName in ("test_deadline_independent_of_network", "test_queued_deadline")
        request_timeout = 400 if deadline_test else profile.get("request_timeout_ms", 10000)
        session_timeout = 4000000 if deadline_test else profile.get("session_timeout_us", 2000000)
        trace = 0 if config.get("negative_control") == "trace-loss" else 1
        if config.get("negative_control") == "wrong-value":
            self.peer.values[1] = 909
        lines = [
            f'devSnmpSetParam("RequestTrace", {trace})',
            f'devSnmpSetParam("RequestTimeoutMSec", {request_timeout})',
            f'devSnmpSetParam("SessionRetries", {profile.get("session_retries", 0)})',
            f'devSnmpSetParam("SessionTimeout", {session_timeout})',
            f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")',
            f'devSnmpSetMaxOidsPerReq("{host}", {profile.get("max_oids", 20)})',
            f'dbLoadRecords("{ROOT}/tests/sequence.db", "P={PREFIX},HOST={host},DTYP={dtype}")',
        ]
        if config.get("negative_control") == "miswired":
            lines.append(f'dbLoadRecords("{ROOT}/tests/sequence_miswired.db", "P={PREFIX}")')
        if self._testMethodName == "test_mixed_legacy_idle":
            lines.append(f'dbLoadRecords("{ROOT}/tests/legacy.db", "P={PREFIX},HOST={host}")')
        if self._testMethodName == "test_legacy_polling_does_not_starve_request":
            self.peer.values[3] = 303
            lines.append(f'devSnmpSetMaxOidsPerReq("{host}", 1)')
            lines.append(f'dbLoadRecords("{ROOT}/tests/legacy_saturation.db", "P={PREFIX},HOST={host}")')
        if self._testMethodName == "test_callback_queue_pressure":
            lines.append('callbackSetQueueSize(2)')
        self.runtime = IOC(self.work, lines)
        self.ioc = self.runtime.process
        self.env = self.runtime.env
        self.addCleanup(self.cleanup)
        self.wait_for(lambda: self.get("A.PACT") == "0")

    def cleanup(self):
        self.runtime.close()
        driver, audits = trace_evidence(self.work)
        self.assertEqual(self.peer.errors, [])
        self.assertTrue(all(r["pdu"] == 0xA0 for r in self.peer.requests), "Unexpected SNMP SET")
        log = (self.work / "ioc.log").read_text()
        if self._testMethodName.startswith("test_shutdown_"):
            return
        self.assertIn("overflow=0", log, "Missing or overflowing driver trace")
        self.assertTrue(driver, "Missing driver events")
        sequences = {}
        self.assertEqual([row["sequence"] for row in driver], list(range(len(driver))))
        for row in driver:
            key = (row["record"], row["generation"])
            sequences.setdefault(key, []).append(row)
        for key, events in sequences.items():
            expected = ["accepted", "claimed", "dispatch", "result", "applied", "complete"]
            if self._testMethodName == "test_queued_deadline" and key[0].endswith(":B"):
                expected = ["accepted", "result", "applied", "complete"]
            self.assertEqual([row["event"] for row in events], expected, key)
            stamps = [row["time"] for row in events]
            self.assertEqual(stamps, sorted(stamps), key)
            dispatched = [row for row in events if row["event"] == "dispatch"]
            for row in dispatched:
                fields = dict(item.split("=", 1) for item in row["extra"].split())
                self.assertGreater(int(fields["tx"]), 0)
                observed = [wire for wire in self.peer.requests
                            if wire["id"] == int(fields["wire"]) and fields["oid"] in wire["numeric_oids"]]
                self.assertTrue(observed, f"No wire request matching {key}: {fields}")
                for terminal in events[events.index(row) + 1:]:
                    identity = dict(item.split("=", 1) for item in terminal["extra"].split())
                    self.assertEqual(identity, fields, "Transaction identity changed during completion")
        observed_audits = {}
        for audit in audits:
            self.assertEqual(audit["pact"], 1, "FLNK must run before PACT clears")
            key = (audit["record"].replace("Audit", ""), audit["count"])
            self.assertIn(key, sequences, "FLNK has no matching accepted request")
            observed_audits.setdefault(key, []).append(audit)
            self.assertLessEqual(sequences[key][-2]["time"], audit["time"], "Value/alarm application precedes FLNK")
            self.assertLessEqual(audit["time"], sequences[key][-1]["time"], "FLNK precedes completed processing")
        self.assertEqual(set(sequences), set(observed_audits), "Missing FLNK completion evidence")
        self.assertTrue(all(len(rows) == 1 for rows in observed_audits.values()), "Duplicate FLNK")
        self.assertNotRegex(log, r"SNMPREQ .* complete 0")

    def get(self, name):
        return self.runtime.get(name)

    def put(self, name, value=1):
        return self.runtime.put(name, value)

    def wait_for(self, predicate):
        self.runtime.wait_for(predicate)

    def done(self, record="A", count=1):
        self.wait_for(lambda: self.get(f"Audit{record}") == str(count) and self.get(f"{record}.PACT") == "0")
        self.runtime.client(["caget", "-w", "0.4", "-a", PREFIX + record])

    def test_idle_delayed_and_unchanged(self):
        time.sleep(0.3)
        self.assertEqual(self.peer.requests, [])
        self.peer.hold = True
        self.put("A.PROC")
        self.wait_for(lambda: bool(self.peer.held))
        self.assertEqual(self.get("A.PACT"), "1")
        self.assertEqual(self.get("AuditA"), "0")
        self.peer.release()
        self.done()
        self.assertEqual(self.get("A"), "101")
        self.assertEqual(self.get("A.SEVR"), "0")
        self.peer.hold = False
        self.put("A.PROC")
        self.done(count=2)
        self.assertEqual(len(self.peer.requests), 2)

    def test_serial_forward_link(self):
        self.put("AuditA.FLNK", PREFIX + "B")
        self.peer.hold = True
        self.put("A.PROC")
        self.wait_for(lambda: bool(self.peer.held))
        self.assertEqual([r["oids"] for r in self.peer.requests], [[1]])
        self.assertEqual(self.get("B.PACT"), "0")
        self.peer.release()
        self.wait_for(lambda: len(self.peer.requests) == 2)
        self.assertEqual(self.peer.requests[1]["oids"], [2])
        self.assertEqual(self.get("AuditB"), "0")
        self.peer.release()
        self.done("B")

    def test_late_shared_oid_request(self):
        self.peer.hold = True
        self.put("A.PROC")
        self.wait_for(lambda: bool(self.peer.held))
        self.peer.values[1] = 303
        self.put("Shared.PROC")
        self.assertEqual(self.get("Shared.PACT"), "1")
        self.peer.release()
        self.done()
        self.assertEqual(self.get("A"), "101")
        self.assertEqual(self.get("AuditShared"), "0")
        self.wait_for(lambda: bool(self.peer.held))
        self.peer.release()
        self.done("Shared")
        self.assertEqual(self.get("Shared"), "303")
        self.assertEqual(len(self.peer.requests), 2)

    def test_batch_oid_mapping_and_conversion(self):
        self.peer.mode = "reverse"
        self.put("All.PROC")
        self.done()
        self.done("B")
        self.done("Shared")
        self.wait_for(lambda: self.get("Text.PACT") == "0" and self.get("Raw.PACT") == "0")
        self.assertEqual(self.get("A"), "101")
        self.assertEqual(self.get("B"), "202")
        self.assertEqual(self.get("Shared"), "101")
        self.assertEqual(self.get("Raw"), "12.3")
        self.assertEqual(self.get("AuditRaw.A"), "12.3")
        self.assertEqual(self.get("Text"), r'\"hello\"')
        self.assertEqual(self.get("TextSink"), r'\"hello\"')
        self.assertTrue(any(len(r["oids"]) > 1 for r in self.peer.requests), "Batch not exercised")

    def test_timeout_recovery_preserves_value(self):
        self.put("A.PROC")
        self.done()
        self.peer.mode = "drop"
        self.put("A.PROC")
        self.done(count=2)
        self.assertEqual(self.get("A.SEVR"), "3")
        self.assertEqual(self.get("AuditA.C"), "3")
        self.assertEqual(self.get("A"), "101")
        self.peer.mode = "normal"
        self.peer.values[1] = 404
        self.put("A.PROC")
        self.done(count=3)
        self.assertEqual(self.get("A"), "404")
        self.assertEqual(self.get("A.SEVR"), "0")

    def test_active_proc_coalesces(self):
        self.peer.hold = True
        self.put("A.PROC")
        self.wait_for(lambda: bool(self.peer.held))
        for _ in range(3):
            self.put("A.PROC")
        self.assertEqual(len(self.peer.requests), 1)
        self.assertEqual(self.get("AuditA"), "0")
        self.peer.release()
        self.wait_for(lambda: len(self.peer.requests) == 2 and bool(self.peer.held))
        self.peer.hold = False
        self.peer.release()
        self.done(count=2)
        time.sleep(0.2)
        self.assertEqual(len(self.peer.requests), 2)

    def test_terminal_protocol_errors(self):
        for count, mode in enumerate(("exception", "missing", "duplicate", "error"), 1):
            self.peer.mode = mode
            self.put("A.PROC")
            self.done(count=count)
            self.assertEqual(self.get("A.SEVR"), "3", mode)

    def test_periodic_scan_while_active(self):
        self.peer.hold = True
        self.put("A.SCAN", ".1 second")
        self.wait_for(lambda: bool(self.peer.held))
        time.sleep(0.35)
        self.put("A.SCAN", "Passive")
        self.assertEqual(len(self.peer.requests), 1)
        self.assertEqual(self.get("AuditA"), "0")
        self.peer.release()
        self.done()
        time.sleep(0.2)
        self.assertEqual(len(self.peer.requests), 1)

    def test_late_reply_after_timeout(self):
        self.peer.hold = True
        self.put("A.PROC")
        self.wait_for(lambda: bool(self.peer.held))
        self.done()
        self.assertEqual(self.get("A.SEVR"), "3")
        self.peer.values[1] = 505
        self.put("A.PROC")
        self.wait_for(lambda: len(self.peer.held) == 2)
        self.peer.release()
        time.sleep(0.15)
        self.assertEqual(self.get("AuditA"), "1")
        self.assertEqual(self.get("A.PACT"), "1")
        self.peer.release()
        self.done(count=2)
        self.assertEqual(self.get("A"), "505")

    def test_type_and_buffer_errors(self):
        for count, value in enumerate(("not-a-number", "x" * 300), 1):
            self.peer.values[1] = value
            self.put("A.PROC")
            self.done(count=count)
            self.assertEqual(self.get("A.SEVR"), "3")

    def test_deadline_independent_of_network(self):
        self.peer.mode = "drop"
        started = time.monotonic()
        self.put("A.PROC")
        self.done()
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(self.get("A.SEVR"), "3")

    def test_shutdown_eof_pending(self):
        self.peer.hold = True
        self.put("A.PROC")
        self.wait_for(lambda: bool(self.peer.held))
        self.assertEqual(self.get("A.PACT"), "1")

    def test_shutdown_explicit_pending(self):
        self.peer.hold = True
        self.put("A.PROC")
        self.wait_for(lambda: bool(self.peer.held))
        self.ioc.communicate("exit\n", timeout=8)

    def test_shutdown_callback_pending(self):
        self.ioc.stdin.write("requestBlockCallbacks()\n")
        self.ioc.stdin.flush()
        self.wait_for(lambda: "SNMPBLOCK ready" in (self.work / "ioc.log").read_text())
        self.put("A.PROC")
        self.wait_for(lambda: bool(self.peer.requests))
        self.assertEqual(self.get("A.PACT"), "1")

    def test_mixed_legacy_idle(self):
        self.wait_for(lambda: self.get("Legacy") == "101")
        self.assertEqual(self.get("AuditA"), "0")
        self.peer.values[1] = 606
        self.wait_for(lambda: self.get("Legacy") == "606")
        self.assertEqual(self.get("AuditA"), "0")
        self.put("A.PROC")
        self.done()
        self.assertEqual(self.get("A"), "606")

    def test_callback_queue_pressure(self):
        self.ioc.stdin.write("requestBlockCallbacks()\n")
        self.ioc.stdin.flush()
        self.wait_for(lambda: "SNMPBLOCK ready" in (self.work / "ioc.log").read_text())
        self.put("A.PROC")
        self.wait_for(lambda: bool(self.peer.requests))
        time.sleep(0.1)
        self.assertEqual(self.get("A.PACT"), "1")
        self.assertEqual(self.get("AuditA"), "0")
        self.done()
        self.assertEqual(self.get("A"), "101")
        self.assertEqual(len(self.peer.requests), 1)
        self.assertIn("ring buffer full", (self.work / "ioc.log").read_text())

    def test_queued_deadline(self):
        self.peer.hold = True
        self.put("A.PROC")
        self.wait_for(lambda: bool(self.peer.held))
        self.put("B.PROC")
        self.done()
        self.done("B")
        self.assertEqual(self.get("B.SEVR"), "3")
        self.peer.release()
        time.sleep(0.3)
        self.assertEqual([r["oids"] for r in self.peer.requests], [[1]])

    def test_signed_and_changing_values(self):
        self.peer.values[2] = -123
        self.peer.values[3] = ""
        self.peer.values[4] = 246
        self.put("All.PROC")
        self.done("B")
        self.done("Text")
        self.done("Raw")
        self.assertEqual(self.get("B"), "-123")
        self.assertEqual(self.get("AuditRaw.A"), "24.6")
        self.assertEqual(self.get("TextSink"), self.get("Text"))
        self.peer.values[3] = "updated"
        self.put("Text.PROC")
        self.done("Text", count=2)
        self.assertEqual(self.get("TextSink"), r'\"updated\"')

    def test_legacy_polling_does_not_starve_request(self):
        self.wait_for(lambda: self.get("LegacyFast3") == "303" and self.get("LegacyFast4") == "123")
        started = time.monotonic()
        self.put("B.PROC")
        self.done("B")
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(self.get("B"), "202")
        self.assertEqual(self.get("B.SEVR"), "0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
