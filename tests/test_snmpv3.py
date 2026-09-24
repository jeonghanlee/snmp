"""Measure actual IOC cold/warm USM traffic, record completion and native calls."""

from collections import Counter
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unittest

from ioc import IOC, ROOT, digest, settings, trace_evidence, write_json
from snmp_agent import Agent, Proxy, NAME
from test_pressure import resources


CASES = ("cold_starts", "warm_reads", "warm_reads_without_audit", "healthy_peer_control", "healthy_peer_discovery_loss")
COLD_STARTS = 100
WARM_READS = 1000
LEVEL = "authPriv"
VALUE = '"fixture-agent"'
HEALTHY_INTERVAL_SECONDS = 0.1
ISOLATION_TIMEOUT_US = 4000000
ISOLATION_DEADLINE_MS = 400
FAULT_INTERVAL_READS = 100


class SnmpV3Test(unittest.TestCase):
    def setUp(self):
        self.config = settings()
        self.profile = self.config["profile"]
        self.assertIn("3", self.profile["protocols"])
        self.assertIn(LEVEL, self.profile["security_levels"])
        self.work = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=self.config.get("output")))
        print(f"Evidence: {self.work}", flush=True)
        self.agent = Agent(self.work, self.profile)
        self.addCleanup(self.agent.close)
        self.proxy = Proxy(self.work, self.agent.port)
        self.addCleanup(self.proxy.close)
        self.audit = None
        if self._testMethodName in ("test_cold_starts", "test_warm_reads"):
            compiler = shutil.which("cc")
            self.assertTrue(compiler, "Native observation requires a real C compiler")
            self.audit = self.work / "native-audit.so"
            command = [compiler, "-std=c11", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror",
                       "-o", str(self.audit), str(ROOT / "tests/native_audit.c")]
            build = subprocess.run(command, capture_output=True, text=True)
            write_json(self.work / "observer-build.json", {"argv": command, "exit_code": build.returncode,
                "out": build.stdout, "err": build.stderr, "compiler_sha256": digest(Path(compiler)),
                "source_sha256": digest(ROOT / "tests/native_audit.c")})
            self.assertEqual(build.returncode, 0, build.stderr)
        oracle = self.agent.client("3", LEVEL, NAME)
        write_json(self.work / "native-oracle.json", {"exit_code": oracle.returncode,
                                                     "out": oracle.stdout, "err": oracle.stderr})
        self.assertEqual(oracle.returncode, 0, oracle.stderr)
        self.assertIn(VALUE, oracle.stdout)

    def runtime(self, work):
        work.mkdir()
        host = f"127.0.0.1:{self.proxy.port}"
        lines = ['devSnmpSetParam("RequestTrace", 1)',
                 f'devSnmpSetParam("RequestTimeoutMSec", {self.profile["request_timeout_ms"]})',
                 f'devSnmpSetParam("SessionTimeout", {self.profile["session_timeout_us"]})',
                 f'devSnmpSetParam("SessionRetries", {self.profile["session_retries"]})',
                 f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_3")',
                 f'devSnmpSetSnmpV3ConfigFile("{host}", "{self.agent.ioc_config(LEVEL)}")',
                 f'dbLoadRecords("{ROOT}/tests/snmpv3.db", "P=SNMPTEST:,HOST={host}")']
        return IOC(work, lines, process_env={"LD_AUDIT": str(self.audit)} if self.audit else None)

    def read(self, runtime, generation):
        started = time.monotonic_ns()
        runtime.put("Name.PROC")
        values = {}
        def complete():
            values.update(runtime.get_many(["AuditName", "Name.PACT", "Name.SEVR", "Name"]))
            return values["AuditName"] == str(generation) and values["Name.PACT"] == "0"
        runtime.wait_for(complete, "actual value application and FLNK")
        self.assertEqual(values["Name"], r'\"fixture-agent\"')
        self.assertEqual(values["Name.SEVR"], "0")
        return {"generation": generation, "started_ns": started, "completed_ns": time.monotonic_ns()}

    def completed(self, work, count):
        driver, audits = trace_evidence(work)
        events = {}
        for row in driver:
            events.setdefault((row["record"], row["generation"]), []).append(row)
        self.assertEqual(len(events), count)
        self.assertEqual(len(audits), count)
        latencies = []
        for generation in range(1, count + 1):
            rows = events[("SNMPTEST:Name", generation)]
            self.assertEqual([row["event"] for row in rows],
                             ["accepted", "claimed", "dispatch", "result", "applied", "complete"])
            stamps = [row["time"] for row in rows]
            self.assertEqual(stamps, sorted(stamps))
            audit = [row for row in audits if row["count"] == generation]
            self.assertEqual(len(audit), 1)
            audit = audit[0]
            self.assertEqual((audit["pact"], audit["severity"], audit["text"]), (1, 0, VALUE))
            self.assertLessEqual(rows[4]["time"], audit["time"])
            self.assertLessEqual(audit["time"], rows[5]["time"])
            latencies.append({"generation": generation, "accepted_ns": stamps[0],
                              "dispatch_ns": stamps[2], "result_ns": stamps[3], "flnk_ns": audit["time"],
                              "complete_ns": stamps[5]})
        native = [dict(pid=int(pid), time=int(stamp), event=event, symbol=symbol, result=int(result))
                  for pid, stamp, event, symbol, result in re.findall(
                      r"SNMPNATIVE (\d+) (\d+) (enter|return) (\w+) (\d+)$", (work / "ioc.log").read_text(), re.M)]
        if self.audit:
            self.assertTrue(native, "No actual dynamic-library call observations")
            self.assertEqual(Counter(row["symbol"] for row in native if row["event"] == "enter"),
                             Counter(row["symbol"] for row in native if row["event"] == "return"))
            opens = [row for row in native if row["event"] == "return" and row["symbol"].endswith("open")]
            closes = [row for row in native if row["event"] == "return" and row["symbol"].endswith("close")]
            self.assertTrue(opens)
            self.assertTrue(all(row["result"] for row in opens))
            self.assertEqual(len(opens), len(closes))
        write_json(work / "native-calls.json", native)
        write_json(work / "latencies.json", latencies)
        return {"completed": count, "native_calls": dict(Counter(row["symbol"] for row in native
                                                                  if row["event"] == "return"))}

    def test_cold_starts(self):
        runs = []
        for index in range(COLD_STARTS):
            work = self.work / f"cold-{index:03}"
            first = len(self.proxy.records)
            runtime = self.runtime(work)
            try:
                before = resources(runtime)
                samples = [self.read(runtime, 1)]
                after = resources(runtime)
            finally:
                runtime.close()
            row = self.completed(work, 1)
            wire = self.proxy.records[first:]
            discoveries = [r for r in wire if r["event"] == "request" and not r["engine_id"]]
            self.assertTrue(discoveries, "Cold IOC did not make an observed discovery request")
            row.update(resources=[before, after], samples=samples, discovery_requests=len(discoveries))
            runs.append(row)
            write_json(self.work / "observations.json", {"runs": runs, "native_observer": True})
        self.assertEqual(len(runs), COLD_STARTS)

    def warm(self):
        work = self.work / "warm"
        runtime = self.runtime(work)
        observations, samples = [], []
        try:
            observations.append(resources(runtime))
            for generation in range(1, WARM_READS + 1):
                samples.append(self.read(runtime, generation))
                if generation % 10 == 0:
                    observations.append(resources(runtime))
            observations.append(resources(runtime))
        finally:
            runtime.close()
            write_json(work / "resources.json", observations)
            write_json(work / "samples.json", samples)
        row = self.completed(work, WARM_READS)
        row.update(discovery_requests=sum(r["event"] == "request" and not r["engine_id"]
                                          for r in self.proxy.records), native_observer=bool(self.audit))
        write_json(self.work / "observations.json", row)
        self.assertEqual(self.proxy.errors, [])

    def test_warm_reads(self):
        self.warm()

    def test_warm_reads_without_audit(self):
        self.warm()

    def healthy_peer(self, faulted):
        other_work = self.work / "other"
        other_work.mkdir()
        other_agent = Agent(other_work, self.profile)
        self.addCleanup(other_agent.close)
        other_proxy = Proxy(other_work, other_agent.port)
        self.addCleanup(other_proxy.close)
        oracle = other_agent.client("3", LEVEL, NAME)
        write_json(other_work / "native-oracle.json", {"exit_code": oracle.returncode,
                                                      "out": oracle.stdout, "err": oracle.stderr})
        self.assertEqual(oracle.returncode, 0, oracle.stderr)
        if faulted:
            other_proxy.fault("drop-requests")
        lines = ['devSnmpSetParam("RequestTrace", 1)',
                 f'devSnmpSetParam("RequestTimeoutMSec", {ISOLATION_DEADLINE_MS})',
                 f'devSnmpSetParam("SessionTimeout", {ISOLATION_TIMEOUT_US})',
                 'devSnmpSetParam("SessionRetries", 0)']
        for prefix, agent, proxy in (("", self.agent, self.proxy), ("Other", other_agent, other_proxy)):
            host = f"127.0.0.1:{proxy.port}"
            lines += [f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_3")',
                      f'devSnmpSetSnmpV3ConfigFile("{host}", "{agent.ioc_config(LEVEL)}")',
                      f'dbLoadRecords("{ROOT}/tests/snmpv3.db", "P=SNMPTEST:,R={prefix},HOST={host}")']
        work = self.work / "ioc"
        work.mkdir()
        runtime = IOC(work, lines)
        samples, usage, other_commands = [], [], []
        try:
            usage.append(resources(runtime))
            for generation in range(1, WARM_READS + 1):
                if (generation - 1) % FAULT_INTERVAL_READS == 0:
                    runtime.wait_for(lambda: runtime.get("OtherName.PACT") == "0", "other record ready")
                    before = len(other_proxy.records)
                    other_commands.append(time.monotonic_ns())
                    runtime.put("OtherName.PROC")
                    runtime.wait_for(lambda: len(other_proxy.records) > before, "actual other endpoint request")
                start = time.monotonic_ns()
                runtime.put("Name.PROC")
                values = {}
                def complete():
                    values.update(runtime.get_many(["AuditName", "Name.PACT", "Name.SEVR", "Name"]))
                    return values["AuditName"] == str(generation) and values["Name.PACT"] == "0"
                runtime.wait_for(complete, "healthy record terminal completion")
                samples.append({"generation": generation, "started_ns": start,
                                "observed_ns": time.monotonic_ns(), "fields": values.copy()})
                if generation % 10 == 0:
                    usage.append(resources(runtime))
                time.sleep(max(0, HEALTHY_INTERVAL_SECONDS - (time.monotonic_ns() - start) / 1e9))
            runtime.wait_for(lambda: runtime.get("OtherName.PACT") == "0", "last other record completion")
        finally:
            runtime.close()
            write_json(work / "samples.json", samples)
            write_json(work / "resources.json", usage)
            write_json(work / "other-commands.json", other_commands)
        driver, audits = trace_evidence(work)
        self.assertTrue(driver)
        self.assertEqual([row["sequence"] for row in driver], list(range(len(driver))))
        outcomes = []
        for prefix, count in (("", WARM_READS), ("Other", len(other_commands))):
            record = "SNMPTEST:" + prefix + "Name"
            selected = [row for row in driver if row["record"] == record]
            record_audits = [row for row in audits if row["record"] == "SNMPTEST:" + prefix + "AuditName"]
            self.assertEqual(len(record_audits), count)
            for generation in range(1, count + 1):
                rows = [row for row in selected if row["generation"] == generation]
                events = [row["event"] for row in rows]
                self.assertEqual(events[0], "accepted")
                for event in ("accepted", "result", "applied", "complete"):
                    self.assertEqual(events.count(event), 1)
                self.assertEqual(events[-2:], ["applied", "complete"])
                audit = [row for row in record_audits if row["count"] == generation]
                self.assertEqual(len(audit), 1)
                audit = audit[0]
                self.assertEqual(audit["pact"], 1)
                self.assertLessEqual(rows[-2]["time"], audit["time"])
                self.assertLessEqual(audit["time"], rows[-1]["time"])
                if prefix == "":
                    outcomes.append({"generation": generation, "accepted_ns": rows[0]["time"],
                                     "complete_ns": rows[-1]["time"], "severity": audit["severity"],
                                     "text": audit["text"], "events": events})
        write_json(work / "healthy-outcomes.json", outcomes)
        latencies = sorted((row["complete_ns"] - row["accepted_ns"]) / 1e9 for row in outcomes)
        invalid = sum(row["severity"] != 0 or row["text"] != VALUE for row in outcomes)
        summary = {"observation_only": True, "faulted": faulted, "count": len(outcomes),
                   "p99_seconds": latencies[(len(latencies) * 99 + 99) // 100 - 1],
                   "maximum_seconds": max(latencies), "invalid_count": invalid,
                   "request_deadline_ms": ISOLATION_DEADLINE_MS, "transport_timeout_us": ISOLATION_TIMEOUT_US,
                   "requested_interval_seconds": HEALTHY_INTERVAL_SECONDS,
                   "other_requests": len(other_commands), "other_discovery_requests": sum(
                       row["event"] == "request" and not row["engine_id"] for row in other_proxy.records)}
        write_json(self.work / "observations.json", summary)
        if not faulted:
            self.assertEqual(invalid, 0)
        else:
            self.assertTrue(summary["other_discovery_requests"])
            self.assertTrue(all(row["action"] == "drop" for row in other_proxy.records if row["event"] == "request"))
        self.assertEqual(self.proxy.errors + other_proxy.errors, [])

    def test_healthy_peer_control(self):
        self.healthy_peer(False)

    def test_healthy_peer_discovery_loss(self):
        self.healthy_peer(True)
