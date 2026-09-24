"""Shared real-path fixtures and strict per-generation acceptance checks."""

from contextlib import contextmanager
import errno
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest

from ioc import IOC, ROOT, settings, trace_evidence, write_json
from snmp_peer import Peer, oid_bytes


ORDINARY_CYCLES = 100
IMMEDIATE_CYCLES = 1000
PREFIX = "SNMPTEST:"


class Scenario:
    def __init__(self, test, label, fixture="lifecycle.db", peers=1, hold=False,
                 macros="", timeout_us=None, max_oids=None, extra=(), writable=False, values=None,
                 transport_fault=None):
        self.test = test
        self.work = Path(tempfile.mkdtemp(prefix=label + "-", dir=test.work))
        self.peers = []
        self.expected = {}
        self.runtime = None
        self.token = 0
        self.driver, self.audits = [], []
        self.writable = writable
        self.transport_fault = transport_fault
        config = settings()
        profile = config["profile"]
        try:
            for number in range(peers):
                directory = self.work if number == 0 else self.work / ("peer-" + str(number))
                directory.mkdir(exist_ok=True)
                peer = Peer(directory, writable=writable)
                peer.values.update({n: 100 + n for n in range(1, 100)})
                peer.values.update(values or {})
                peer.names.update({oid_bytes((1, 3, 6, 1, 4, 1, 55555, n, 0)): n for n in peer.values})
                peer.hold = hold
                self.peers.append(peer)
            self.peer = self.peers[0]
            self.hosts = [f"127.0.0.1:{peer.server_address[1]}" for peer in self.peers]
            trace = 0 if config.get("negative_control") == "trace-loss" else 1
            lines = [f'devSnmpSetParam("RequestTrace", {trace})',
                     f'devSnmpSetParam("RequestTimeoutMSec", {profile["request_timeout_ms"]})',
                     f'devSnmpSetParam("SessionTimeout", {timeout_us or profile["session_timeout_us"]})',
                     f'devSnmpSetParam("SessionRetries", {profile["session_retries"]})']
            for host in self.hosts:
                lines += [f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")',
                          f'devSnmpSetMaxOidsPerReq("{host}", {max_oids or profile["max_oids"]})']
            substitutions = f"P={PREFIX},HOST={self.hosts[0]},HOST_B={self.hosts[-1]}" + macros
            lines += list(extra)
            lines += [f'dbLoadRecords("{ROOT}/tests/{fixture}", "{substitutions}")']
            if config.get("negative_control") == "miswired":
                lines += [f'dbLoadRecords("{ROOT}/tests/sequence_miswired.db", "P={PREFIX}")']
            process_env = transport_fault.environment(self.peer.server_address[1]) if transport_fault else None
            self.runtime = IOC(self.work, lines, process_env=process_env)
        except BaseException:
            for peer in self.peers:
                peer.close()
            raise

    def get(self, name):
        return self.runtime.get(name)

    def put(self, name, value=1):
        return self.runtime.put(name, value)

    def wait(self, predicate, description="scenario precondition", timeout=None):
        self.runtime.wait_for(predicate, description, timeout)

    def state(self, record):
        self.token += 1
        self.runtime.process.stdin.write(f'requestRecordState("{PREFIX}{record}", {self.token})\n')
        self.runtime.process.stdin.flush()
        pattern = re.compile(rf"SNMPSTATE {self.token} (\d+) {re.escape(PREFIX + record)} ([^\n]+)")
        self.wait(lambda: pattern.search((self.work / "ioc.log").read_text()), "record state observation")
        match = pattern.search((self.work / "ioc.log").read_text())
        return {k: int(v) for k, v in (field.split("=") for field in match[2].split())}

    def expect(self, record, count, value, severity=0, status=0, raw=None, text=None, failure=None):
        key = (PREFIX + record, count)
        self.test.assertNotIn(key, self.expected)
        self.expected[key] = dict(value=value, severity=severity, status=status, raw=raw, text=text, failure=failure)

    def done(self, record, count, value, severity=0, status=0, raw=None, text=None, failure=None):
        fields = ["Audit" + record, record + ".PACT", record + ".SEVR", record + ".STAT"]
        if text is None:
            fields.append(record)
        observed = {}
        def sample():
            observed.update(self.runtime.get_many(fields))
            return observed["Audit" + record] == str(count) and observed[record + ".PACT"] == "0"
        self.wait(sample, f"{record} completion {count}")
        self.test.assertEqual(observed[record + ".SEVR"], str(severity))
        self.test.assertEqual(observed[record + ".STAT"], str(status))
        if text is None:
            self.test.assertAlmostEqual(float(observed[record]), value, delta=1e-9)
        self.expect(record, count, value, severity, status, raw, text, failure)

    def done_many(self, values, count):
        fields = [field for record in values for field in
                  ("Audit" + record, record + ".PACT", record + ".SEVR", record + ".STAT", record)]
        observed = {}
        def sample():
            observed.update(self.runtime.get_many(fields))
            return all(observed["Audit" + record] == str(count) and observed[record + ".PACT"] == "0"
                       for record in values)
        self.wait(sample, "all batch members completed")
        for record, value in values.items():
            self.test.assertEqual(observed[record + ".SEVR"], "0")
            self.test.assertEqual(observed[record + ".STAT"], "0")
            self.test.assertAlmostEqual(float(observed[record]), value, delta=1e-9)
            self.expect(record, count, value)

    @contextmanager
    def completion_put(self, record):
        """Own an actual CA put-notify client through both held acquisitions."""
        args = ["caput", "-c", "-w", str(self.runtime.deadline), "-t", PREFIX + record + ".PROC", "1"]
        started = time.monotonic_ns()
        client = subprocess.Popen(args, env=self.runtime.env, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            yield client
            out, err = client.communicate(timeout=self.runtime.deadline)
            write_json(self.work / f"notify-{started}.json", dict(args=args, started=started,
                       finished=time.monotonic_ns(), status=client.returncode, stdout=out, stderr=err))
            self.test.assertEqual(client.returncode, 0, err)
            self.test.assertNotIn("timed out", err, "CA callback timeout is not a completed put")
        finally:
            if client.poll() is None:
                client.kill()
                client.communicate()

    def close(self, verify=True):
        try:
            self.runtime.close()
            self.driver, self.audits = trace_evidence(self.work)
            if verify:
                self.verify()
        finally:
            for peer in self.peers:
                peer.close()

    def verify(self):
        test = self.test
        log = (self.work / "ioc.log").read_text()
        test.assertNotIn("SNMPAUDIT_ERROR", log)
        test.assertIn("overflow=0", log)
        test.assertEqual([row["sequence"] for row in self.driver], list(range(len(self.driver))))
        wire = [entry for peer in self.peers for entry in peer.requests]
        for peer in self.peers:
            test.assertEqual(peer.errors, [])
        if not self.writable:
            test.assertTrue(all(entry["pdu"] == 0xA0 for entry in wire), "Read completion emitted SET")
        groups = {}
        for row in self.driver:
            groups.setdefault((row["record"], row["generation"]), []).append(row)
        test.assertEqual(set(groups), set(self.expected), "Unexpected or missing accepted generation")
        seen = {}
        for audit in self.audits:
            key = (audit["record"].replace("Audit", ""), audit["count"])
            test.assertIn(key, groups)
            seen.setdefault(key, []).append(audit)
        test.assertEqual(set(groups), set(seen), "Missing FLNK observation")
        faults = self.transport_fault.events() if self.transport_fault else []
        used_faults = set()
        for key, events in groups.items():
            expected = self.expected[key]
            names = ["accepted", "claimed", "dispatch", "result", "applied", "complete"]
            if expected["failure"] == "open":
                names.remove("dispatch")
            test.assertEqual([r["event"] for r in events], names, key)
            stamps = [row["time"] for row in events]
            test.assertEqual(stamps, sorted(stamps), key)
            identity = dict(field.split("=", 1) for field in events[2]["extra"].split())
            test.assertGreater(int(identity["tx"]), 0)
            matches = [entry for entry in wire if entry["id"] == int(identity["wire"]) and
                       identity["oid"] in entry["numeric_oids"]]
            if expected["failure"]:
                test.assertEqual(matches, [], "Failed outer transport unexpectedly transmitted")
                candidates = [i for i, fault in enumerate(faults)
                              if events[1]["time"] <= fault["time"] <= events[-3]["time"]]
                test.assertEqual(len(candidates), 1, "No unique real socket failure")
                number = candidates[0]
                test.assertNotIn(number, used_faults)
                used_faults.add(number)
                fault = faults[number]
                if expected["failure"] == "open":
                    test.assertEqual((fault["operation"], fault["errno"], int(identity["wire"])), ("socket", errno.EMFILE, 0))
                else:
                    test.assertIn(fault["operation"], ("sendto", "sendmsg"))
                    test.assertEqual((fault["errno"], fault["port"]), (errno.EIO, self.peer.server_address[1]))
            else:
                test.assertTrue(matches, key)
            for row in events[3:]:
                test.assertEqual(dict(field.split("=", 1) for field in row["extra"].split()), identity)
            test.assertTrue(events[-1]["success"], "Completion returned with PACT active")
            test.assertEqual(len(seen[key]), 1, "Duplicate FLNK")
            audit = seen[key][0]
            test.assertEqual(audit["pact"], 1)
            test.assertLessEqual(events[-2]["time"], audit["time"])
            test.assertLessEqual(audit["time"], events[-1]["time"])
            test.assertAlmostEqual(float(audit["value"]), expected["value"], delta=1e-9, msg=str(key))
            test.assertEqual(audit["severity"], expected["severity"], key)
            test.assertEqual(audit["status"], expected["status"], key)
            test.assertEqual(audit["undefined"], 0, key)
            test.assertEqual(events[-2]["success"], expected["severity"] == 0, key)
            if expected["raw"] is not None:
                test.assertEqual(audit["raw"], expected["raw"], key)
            if expected["text"] is not None:
                test.assertEqual(audit["text"], expected["text"], key)
        test.assertEqual(used_faults, set(range(len(faults))), "Unaccounted socket fault")
        write_json(self.work / "acceptance.json", {"generations": len(groups), "audits": len(self.audits),
                                                  "wire_requests": len(wire), "passed": True})

    def events(self, record, event):
        return [row for row in self.driver if row["record"] == PREFIX + record and row["event"] == event]


class ScenarioTest(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=settings().get("output")))
        print("Evidence:", self.work, flush=True)

    def cycles(self, immediate=False):
        return settings().get("cycles") or (IMMEDIATE_CYCLES if immediate else ORDINARY_CYCLES)

    @contextmanager
    def scenario(self, label, **options):
        scenario = Scenario(self, label, **options)
        try:
            yield scenario
        except BaseException:
            scenario.close(verify=False)
            raise
        else:
            scenario.close()
