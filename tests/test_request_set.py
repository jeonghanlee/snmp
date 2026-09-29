"""Acceptance of request-driven SETs against the real IOC and a writable UDP peer."""

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

from diagnostics import verify as verify_diagnostics
from ioc import ROOT, settings
from owned_thread import paused_thread
from request_cases import Scenario, ScenarioTest, PREFIX


CASES = ("success", "held_completion", "agent_error", "response_mismatch", "request_loss",
         "reply_loss", "unencodable_value", "put_during_write", "oopt_restored", "simulation_during_write",
         "ivoa_guard", "queued_expiry", "queued_order", "late_reply", "transport_failures", "oopt_during_write",
         "oopt_first_pass", "oopt_exit", "rejected_bindings", "shared_oid")

# record, peer key, CA value, value on the wire, RBV after success
OUTPUTS = (("AnalogSet", 5, 25.5, 255, 255), ("EngineeringSet", 8, 42, 42, 42),
           ("IntegerSet", 6, -77, -77, None), ("FloatSet", 9, 3.5, 3.5, None))
TEXT = ("TextSet", 7, "applied")
# 39 characters, the stringout VAL capacity and the fixture's buffer length of 40
LONG_TEXT = "abcdefghijklmnopqrstuvwxyz0123456789ABC"
# glibc fills freed memory, so a use of freed dbEvent state at exit fails the
# exit instead of passing by chance; the check needs a bare IOC with the
# one-record fixture, since a larger database or client traffic reuses the
# freed memory first
FREE_FILL = {"MALLOC_PERTURB_": "165"}
EXIT_PROBES = 3


