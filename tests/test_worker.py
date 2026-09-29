"""Run the shipped IOC/helper/native path against real external agents."""

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from ioc import IOC, ROOT, settings, trace_evidence, write_json
from test_config import ConfigTest, VALUE
from snmp_agent import USERS
from snmp_peer import Peer, oid_bytes


CASES = ("default_budget", "watchdog_examples", "missing_helper", "process_limit", "child_restart",
         "parent_loss", "isolation", "native_ownership", "ipc_startup", "ipc_results", "absolute_deadline",
         "snapshot_restart", "sentinel_budget", "discovery_isolation", "shared_budget", "set_child_loss",
         "default_retirement", "budget_boundaries")
ISOLATION_READS = 1000
ISOLATION_INTERVAL = 0.1
FAULT_INTERVAL = 100


class WorkerTest(ConfigTest):
    def runtime(self, lines, helper=None, maximum=32, parameters=(), process_env=None):
        work = self.fresh("ioc")
        helper = helper or Path(settings()["ioc"]).resolve().with_name("snmpWorker")
        startup = [f'iocshLoad("{ROOT}/examples/request-worker.iocsh", '
                   f'"SNMP_WORKER={helper},SNMP_MAX_WORKERS={maximum}")'] + list(parameters)
        startup += ['devSnmpSetParam("RequestTrace", 1)',
                    'devSnmpSetParam("RequestTimeoutMSec", 400)'] + lines
        runtime = IOC(work, startup, terminal=True, process_env=process_env)
        self.addCleanup(runtime.close)
        return runtime

    def endpoint_records(self, endpoint, prefix, community=None):
        return (f'dbLoadRecords("{ROOT}/tests/worker.db", '
                f'"P=SNMPTEST:,R={prefix},HOST=endpoint:{endpoint},COMM={community or "-"}")')

    def setup_lines(self, proxy, endpoint="e", prefix="A:", timeout=None, retries=None):
        profile = self.profile_file(endpoint, "authPriv", USERS["authPriv"])
        lines = [f'devSnmpLoadV3Profile("{endpoint}", "{profile}")',
                 f'devSnmpDefineEndpoint("{endpoint}", "udp:{self.proxied(proxy)}", "{endpoint}")']
        if timeout is not None:
            lines += [f'devSnmpSetEndpointParam("{endpoint}", "timeoutMSec", "{timeout}")']
        if retries is not None:
            lines += [f'devSnmpSetEndpointParam("{endpoint}", "retries", "{retries}")']
        return lines + [self.endpoint_records(endpoint, prefix)]

    def children(self, runtime):
        tasks = Path(f"/proc/{runtime.process.pid}/task")
        return sorted({int(pid) for path in tasks.glob("*/children") for pid in path.read_text().split()})

    def test_default_budget(self):
        agent, proxy = self.agent()
        runtime = self.runtime(self.setup_lines(proxy))
        self.assertIn("progressMSec=150000", self.log(runtime))
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assertEqual(len(self.children(runtime)), 1)
        self.assert_no_secret(runtime)
        for override, valid in ((149999, False), (150000, True)):
            runtime = self.runtime(self.setup_lines(proxy, f"p{override}"),
                                   parameters=(f'devSnmpSetParam("WorkerProgressLimitMSec", {override})',))
            if valid:
                self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
            else:
                self.assertIn("undersized", self.log(runtime))
                self.assertEqual(self.children(runtime), [])

    def test_watchdog_examples(self):
        agent, proxy = self.agent()
        for timeout, retries, expected in ((4000, 0, 20000), (200, 5, 7600), (60000, 5, 900000)):
            runtime = self.runtime(self.setup_lines(proxy, f"e{timeout}", timeout=timeout, retries=retries))
            self.assertIn(f"progressMSec={expected}", self.log(runtime))
            self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))

    def test_sentinel_budget(self):
        agent, proxy = self.agent()
        runtime = self.runtime(self.setup_lines(proxy), parameters=(
            'devSnmpSetParam("SessionTimeout", -1)', 'devSnmpSetParam("SessionRetries", -1)'))
        self.assertIn("progressMSec=18000", self.log(runtime))
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))

    def test_shared_budget(self):
        agent, proxy = self.agent()
        lines = self.setup_lines(proxy, timeout=4000, retries=0) + self.setup_lines(proxy, "f", "B:")
        runtime = self.runtime(lines)
        self.assertEqual(len(self.children(runtime)), 1)
        limits = re.findall(r"bound id=\d+ pid=\d+ epoch=\d+ progressMSec=(\d+)", self.log(runtime))
        self.assertEqual(limits, ["20000", "150000"])
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assertEqual(self.read(runtime, "B:"), (VALUE, "0"))
        before = len(proxy.records)
        limited = self.runtime(lines, parameters=('devSnmpSetParam("WorkerProgressLimitMSec", 20000)',))
        self.assertIn("undersized", self.log(limited))
        self.assertEqual(len(proxy.records), before, "Budget admission sent application traffic")
        self.assertEqual(self.read(limited, "A:"), (VALUE, "0"))
        self.assertEqual(self.read(limited, "B:")[1], "3")

    def test_budget_boundaries(self):
        agent, proxy = self.agent()
        for timeout, retries in ((0, 0), (-2, 0), (1000, -2), (1000, 2147483647),
                                 (2147483647, 2147483646)):
            before = len(proxy.records)
            runtime = self.runtime(self.setup_lines(proxy), parameters=(
                f'devSnmpSetParam("SessionTimeout", {timeout})',
                f'devSnmpSetParam("SessionRetries", {retries})'))
            self.assertIn("worker progress budget is invalid", self.log(runtime))
            self.assertEqual(self.children(runtime), [])
            self.assertEqual(len(proxy.records), before)
            runtime.close()
        runtime = self.runtime(self.setup_lines(proxy), parameters=(
            'devSnmpSetParam("SessionTimeout", 60000000)', 'devSnmpSetParam("SessionRetries", 20000)'))
        self.assertIn("progressMSec=2640198000", self.log(runtime))
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))

    def test_set_child_loss(self):
        peer = Peer(self.fresh("peer"), writable=True)
        self.addCleanup(peer.close)
        peer.values[6] = 0
        peer.names[oid_bytes((1, 3, 6, 1, 4, 1, 55555, 6, 0))] = 6
        peer.hold = True
        host = f"127.0.0.1:{peer.server_address[1]}"
        runtime = self.runtime([f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")',
                                f'dbLoadRecords("{ROOT}/tests/request_set.db", "P=SNMPTEST:,HOST={host}")'])
        runtime.put("IntegerSet", 123)
        runtime.wait_for(lambda: len(peer.held) == 1, "SET applied and reply held")
        self.assertEqual(peer.values[6], 123)
        self.assertEqual(runtime.get("IntegerSet.PACT"), "1")
        child, = self.children(runtime)
        os.kill(child, signal.SIGKILL)
        runtime.wait_for(lambda: runtime.get("IntegerSet.PACT") == "0", "failed SET completion")
        self.assertEqual(runtime.get("AuditIntegerSet"), "1")
        self.assertEqual(runtime.get("IntegerSet.SEVR"), "3")
        runtime.wait_for(lambda: self.children(runtime) and child not in self.children(runtime), "SET worker replacement")
        time.sleep(0.2)
        self.assertEqual(len(peer.requests), 1, "Worker replayed an outcome-unknown SET")
        peer.hold = False
        runtime.put("IntegerSet", 124)
        runtime.wait_for(lambda: runtime.get("AuditIntegerSet") == "2", "new explicit SET completion")
        self.assertEqual(runtime.get("IntegerSet.SEVR"), "0")
        self.assertEqual(peer.values[6], 124)
        self.assertEqual([row["sets"][0]["value"] for row in peer.requests], [123, 124])
        self.assertEqual(peer.errors, [])

    def test_snapshot_restart(self):
        agent, proxy = self.agent()
        runtime = self.runtime(self.setup_lines(proxy))
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        (self.files / "e.keys").write_text("authPassPhrase changed-secret\nprivPassPhrase changed-secret\n")
        child, = self.children(runtime)
        os.kill(child, signal.SIGKILL)
        runtime.wait_for(lambda: self.children(runtime) and child not in self.children(runtime), "snapshot replacement")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))

    def test_native_ownership(self):
        audit = self.work / "worker-audit.so"
        subprocess.run(["cc", "-shared", "-fPIC", "-O2", "-o", str(audit),
                        str(ROOT / "tests/worker_audit.c")], check=True)
        agent, proxy = self.agent()
        runtime = self.runtime(self.setup_lines(proxy), process_env={"LD_AUDIT": str(audit)})
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        child, = self.children(runtime)
        runtime.close()
        calls = re.findall(r"SNMPNATIVE (\d+) \d+ enter (\S+)", self.log(runtime))
        self.assertTrue(calls)
        self.assertFalse([row for row in calls if int(row[0]) == runtime.process.pid], "Parent called Net-SNMP")
        names = {name for pid, name in calls if int(pid) == child}
        self.assertTrue({"init_snmp", "read_objid", "generate_Ku", "snmp_sess_open", "snmp_sess_async_send"} <= names)
        write_json(runtime.work / "native-owner.json", {"parent": runtime.process.pid, "child": child, "calls": calls})

    def fault_runtime(self, proxy, mode, timeout=100):
        environment = {"SNMP_WORKER_TARGET": str(Path(settings()["ioc"]).resolve().with_name("snmpWorker")),
                       "SNMP_WORKER_FAULT": mode, "SNMP_WORKER_PROXY_LOG": str(self.work / (mode + "-ipc"))}
        return self.runtime(self.setup_lines(proxy, timeout=timeout, retries=0),
                            helper=ROOT / "tests/worker_proxy.py", process_env=environment)

    def test_ipc_startup(self):
        agent, proxy = self.agent()
        for mode in ("magic", "version", "kind", "oversize", "reserved", "build"):
            before = len(proxy.records)
            runtime = self.fault_runtime(proxy, mode)
            self.assertIn("worker local binding failed", self.log(runtime))
            self.assertEqual(len(proxy.records), before, "Invalid bootstrap sent application traffic")
            runtime.close()
            observations = [json.loads(line) for path in self.work.glob(mode + "-ipc-*.jsonl")
                            for line in path.read_text().splitlines()]
            self.assertTrue(any(row["direction"] == "to-worker" and row["kind"] == 1
                                for row in observations), "Fault proxy never received BOOTSTRAP")
            if mode != "build":
                self.assertTrue(any(row["direction"] == "to-ioc" and row["kind"] == 2
                                    for row in observations), "Fault proxy never received actual READY")

    def test_ipc_results(self):
        agent, proxy = self.agent()
        for mode in ("fragment", "epoch", "identity", "truncate", "duplicate"):
            runtime = self.fault_runtime(proxy, mode)
            value, severity = self.read(runtime, "A:")
            self.assertEqual(severity, "0" if mode in ("fragment", "duplicate") else "3", mode)
            time.sleep(0.1)
            self.assertEqual(runtime.get("A:AuditName"), "1", "Duplicate terminal completion")
            if mode in ("fragment", "duplicate"):
                self.assertEqual(value, VALUE)
            runtime.close()

    def test_absolute_deadline(self):
        agent, proxy = self.agent()
        for mode in ("partial-request", "slow-result"):
            runtime = self.fault_runtime(proxy, mode)
            self.assertIn("progressMSec=5300", self.log(runtime))
            child, = self.children(runtime)
            started = time.monotonic()
            self.assertEqual(self.read(runtime, "A:")[1], "3")
            self.assertLess(time.monotonic() - started, 1.0, "Worker extended the record deadline")
            runtime.wait_for(lambda: "absolute deadline" in self.log(runtime), "absolute worker retirement", timeout=7)
            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, 5.25)
            self.assertLess(elapsed, 6.3)
            self.assertEqual(runtime.get("A:AuditName"), "1")
            write_json(runtime.work / "deadline.json", {"child": child, "elapsed": elapsed, "mode": mode})
            runtime.close()

    def test_default_retirement(self):
        agent, proxy = self.agent()
        runtime = self.runtime(self.setup_lines(proxy))
        self.assertIn("progressMSec=150000", self.log(runtime))
        child, = self.children(runtime)
        os.kill(child, signal.SIGSTOP)
        self.addCleanup(lambda: os.kill(child, signal.SIGCONT) if Path(f"/proc/{child}").exists() else None)
        started = time.monotonic()
        self.assertEqual(self.read(runtime, "A:")[1], "3")
        self.assertLess(time.monotonic() - started, 1.0)
        runtime.wait_for(lambda: "absolute deadline" in self.log(runtime), "default worker retirement", timeout=153)
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 149.9)
        self.assertLess(elapsed, 151.5)
        self.assertEqual(runtime.get("A:AuditName"), "1")
        runtime.wait_for(lambda: self.children(runtime) and child not in self.children(runtime), "default watchdog recovery")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        write_json(runtime.work / "default-retirement.json", {"elapsed": elapsed, "configured_ms": 150000})

    def test_missing_helper(self):
        agent, proxy = self.agent()
        for helper in ("/no/such/snmpWorker", "/bin/true"):
            before = len(proxy.records)
            runtime = self.runtime(self.setup_lines(proxy), helper=helper)
            self.assertIn("worker local binding failed", self.log(runtime))
            self.assertEqual(len(proxy.records), before)

    def test_process_limit(self):
        agent, proxy = self.agent()
        other, second = self.agent()
        runtime = self.runtime(self.setup_lines(proxy) + self.setup_lines(second, "f", "B:"), maximum=1)
        self.assertIn("worker process limit reached", self.log(runtime))
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assertEqual(len(self.children(runtime)), 1)

    def test_child_restart(self):
        agent, proxy = self.agent()
        runtime = self.runtime(self.setup_lines(proxy))
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        child, = self.children(runtime)
        os.kill(child, signal.SIGKILL)
        runtime.wait_for(lambda: self.children(runtime) and child not in self.children(runtime), "replacement child")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assert_no_secret(runtime)

    def test_parent_loss(self):
        agent, proxy = self.agent()
        proxy.fault("drop-requests")
        runtime = self.runtime(self.setup_lines(proxy, timeout=4000, retries=0))
        child, = self.children(runtime)
        runtime.put("A:Name.PROC")
        runtime.wait_for(lambda: any(row["event"] == "request" and not row["engine_id"]
                                    for row in proxy.records), "native discovery blocked")
        runtime.require_shutdown = False
        runtime.process.kill()
        runtime.process.wait(timeout=3)
        def gone():
            status = Path(f"/proc/{child}/stat")
            return not status.exists() or status.read_text().split()[2] == "Z"
        due = time.monotonic() + 3
        while not gone() and time.monotonic() < due:
            time.sleep(0.01)
        runtime.close(mode="forced")
        self.assertTrue(gone(), "Child survived parent death")
        write_json(runtime.work / "parent-loss.json", {"child": child, "terminated": gone()})

    def test_discovery_isolation(self):
        summaries = {}
        for mode in ("control", "cold", "restart"):
            agent, proxy = self.agent()
            other, second = self.agent()
            if mode == "cold":
                proxy.fault("drop-requests")
            runtime = self.runtime(self.setup_lines(proxy, timeout=4000, retries=0) +
                                   self.setup_lines(second, "f", "B:", timeout=4000, retries=0))
            prior_faults = 0
            if mode == "restart":
                self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
                prior_faults = 1
                proxy.fault("drop-requests")
                child = self.children(runtime)[0]
                os.kill(child, signal.SIGKILL)
                runtime.wait_for(lambda: child not in self.children(runtime) and len(self.children(runtime)) == 2,
                                 "faulted worker replacement")
            fault_count = prior_faults
            for generation in range(1, ISOLATION_READS + 1):
                if (generation - 1) % FAULT_INTERVAL == 0:
                    before = len(proxy.records)
                    runtime.put("A:Name.PROC")
                    fault_count += 1
                    runtime.wait_for(lambda: len(proxy.records) > before, "real faulted-agent transaction")
                started = time.monotonic()
                runtime.put("B:Name.PROC")
                values = {}
                def complete():
                    values.update(runtime.get_many(["B:AuditName", "B:Name.PACT", "B:Name.SEVR", "B:Name"]))
                    return values["B:AuditName"] == str(generation) and values["B:Name.PACT"] == "0"
                runtime.wait_for(complete, "healthy value and FLNK")
                self.assertEqual((values["B:Name"], values["B:Name.SEVR"]), (VALUE, "0"))
                time.sleep(max(0, ISOLATION_INTERVAL - (time.monotonic() - started)))
            runtime.wait_for(lambda: runtime.get("A:Name.PACT") == "0", "last faulted completion")
            runtime.close()
            driver, audits = trace_evidence(runtime.work)
            self.assertNotIn("overflow=1", self.log(runtime))
            self.assertEqual([row["sequence"] for row in driver], list(range(len(driver))))
            latency = []
            for prefix, count in (("A:", fault_count), ("B:", ISOLATION_READS)):
                record = "SNMPTEST:" + prefix + "Name"
                selected = [row for row in driver if row["record"] == record]
                seen = [row for row in audits if row["record"] == "SNMPTEST:" + prefix + "AuditName"]
                self.assertEqual(len(seen), count)
                self.assertEqual({row["generation"] for row in selected}, set(range(1, count + 1)))
                for generation in range(1, count + 1):
                    rows = [row for row in selected if row["generation"] == generation]
                    self.assertEqual([row["event"] for row in rows],
                                     ["accepted", "claimed", "dispatch", "result", "applied", "complete"])
                    stamps = [row["time"] for row in rows]
                    self.assertEqual(stamps, sorted(stamps))
                    audit, = [row for row in seen if row["count"] == generation]
                    self.assertEqual(audit["pact"], 1)
                    self.assertLessEqual(stamps[-2], audit["time"])
                    self.assertLessEqual(audit["time"], stamps[-1])
                    elapsed = (stamps[-1] - stamps[0]) / 1e9
                    self.assertLess(elapsed, 1.0)
                    faulted = prefix == "A:" and mode != "control" and generation > prior_faults
                    self.assertEqual(audit["severity"], 3 if faulted else 0)
                    if prefix == "B:":
                        self.assertEqual(audit["text"], '"fixture-agent"')
                        latency.append(elapsed)
            latency.sort()
            accepted = [row["time"] for row in driver if row["record"] == "SNMPTEST:B:Name" and row["event"] == "accepted"]
            summaries[mode] = {"count": len(latency), "invalid": 0, "maximum_seconds": max(latency),
                               "p99_seconds": latency[(len(latency) * 99 + 99) // 100 - 1],
                               "record_deadline_ms": 400, "native_timeout_ms": 4000,
                               "requested_interval_seconds": ISOLATION_INTERVAL,
                               "mean_accepted_interval_seconds": (accepted[-1] - accepted[0]) / 1e9 / (len(accepted) - 1),
                               "evidence": str(runtime.work)}
            write_json(self.work / "isolation-summary.json", summaries)
            if mode != "control":
                self.assertLessEqual(summaries[mode]["p99_seconds"], summaries["control"]["p99_seconds"] + 0.1)
                self.assertTrue(any(row["event"] == "request" and not row["engine_id"] and row["action"] == "drop"
                                    for row in proxy.records))
            self.assertEqual(proxy.errors + second.errors, [])

    def test_isolation(self):
        agent, proxy = self.agent()
        other, second = self.agent()
        runtime = self.runtime(self.setup_lines(proxy, timeout=4000, retries=0) +
                               self.setup_lines(second, "f", "B:", timeout=4000, retries=0))
        self.assertEqual(len(self.children(runtime)), 2)
        self.assertEqual(self.read(runtime, "B:"), (VALUE, "0"))
        child = self.children(runtime)[0]
        os.kill(child, signal.SIGSTOP)
        self.addCleanup(lambda: os.kill(child, signal.SIGCONT) if Path(f"/proc/{child}").exists() else None)
        runtime.put("A:Name.PROC")
        started = time.monotonic()
        samples = []
        for _ in range(25):
            before = time.monotonic()
            self.assertEqual(self.read(runtime, "B:"), (VALUE, "0"))
            samples.append(time.monotonic() - before)
        runtime.wait_for(lambda: runtime.get("A:Name.PACT") == "0", "independent record deadline")
        self.assertEqual(runtime.get("A:Name.SEVR"), "3")
        self.assertLess(max(samples), 1.0)
        write_json(runtime.work / "isolation.json", {"samples": samples, "elapsed": time.monotonic() - started})

    # ConfigTest supplies fixture methods; its acceptance cases belong to its
    # own public suite and are selected explicitly by run_snmp.py.