class RequestSetTest(ScenarioTest):
    def sets(self, scenario):
        return [row for row in scenario.peer.requests if row["pdu"] == 0xA3]

    def test_success(self):
        with self.scenario("success", fixture="request_set.db", writable=True, extra=('devSnmpSetParam("DebugLevel", 2)',)) as s:
            self.assertEqual(self.sets(s), [], "Initialization emitted a SET")
            self.assertEqual(s.get("FloatSet"), "12.5", "ao VAL did not come from the database")
            for cycle in range(self.cycles()):
                for record, key, value, wire, rbv in OUTPUTS:
                    before = len(self.sets(s))
                    s.put(record, value)
                    s.done(record, cycle + 1, value, raw=rbv)
                    self.assertEqual(len(self.sets(s)), before + 1)
                    self.assertEqual(self.sets(s)[-1]["sets"][0]["value"], wire)
                    self.assertEqual(s.peer.values[key], wire)
                text = TEXT[2] if cycle % 2 == 0 else LONG_TEXT
                s.put(TEXT[0], text)
                s.done(TEXT[0], cycle + 1, 0, text=text)
                self.assertEqual(s.peer.values[TEXT[1]], text)
        verify_diagnostics(s)

    def test_held_completion(self):
        with self.scenario("held", fixture="request_set.db", writable=True, hold=True) as s:
            for cycle in range(self.cycles()):
                value = 100 + cycle
                s.put("IntegerSet", value)
                s.wait(lambda: len(s.peer.held) == 1, "held SET response")
                self.assertEqual(s.get("IntegerSet.PACT"), "1")
                self.assertEqual(s.get("AuditIntegerSet"), str(cycle))
                self.assertEqual(s.peer.values[6], value, "SET applied before the reply")
                s.peer.release()
                s.done("IntegerSet", cycle + 1, value)
        verify_diagnostics(s)

    def test_agent_error(self):
        with self.scenario("agent-error", fixture="request_set.db", writable=True) as s:
            for cycle in range(self.cycles()):
                s.peer.mode = "normal"
                s.put("IntegerSet", 10 + cycle)
                s.done("IntegerSet", 3 * cycle + 1, 10 + cycle)
                s.peer.mode = "error"
                s.put("IntegerSet", 500 + cycle)
                s.done("IntegerSet", 3 * cycle + 2, 500 + cycle, severity=3, status=2)
                self.assertEqual(s.peer.values[6], 10 + cycle, "peer applied a value it refused")
                s.peer.mode = "normal"
                s.put("IntegerSet", 20 + cycle)
                s.done("IntegerSet", 3 * cycle + 3, 20 + cycle)
        verify_diagnostics(s)

    def test_response_mismatch(self):
        with self.scenario("mismatch", fixture="request_set.db", writable=True) as s:
            count = 0
            for cycle in range(self.cycles()):
                for mode in ("set_wrong_type", "set_extra", "set_missing"):
                    s.peer.mode = "normal"
                    s.put("EngineeringSet", 1000 + cycle)
                    count += 1
                    s.done("EngineeringSet", count, 1000 + cycle, raw=1000 + cycle)
                    s.peer.mode = mode
                    s.put("EngineeringSet", 2000 + cycle)
                    count += 1
                    # RBV keeps the last accepted value; the write itself failed
                    s.done("EngineeringSet", count, 2000 + cycle, severity=3, status=2, raw=1000 + cycle)
            s.peer.mode = "normal"
        verify_diagnostics(s)

    def loss(self, label, mode, applied):
        """A lost request or a lost reply ends in TIMEOUT; only a lost reply leaves the value applied."""
        with self.scenario(label, fixture="request_set.db", writable=True, timeout_us=200000) as s:
            for cycle in range(self.cycles()):
                s.peer.mode = "normal"
                s.put("IntegerSet", 1 + cycle)
                s.done("IntegerSet", 2 * cycle + 1, 1 + cycle)
                s.peer.mode = mode
                s.put("IntegerSet", 300 + cycle)
                s.done("IntegerSet", 2 * cycle + 2, 300 + cycle, severity=3, status=10)
                self.assertEqual(s.peer.values[6], 300 + cycle if applied else 1 + cycle)
            s.peer.mode = "normal"
        verify_diagnostics(s)

    def test_request_loss(self):
        self.loss("request-loss", "drop_request", applied=False)

    def test_reply_loss(self):
        self.loss("reply-loss", "drop", applied=True)

    def test_unencodable_value(self):
        """A value that fails its encoding check never reaches the wire and completes in its first pass."""
        s = Scenario(self, "unencodable", fixture="request_set.db", writable=True)
        try:
            for record, value in (("EngineeringSet", 1.5), ("EngineeringSet", 3e9), ("FloatSet", 1e300)):
                before = len(s.peer.requests)
                audit = int(s.get("Audit" + record))
                s.put(record, value)
                s.wait(lambda: s.get("Audit" + record) == str(audit + 1), "first-pass completion")
                fields = s.runtime.get_many([record + ".PACT", record + ".SEVR", record + ".STAT"])
                self.assertEqual(fields, {record + ".PACT": "0", record + ".SEVR": "3", record + ".STAT": "2"})
                time.sleep(0.3)
                self.assertEqual(len(s.peer.requests), before, "unencodable value reached the wire")
            s.put("EngineeringSet", 7)
            s.wait(lambda: s.get("EngineeringSet.SEVR") == "0" and s.get("EngineeringSet.PACT") == "0",
                   "recovery after an unencodable value")
            self.assertEqual(s.peer.values[8], 7)
        finally:
            s.close(verify=False)

    def test_put_during_write(self):
        """A put through dbPutField during an active write sets RPRO and is sent after completion."""
        with self.scenario("rpro", fixture="request_set.db", writable=True, hold=True) as s:
            for cycle in range(self.cycles()):
                first, second = 10 + cycle, 5000 + cycle
                s.put("IntegerSet", first)
                s.wait(lambda: len(s.peer.held) == 1, "first SET held")
                s.put("IntegerSet", second)
                self.assertEqual(s.state("IntegerSet")["rpro"], 1)
                s.peer.release()
                s.wait(lambda: len(s.peer.held) == 1, "second SET held")
                # the first write completed with its own reply while VAL already held the
                # second value and the RPRO pass kept the record active
                s.wait(lambda: s.get("AuditIntegerSet") == str(2 * cycle + 1), "first completion")
                self.assertEqual(s.get("IntegerSet.PACT"), "1")
                s.expect("IntegerSet", 2 * cycle + 1, second)
                s.peer.release()
                s.done("IntegerSet", 2 * cycle + 2, second)
                self.assertEqual([row["sets"][0]["value"] for row in self.sets(s)[-2:]], [first, second])
        verify_diagnostics(s)

    def test_oopt_restored(self):
        """OOPT changed at run time is restored by the module's monitor without processing the record."""
        s = Scenario(self, "oopt", fixture="request_set.db", writable=True)
        try:
            s.put("IntegerSet", 5)
            s.wait(lambda: s.get("AuditIntegerSet") == "1", "first write")
            audit = s.get("AuditIntegerSet")
            s.put("IntegerSet.OOPT", "On Change")
            s.wait(lambda: s.get("IntegerSet.OOPT") == "0", "OOPT restored by the monitor")
            fields = s.runtime.get_many(["IntegerSet.SEVR", "IntegerSet.STAT", "AuditIntegerSet", "IntegerSet.PACT"])
            self.assertEqual(fields, {"IntegerSet.SEVR": "3", "IntegerSet.STAT": "2",
                                      "AuditIntegerSet": audit, "IntegerSet.PACT": "0"})
            self.assertIn("OOPT 1 restored to Every Time (monitor)", (s.work / "ioc.log").read_text())
            s.put("IntegerSet", 5)
            s.wait(lambda: s.get("AuditIntegerSet") == "2" and s.get("IntegerSet.SEVR") == "0", "same value sent again")
            self.assertEqual(len(self.sets(s)), 2)
        finally:
            s.close(verify=False)

    def test_simulation_during_write(self):
        """SIMM switched on during a write: record support skips device support and the slot is freed."""
        with self.scenario("simulation", fixture="request_set.db", writable=True, hold=True) as s:
            count = 0
            for cycle in range(self.cycles()):
                value = 40 + cycle
                s.put("IntegerSet", value)
                s.wait(lambda: len(s.peer.held) == 1, "held SET response")
                s.put("IntegerSet.SIMM", "YES")
                s.peer.release()
                count += 1
                s.done("IntegerSet", count, value, failure="simulated")
                s.put("IntegerSet.SIMM", "NO")
                s.put("IntegerSet", value + 1000)
                s.wait(lambda: len(s.peer.held) == 1, "held SET after simulation")
                s.peer.release()
                count += 1
                s.done("IntegerSet", count, value + 1000)
        verify_diagnostics(s)

    def test_ivoa_guard(self):
        """IVOA Don't drive outputs on an INVALID limit alarm sends nothing; the next valid value is sent."""
        s = Scenario(self, "ivoa", fixture="request_set.db", writable=True)
        try:
            before = len(s.peer.requests)
            s.put("GuardedSet", 950)
            s.wait(lambda: s.get("AuditGuardedSet") == "1", "first pass with IVOA")
            fields = s.runtime.get_many(["GuardedSet.PACT", "GuardedSet.SEVR", "GuardedSet.STAT"])
            self.assertEqual(fields, {"GuardedSet.PACT": "0", "GuardedSet.SEVR": "3", "GuardedSet.STAT": "3"})
            time.sleep(0.3)
            self.assertEqual(len(s.peer.requests), before, "IVOA record reached the wire")
            s.put("GuardedSet", 10)
            s.wait(lambda: s.get("AuditGuardedSet") == "2" and s.get("GuardedSet.PACT") == "0", "write below the limit")
            self.assertEqual(s.get("GuardedSet.SEVR"), "0")
            self.assertEqual(s.peer.values[10], 10)
        finally:
            s.close(verify=False)

    def test_queued_expiry(self):
        """A write still queued behind a busy host at its deadline completes TIMEOUT unsent."""
        with self.scenario("queued", fixture="request_set.db", writable=True, hold=True,
                           extra=('devSnmpSetParam("RequestTimeoutMSec", 1000)',)) as s:
            for cycle in range(self.cycles()):
                s.put("IntegerSet", 1 + cycle)
                s.wait(lambda: len(s.peer.held) == 1, "first SET held")
                first = len(s.peer.requests)
                s.put("EngineeringSet", 2 + cycle)
                s.done("EngineeringSet", cycle + 1, 2 + cycle, severity=3, status=10, failure="queued")
                self.assertEqual(len(s.peer.requests), first, "expired queued write reached the wire")
                # the write on the wire reached the same deadline while its reply was held
                s.done("IntegerSet", 2 * cycle + 1, 1 + cycle, severity=3, status=10)
                s.peer.release()
                s.wait(lambda: len(s.peer.held) == 0, "held reply released")
                s.put("IntegerSet", 100 + cycle)
                s.wait(lambda: len(s.peer.held) == 1, "recovery SET held")
                s.peer.release()
                s.done("IntegerSet", 2 * cycle + 2, 100 + cycle)
        verify_diagnostics(s)

    def test_queued_order(self):
        """A write re-admitted after expiring in the host queue goes out in its new admission order."""
        # the native timeout outlasts the request deadline, so the queued write expires
        # while the held write still occupies the host
        with self.scenario("order", fixture="request_set.db", writable=True, hold=True, timeout_us=10000000,
                           extra=('devSnmpSetParam("RequestTimeoutMSec", 1000)',)) as s:
            s.put("IntegerSet", 1)
            s.wait(lambda: len(s.peer.held) == 1, "first SET held")
            s.put("EngineeringSet", 2)
            s.done("EngineeringSet", 1, 2, severity=3, status=10, failure="queued")
            s.done("IntegerSet", 1, 1, severity=3, status=10)
            s.put("AnalogSet", 25.5)
            s.put("EngineeringSet", 3)
            s.peer.release()
            for record, count, value, wire, key in (("AnalogSet", 1, 25.5, 255, 5), ("EngineeringSet", 2, 3, 3, 8)):
                s.wait(lambda: len(s.peer.held) == 1, record + " SET held")
                self.assertEqual(self.sets(s)[-1]["sets"][0]["key"], key, "request SETs left admission order")
                s.peer.release()
                s.done(record, count, value, raw=wire)
            self.assertEqual([row["sets"][0]["key"] for row in self.sets(s)], [6, 5, 8])
        verify_diagnostics(s)

    def test_late_reply(self):
        """A reply after the request deadline cannot change a TIMEOUT result."""
        with self.scenario("late", fixture="request_set.db", writable=True, hold=True,
                           extra=('devSnmpSetParam("RequestTimeoutMSec", 1000)',)) as s:
            for cycle in range(self.cycles()):
                count = 2 * cycle
                s.put("IntegerSet", 7 + cycle)
                s.wait(lambda: len(s.peer.held) == 1, "SET held")
                s.done("IntegerSet", count + 1, 7 + cycle, severity=3, status=10)
                s.peer.release()
                s.wait(lambda: len(s.peer.held) == 0 and len(s.peer.sent) > 0, "late reply released")
                time.sleep(0.2)
                self.assertEqual(s.get("AuditIntegerSet"), str(count + 1), "late reply completed the record again")
                s.put("IntegerSet", 70 + cycle)
                s.wait(lambda: len(s.peer.held) == 1, "next SET held")
                s.peer.release()
                s.done("IntegerSet", count + 2, 70 + cycle)
        verify_diagnostics(s)

    def test_transport_failures(self):
        from socket_fault import SocketFault
        fault = SocketFault(self.work)
        with self.scenario("transport", fixture="request_set.db", writable=True, transport_fault=fault) as s:
            count = 0
            for stage in ("open", "send"):
                for cycle in range(self.cycles()):
                    value = 100 + cycle
                    s.put("IntegerSet", value)
                    count += 1
                    s.done("IntegerSet", count, value)
                    wire_count = len(s.peer.requests)
                    fault.arm(stage)
                    s.put("IntegerSet", value + 500)
                    count += 1
                    s.done("IntegerSet", count, value + 500, severity=3, status=2, failure=stage)
                    self.assertFalse(fault.control.exists(), "Socket fault was not consumed")
                    self.assertEqual(len(s.peer.requests), wire_count)
                    self.assertEqual(s.peer.values[6], value, "a failed transport reached the peer")
        verify_diagnostics(s)

    def test_oopt_during_write(self):
        """OOPT changed while a write is active, seen first by the completion callback."""
        with self.scenario("oopt-completion", fixture="request_set.db", writable=True, hold=True) as s:
            for cycle in range(self.cycles()):
                value = 60 + cycle
                s.put("IntegerSet", value)
                s.wait(lambda: len(s.peer.held) == 1, "SET held")
                with paused_thread(s.runtime, "snmpOopt"):
                    s.put("IntegerSet.OOPT", "On Change")
                    self.assertEqual(s.get("IntegerSet.OOPT"), "1")
                    s.peer.release()
                    s.done("IntegerSet", cycle + 1, value)
                    self.assertEqual(s.get("IntegerSet.OOPT"), "0")
                time.sleep(0.2)
                self.assertEqual(s.get("IntegerSet.SEVR"), "0", "released monitor event overrode the agent's result")
            self.assertIn("restored to Every Time (completion)", (s.work / "ioc.log").read_text())
        verify_diagnostics(s)

    def test_oopt_first_pass(self):
        """OOPT changed before the monitor runs is caught by the write routine, which sends nothing."""
        s = Scenario(self, "oopt-first", fixture="request_set.db", writable=True)
        try:
            s.put("IntegerSet", 3)
            s.wait(lambda: s.get("AuditIntegerSet") == "1", "first write")
            with paused_thread(s.runtime, "snmpOopt"):
                s.put("IntegerSet.OOPT", "On Change")
                # a plain CA put learns of the failed first pass through ECA_PUTFAIL, which caput
                # reports as an exception message; a put with callback would complete normally
                client = subprocess.run(["caput", "-w", "0.4", "-t", PREFIX + "IntegerSet", "4"],
                                        env=s.runtime.env, capture_output=True, text=True, timeout=4)
                s.wait(lambda: s.get("AuditIntegerSet") == "2", "first-pass completion")
                self.assertIn("write request failed", (client.stdout + client.stderr).lower(),
                              "a plain CA put must report the failed write")
                fields = s.runtime.get_many(["IntegerSet.OOPT", "IntegerSet.SEVR", "IntegerSet.STAT", "IntegerSet.PACT"])
                self.assertEqual(fields, {"IntegerSet.OOPT": "0", "IntegerSet.SEVR": "3",
                                          "IntegerSet.STAT": "2", "IntegerSet.PACT": "0"})
            time.sleep(0.2)
            self.assertEqual(len(self.sets(s)), 1, "rejected first pass reached the wire")
            self.assertIn("restored to Every Time (write)", (s.work / "ioc.log").read_text())
            s.put("IntegerSet", 4)
            s.wait(lambda: s.get("AuditIntegerSet") == "3" and s.get("IntegerSet.SEVR") == "0", "same value sent")
            self.assertEqual(len(self.sets(s)), 2)
        finally:
            s.close(verify=False)

    def test_oopt_exit(self):
        """A bare IOC with one request longout exits cleanly under a free-filling allocator."""
        executable = Path(settings()["ioc"]).resolve()
        dbd = executable.parents[2] / "dbd" / (executable.name + ".dbd")
        deadline = float(settings()["profile"].get("action_timeout", 20))
        for probe in range(EXIT_PROBES):
            work = Path(tempfile.mkdtemp(prefix=f"oopt-exit-{probe}-", dir=self.work))
            for name in ("native-config", "native-state"):
                (work / name).mkdir(mode=0o700)
            with socket.socket() as reserve:
                reserve.bind(("127.0.0.1", 0))
                port = reserve.getsockname()[1]
            env = dict(os.environ, **FREE_FILL, EPICS_CAS_INTF_ADDR_LIST="127.0.0.1", EPICS_CA_AUTO_ADDR_LIST="NO",
                       EPICS_CA_ADDR_LIST=f"127.0.0.1:{port}", EPICS_CA_SERVER_PORT=str(port),
                       EPICS_CAS_SERVER_PORT=str(port), EPICS_CAS_AUTO_BEACON_ADDR_LIST="NO",
                       EPICS_CAS_BEACON_ADDR_LIST="", SNMPCONFPATH=str(work / "native-config"),
                       SNMP_PERSISTENT_DIR=str(work / "native-state"), MIBS="")
            startup = [f'dbLoadDatabase({json.dumps(str(dbd))})', f'{executable.name}_registerRecordDeviceDriver(pdbbase)',
                       f'dbLoadRecords("{ROOT}/tests/request_set_exit.db", "P={PREFIX},HOST=127.0.0.1:9")',
                       "iocInit", "epicsThreadSleep(1)", "exit"]
            (work / "st.cmd").write_text("\n".join(startup) + "\n")
            with (work / "ioc.log").open("w") as log:
                process = subprocess.Popen([str(executable), str(work / "st.cmd")], cwd=executable.parents[2],
                                           env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
                try:
                    process.wait(timeout=deadline)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            text = (work / "ioc.log").read_text()
            (work / "probe.json").write_text(json.dumps({
                "ioc": str(executable), "ioc_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "environment": FREE_FILL, "exit_code": process.returncode,
                "shutdown_complete": "devSnmp: shutdown complete" in text}, indent=1) + "\n")
            self.assertEqual(process.returncode, 0, f"IOC exit code {process.returncode}; evidence: {work}")
            self.assertIn("devSnmp: shutdown complete", text, f"missing shutdown confirmation; evidence: {work}")

    def test_rejected_bindings(self):
        """Unsupported set types, flags, OOPT and SCAN fail at initialization and send nothing."""
        s = Scenario(self, "rejects", fixture="request_set_rejects.db", writable=True)
        try:
            log = (s.work / "ioc.log").read_text()
            for record, message in (("RejectOopt", "OOPT must be Every Time"),
                                    ("RejectRawFlag", "invalid output configuration"),
                                    ("RejectFloatRaw", "invalid output configuration"),
                                    ("RejectStringType", "invalid output configuration"),
                                    ("RejectScan", "invalid OUT or SCAN"),
                                    ("RejectOtherFlag", "invalid output configuration")):
                self.assertRegex(log, r"SnmpRequest: " + message + r".*PV: " + PREFIX + record)
            for record in ("RejectOopt", "RejectRawFlag", "RejectScan"):
                try:
                    s.put(record, 1)
                except RuntimeError:
                    pass
            time.sleep(0.5)
            self.assertEqual(self.sets(s), [], "a rejected record sent a SET")
        finally:
            s.close(verify=False)

    def test_shared_oid(self):
        """A legacy output, a request output and a legacy readback on one OID keep their own paths."""
        with self.scenario("shared", fixture="request_set_shared.db", writable=True,
                           extra=('devSnmpSetParam("PassivePollMSec", 100)',
                                  'devSnmpSetParam("SetSkipReadbackMSec", 300)')) as s:
            s.wait(lambda: s.get("SharedRead") == "111", "legacy readback of the initial peer value")
            for cycle in range(self.cycles()):
                legacy, request = 1000 + cycle, 5000 + cycle
                sets = len(self.sets(s))
                s.put("LegacySet", legacy)
                s.put("SharedSet", request)
                s.done("SharedSet", cycle + 1, request)
                s.wait(lambda: len(self.sets(s)) >= sets + 2, "both SETs transmitted")
                values = [row["sets"][0]["value"] for row in self.sets(s)[sets:]]
                self.assertEqual(sorted(values), sorted([legacy, request]), "a write replaced the other")
                self.assertEqual(len({row["id"] for row in self.sets(s)[sets:]}), 2)
                s.wait(lambda: s.get("SharedRead") == str(s.peer.values[11]), "legacy readback follows the device")
                self.assertEqual(s.get("LegacySet.SEVR"), "0")
        verify_diagnostics(s)
