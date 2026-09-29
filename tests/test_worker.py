"""Run the shipped IOC/helper/native path against real external agents."""

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from ioc import IOC, ROOT, settings, trace_evidence, write_json
from test_config import AGENT_ENGINE, ConfigTest, VALUE, WRONG_ENGINE
from snmp_agent import Agent, Proxy, USERS
from snmp_peer import Peer, oid_bytes


CASES = ("default_budget", "watchdog_examples", "missing_helper", "process_limit", "child_restart",
         "parent_loss", "isolation", "native_ownership", "ipc_startup", "ipc_results", "absolute_deadline",
         "snapshot_restart", "sentinel_budget", "discovery_isolation", "shared_budget", "set_child_loss",
         "default_retirement", "budget_boundaries", "session_reuse", "session_loss_recovery",
         "engine_reboot", "engine_change", "engine_pinned_change", "profile_serialization",
         "session_too_big", "explicit_engine_isolation", "snapshot_files", "snapshot_inflight",
         "snapshot_callback", "snapshot_queued", "snapshot_queued_deadline", "delayed_snapshot_response", "snapshot_full_restart", "snapshot_set_loss", "snapshot_legacy_files", "snapshot_address_isolation")
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

    def endpoint_records(self, endpoint, prefix, community=None, oid=None, mask="STRING:"):
        fields = f",OID={oid},MASK={mask}" if oid else ""
        return (f'dbLoadRecords("{ROOT}/tests/worker.db", '
                f'"P=SNMPTEST:,R={prefix},HOST=endpoint:{endpoint},COMM={community or "-"}{fields}")')

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

    def recovery_runtime(self, proxy, extra=(), credentials=None, deadline=10000, legacy_file=None):
        observer = self.work / "recovery-observer.so"
        command = ["cc", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-o", str(observer),
                   str(ROOT / "tests/recovery_observer.c"), "-ldl"]
        build = subprocess.run(command, capture_output=True, text=True)
        write_json(self.work / "observer-build.json", {"argv": command, "exit": build.returncode,
                                                      "stdout": build.stdout, "stderr": build.stderr})
        self.assertEqual(build.returncode, 0, build.stderr)
        audit = self.work / "recovery-audit.so"
        subprocess.run(["cc", "-shared", "-fPIC", "-O2", "-o", str(audit),
                        str(ROOT / "tests/worker_audit.c")], check=True)
        lines = self.setup_lines(proxy, timeout=2000, retries=0)
        if credentials:
            (self.files / "e.keys").write_text(
                f"authPassPhrase {credentials[0]}\nprivPassPhrase {credentials[1]}\n")
        lines.insert(-1, f'devSnmpSetEndpointParam("e", "securityEngineID", "{AGENT_ENGINE}")')
        lines.insert(-1, 'devSnmpSetEndpointParam("e", "maxOidsPerReq", "1")')
        if legacy_file:
            host = self.proxied(proxy)
            lines = [f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_3")',
                     f'devSnmpSetSnmpV3ConfigFile("{host}", "{legacy_file}")',
                     f'dbLoadRecords("{ROOT}/tests/worker.db", "P=SNMPTEST:,R=A:,HOST={host},COMM=public")']
        return self.runtime([f'devSnmpSetParam("RequestTimeoutMSec", {deadline})'] + lines + list(extra),
                            process_env={"LD_PRELOAD": str(observer), "LD_AUDIT": str(audit)})

    def replace_child(self, runtime):
        old, = self.children(runtime)
        os.kill(old, signal.SIGKILL)
        runtime.wait_for(lambda: len(self.children(runtime)) == 1 and old not in self.children(runtime),
                         "snapshot helper replacement")
        child, = self.children(runtime)
        return old, child

    def mutate_files(self, mode="changed"):
        keys, profile = self.files / "e.keys", self.files / "e.conf"
        if mode == "deleted":
            keys.unlink()
            profile.unlink()
        elif mode == "unreadable":
            keys.chmod(0)
            profile.chmod(0)
        elif mode == "malformed":
            keys.write_text("not a valid credential file\n")
            profile.write_text("not a valid profile file\n")
        else:
            keys.write_text("authPassPhrase changed-secret-test\nprivPassPhrase changed-secret-test\n")
            profile.write_text("securityName wrong-user\nsecurityLevel noAuthNoPriv\n")

    def assert_snapshot_opens(self, runtime, child, paths=None):
        text = self.log(runtime)
        for path in paths or (self.files / "e.keys", self.files / "e.conf"):
            self.assertIn(f"SNMPFILE pid={runtime.process.pid} path={path}", text,
                          "The observer must see the actual parent startup file opens")
            self.assertNotIn(f"SNMPFILE pid={child} path={path}", text,
                             "Recovery reopened a startup file")
        self.assertIn(f"SNMPRECEIVE pid={child} ", text, "Observer must run in the recovered helper")

    def test_snapshot_legacy_files(self):
        for mode in ("changed", "deleted", "unreadable", "malformed"):
            agent, proxy = self.agent()
            path = agent.ioc_config("authPriv")
            runtime = self.recovery_runtime(proxy, legacy_file=path)
            self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
            if mode == "deleted":
                path.unlink()
            elif mode == "unreadable":
                path.chmod(0)
            elif mode == "malformed":
                path.write_text("invalid legacy configuration\n")
            else:
                path.write_text("securityName wrong-user\nsecurityLevel noAuthNoPriv\n")
            old, child = self.replace_child(runtime)
            self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
            self.assert_snapshot_opens(runtime, child, (path,))
            runtime.close()
            self.assert_no_secret(runtime)
            agent.close()

    def test_snapshot_address_isolation(self):
        agent, proxy = self.agent()
        other = Agent(self.fresh("different-key-agent"), settings()["profile"],
                      auth_pass="other-auth-test-only", priv_pass="other-priv-test-only")
        self.addCleanup(other.close)
        second = Proxy(self.fresh("different-key-proxy"), other.port)
        self.addCleanup(second.close)
        lines = self.setup_lines(proxy, "e", "A:") + self.setup_lines(second, "f", "B:")
        (self.files / "f.keys").write_text(
            "authPassPhrase other-auth-test-only\nprivPassPhrase other-priv-test-only\n")
        runtime = self.runtime(lines)
        self.assertEqual(len(self.children(runtime)), 2)
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assertEqual(self.read(runtime, "B:"), (VALUE, "0"))
        before = self.log(runtime)
        child = int(re.findall(r"bound id=1 pid=(\d+)", before)[-1])
        os.kill(child, signal.SIGKILL)
        runtime.wait_for(lambda: child not in self.children(runtime) and len(self.children(runtime)) == 2,
                         "one isolated helper recovered")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assertEqual(self.read(runtime, "B:"), (VALUE, "0"))
        for secret in ("other-auth-test-only", "other-priv-test-only"):
            self.assertNotIn(secret, self.log(runtime))
        self.assert_no_secret(runtime)

    def test_snapshot_files(self):
        for mode in ("changed", "deleted", "unreadable", "malformed"):
            agent, proxy = self.agent()
            runtime = self.recovery_runtime(proxy)
            self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
            self.mutate_files(mode)
            old, child = self.replace_child(runtime)
            self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
            self.assert_snapshot_opens(runtime, child)
            runtime.close()
            self.assert_no_secret(runtime)
            for path in (self.files / "e.keys", self.files / "e.conf"):
                if path.exists():
                    path.chmod(0o600)
            agent.close()

    def test_snapshot_inflight(self):
        agent, proxy = self.agent()
        runtime = self.recovery_runtime(proxy)
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        proxy.fault("hold-auth-replies")
        runtime.put("A:Name.PROC")
        runtime.wait_for(lambda: len(proxy.held_responses) == 1, "real authenticated GET response held")
        self.assertEqual(runtime.get("A:Name.PACT"), "1")
        self.mutate_files()
        old, child = self.replace_child(runtime)
        runtime.wait_for(lambda: runtime.get("A:AuditName") == "2" and runtime.get("A:Name.PACT") == "0",
                         "one failed GET completion")
        self.assertEqual(runtime.get("A:Name.SEVR"), "3")
        proxy.fault("normal")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assertEqual(runtime.get("A:AuditName"), "3")
        self.assert_snapshot_opens(runtime, child)

    def test_snapshot_callback(self):
        agent, proxy = self.agent()
        runtime = self.recovery_runtime(proxy)
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.command(runtime, "requestSustainCallbacks()", "SNMPSUSTAIN ready")
        try:
            runtime.put("A:Name.PROC")
            self.command(runtime, 'requestDiagnostics("SNMPTEST:A:Name")', "SNMPDIAG")
            def result_ready():
                self.command(runtime, 'requestDiagnostics("SNMPTEST:A:Name")', "SNMPDIAG")
                return bool(re.search(r"SNMPDIAG .*A:Name generation=2 state=(ready|scheduled).* valid=1 .*terminal_ns=[1-9][0-9]* applied_ns=0 ",
                                      self.log(runtime)))
            runtime.wait_for(result_ready, "real result immutable before callback")
            self.assertEqual(runtime.get("A:Name.PACT"), "1")
            self.assertEqual(runtime.get("A:AuditName"), "1")
            self.mutate_files()
            old, child = self.replace_child(runtime)
        finally:
            runtime.process.stdin.write("requestReleaseCallbacks()\n")
            runtime.process.stdin.flush()
        runtime.wait_for(lambda: runtime.get("A:AuditName") == "2" and runtime.get("A:Name.PACT") == "0",
                         "original callback applied once after helper loss")
        self.assertEqual(runtime.get("A:Name"), VALUE)
        self.assertEqual(runtime.get("A:Name.SEVR"), "0")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assertEqual(runtime.get("A:AuditName"), "3")
        self.assert_snapshot_opens(runtime, child)

    def test_snapshot_queued(self):
        agent, proxy = self.agent(writable=True)
        runtime = self.recovery_runtime(proxy, extra=(
            self.endpoint_records("e", "B:", oid=".1.3.6.1.4.1.55555.7.0"),
            self.endpoint_records("e", "C:", oid=".1.3.6.1.4.1.55555.6.0", mask="INTEGER:")))
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        proxy.fault("hold-auth-replies")
        runtime.put("A:Name.PROC")
        runtime.wait_for(lambda: len(proxy.held_responses) == 1, "active native response held")
        runtime.put("B:Name.PROC")
        runtime.put("C:Name.PROC")
        self.command(runtime, "snmpr(0)", "SNMPQUEUE")
        self.assertRegex(self.log(runtime), r"SNMPQUEUE epoch=\d+ count=2 ")
        self.mutate_files()
        proxy.fault("normal")
        old, child = self.replace_child(runtime)
        runtime.wait_for(lambda: runtime.get("A:AuditName") == "2" and runtime.get("B:AuditName") == "1" and
                         runtime.get("B:Name.PACT") == "0" and runtime.get("C:AuditName") == "1",
                         "queued snapshot requests complete")
        self.assertEqual(runtime.get("A:Name.SEVR"), "3")
        self.assertEqual((runtime.get("B:Name"), runtime.get("B:Name.SEVR")), (r'\"initial\"', "0"))
        self.assertEqual((runtime.get("C:Name"), runtime.get("C:Name.SEVR")), ("600", "0"))
        terminals = []
        for prefix in ("B:", "C:"):
            self.command(runtime, f'requestDiagnostics("SNMPTEST:{prefix}Name")', "SNMPDIAG_END")
            row = re.findall(rf"SNMPDIAG .*{prefix}Name .*terminal_ns=(\d+)", self.log(runtime))[-1]
            terminals.append(int(row))
        self.assertLess(terminals[0], terminals[1], "Recovered FIFO changed request order")
        self.assert_snapshot_opens(runtime, child)

    def test_snapshot_queued_deadline(self):
        agent, proxy = self.agent()
        deadline = 1000
        runtime = self.recovery_runtime(proxy, extra=(self.endpoint_records("e", "B:"),), deadline=deadline)
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        proxy.fault("hold-auth-replies")
        runtime.put("A:Name.PROC")
        runtime.wait_for(lambda: len(proxy.held_responses) == 1, "active exchange before deadline test")
        runtime.put("B:Name.PROC")
        self.command(runtime, 'requestDiagnostics("SNMPTEST:B:Name")', "SNMPDIAG_END")
        accepted = int(re.findall(r"SNMPDIAG .*B:Name .*accepted_ns=(\d+)", self.log(runtime))[-1])
        self.mutate_files()
        runtime.wait_for(lambda: time.monotonic_ns() >= accepted + deadline * 700000,
                         "queued request reaches seventy percent of its original deadline")
        old, child = self.replace_child(runtime)
        runtime.wait_for(lambda: runtime.get("B:AuditName") == "1" and runtime.get("B:Name.PACT") == "0",
                         "original queued deadline terminates once")
        self.command(runtime, 'requestDiagnostics("SNMPTEST:B:Name")', "SNMPDIAG_END")
        terminal = int(re.findall(r"SNMPDIAG .*B:Name .*terminal_ns=(\d+)", self.log(runtime))[-1])
        self.assertEqual(runtime.get("B:Name.SEVR"), "3")
        self.assertLessEqual(terminal - accepted, deadline * 1100000,
                             "Helper recovery extended the accepted request deadline")
        proxy.fault("normal")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assert_snapshot_opens(runtime, child)

    def test_delayed_snapshot_response(self):
        agent, proxy = self.agent()
        runtime = self.recovery_runtime(proxy)
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        proxy.fault("hold-auth-replies")
        runtime.put("A:Name.PROC")
        runtime.wait_for(lambda: len(proxy.held_responses) == 1, "old authenticated response held")
        old_packet, old_address, _ = proxy.held_responses.pop()
        self.mutate_files()
        old, child = self.replace_child(runtime)
        runtime.wait_for(lambda: runtime.get("A:AuditName") == "2" and runtime.get("A:Name.PACT") == "0",
                         "old generation failed once")
        agent.config.write_text(agent.config.read_text().replace("sysName fixture-agent", "sysName new-generation"))
        agent.restart(AGENT_ENGINE, 3)
        runtime.put("A:Name.PROC")
        runtime.wait_for(lambda: len(proxy.held_responses) == 1, "new valid response held")
        packet, address, _ = proxy.held_responses.pop()
        self.assertNotEqual(packet, old_packet)
        self.assertEqual(runtime.get("A:AuditName"), "2")
        fields = ["A:Name", "A:Name.STAT", "A:Name.SEVR", "A:AuditName"]
        before_state = runtime.get_many(fields)
        before_stamp = runtime.client(["caget", "-w", "0.4", "-a", "-n", "SNMPTEST:A:Name"])
        before = len(self.log(runtime))
        proxy.deliver_response(old_packet, address)
        runtime.wait_for(lambda: f"SNMPRECEIVE pid={child} " in self.log(runtime)[before:] and
                         f"hex={old_packet.hex()}" in self.log(runtime)[before:],
                         "unchanged old packet reached the current native receive path")
        runtime.wait_for(lambda: re.search(rf"hex={old_packet.hex()}\n.*SNMPNATIVE {child} \d+ return snmp_sess_read2 ",
                                          self.log(runtime)[before:], re.S), "native parse of the old packet returned")
        self.assertEqual(runtime.get_many(fields), before_state)
        self.assertEqual(runtime.client(["caget", "-w", "0.4", "-a", "-n", "SNMPTEST:A:Name"]), before_stamp)
        self.assertEqual(runtime.get("A:Name.PACT"), "1")
        self.assertEqual(runtime.get("A:AuditName"), "2")
        self.assertEqual(runtime.get("A:Name"), VALUE)
        proxy.deliver_response(packet, address)
        runtime.wait_for(lambda: runtime.get("A:AuditName") == "3" and runtime.get("A:Name.PACT") == "0",
                         "only new valid response completes")
        self.assertEqual(runtime.get("A:Name"), r'\"new-generation\"')
        self.assertEqual(runtime.get("A:Name.SEVR"), "0")
        write_json(self.work / "delayed-snapshot.json", {"old_child": old, "new_child": child,
                   "old_address": list(old_address), "current_address": list(address),
                   "old_packet": old_packet.hex(), "new_packet": packet.hex()})

    def test_snapshot_full_restart(self):
        agent, proxy = self.agent()
        runtime = self.recovery_runtime(proxy)
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        proxy.fault("hold-auth-replies")
        runtime.put("A:Name.PROC")
        runtime.wait_for(lambda: len(proxy.held_responses) == 1, "old IOC authenticated response held")
        old_packet, old_address, _ = proxy.held_responses.pop()
        old_parent, old_child = runtime.process.pid, self.children(runtime)[0]
        runtime.close()
        agent.close()
        credentials = ("fixture-next-auth-test-only", "fixture-next-priv-test-only")
        next_agent = Agent(self.fresh("replacement-agent"), self.profile, port=agent.port,
                           auth_pass=credentials[0], priv_pass=credentials[1], sys_name="new-generation")
        self.addCleanup(next_agent.close)
        fresh = self.recovery_runtime(proxy, credentials=credentials)
        self.assertNotEqual(fresh.process.pid, old_parent)
        child, = self.children(fresh)
        self.assertNotEqual(child, old_child)
        fresh.put("A:Name.PROC")
        fresh.wait_for(lambda: len(proxy.held_responses) == 1, "new IOC valid B response held")
        packet, address, _ = proxy.held_responses.pop()
        fields = ["A:Name", "A:Name.STAT", "A:Name.SEVR", "A:AuditName"]
        before_state = fresh.get_many(fields)
        before_stamp = fresh.client(["caget", "-w", "0.4", "-a", "-n", "SNMPTEST:A:Name"])
        offset = len(self.log(fresh))
        proxy.deliver_response(old_packet, address)
        fresh.wait_for(lambda: f"SNMPRECEIVE pid={child} " in self.log(fresh)[offset:] and
                       f"hex={old_packet.hex()}" in self.log(fresh)[offset:],
                       "old A packet actually received by new B IOC helper")
        fresh.wait_for(lambda: re.search(rf"hex={old_packet.hex()}\n.*SNMPNATIVE {child} \d+ return snmp_sess_read2 ",
                                        self.log(fresh)[offset:], re.S), "new helper rejected old A packet through native parsing")
        self.assertEqual(fresh.get_many(fields), before_state)
        self.assertEqual(fresh.client(["caget", "-w", "0.4", "-a", "-n", "SNMPTEST:A:Name"]), before_stamp)
        self.assertEqual(fresh.get("A:Name.PACT"), "1")
        proxy.deliver_response(packet, address)
        fresh.wait_for(lambda: fresh.get("A:AuditName") == "1" and fresh.get("A:Name.PACT") == "0",
                       "only valid B response completes the new IOC")
        self.assertEqual(fresh.get("A:Name"), r'\"new-generation\"')
        self.assertEqual(fresh.get("A:Name.SEVR"), "0")
        self.assert_snapshot_opens(fresh, child)
        fresh.close()
        proxy.fault("normal")
        invalid = self.recovery_runtime(proxy, credentials=("short", "short"))
        self.assertEqual(self.read(invalid, "A:")[1], "3")
        self.assertNotEqual(invalid.get("A:Name"), VALUE, "Invalid B cannot reuse A or B's prior value")
        self.assert_logged(invalid, ["credential authPassPhrase must be 8 through 1024 bytes"])
        write_json(self.work / "full-restart.json", {"old_parent": old_parent, "old_child": old_child,
                   "new_parent": fresh.process.pid, "new_child": child,
                   "old_address": list(old_address), "current_address": list(address),
                   "old_packet": old_packet.hex(), "new_packet": packet.hex(), "before": before_state})

    def test_snapshot_set_loss(self):
        agent, proxy = self.agent(writable=True)
        runtime = self.recovery_runtime(proxy, extra=(
            f'dbLoadRecords("{ROOT}/tests/request_set_agent.db", "P=SNMPTEST:,HOST=endpoint:e,COMM=-")',))
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        proxy.fault("hold-auth-replies")
        runtime.put("IntegerSet", 777)
        runtime.wait_for(lambda: len(proxy.held_responses) == 1 and
                         json.loads(agent.values_path.read_text())["values"]["6"] == 777,
                         "actual authenticated SET applied with response held")
        self.assertEqual(runtime.get("IntegerSet.PACT"), "1")
        self.mutate_files()
        old, child = self.replace_child(runtime)
        runtime.wait_for(lambda: runtime.get("AuditIntegerSet") == "1" and
                         runtime.get("IntegerSet.PACT") == "0", "outcome-unknown SET failed once")
        self.assertEqual(runtime.get("IntegerSet.SEVR"), "3")
        proxy.fault("normal")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        writes = [json.loads(line) for line in (agent.work / "writes.jsonl").read_text().splitlines()]
        self.assertEqual(len([row for row in writes if row["value"] == 777]), 1,
                         "Authenticated SET must not replay during helper recovery")
        runtime.put("IntegerSet", 778)
        runtime.wait_for(lambda: runtime.get("AuditIntegerSet") == "2" and
                         runtime.get("IntegerSet.PACT") == "0", "new explicit SET succeeds with retained A")
        self.assertEqual(runtime.get("IntegerSet.SEVR"), "0")
        self.assertEqual(json.loads(agent.values_path.read_text())["values"]["6"], 778)
        self.assert_snapshot_opens(runtime, child)

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

    def observed_runtime(self, lines):
        audit = self.work / "session-audit.so"
        subprocess.run(["cc", "-shared", "-fPIC", "-O2", "-o", str(audit),
                        str(ROOT / "tests/worker_audit.c")], check=True)
        return self.runtime(lines, process_env={"LD_AUDIT": str(audit)})

    def session_opens(self, runtime):
        calls = re.findall(r"SNMPNATIVE (\d+) \d+ return snmp_sess_open (\d+)", self.log(runtime))
        self.assertTrue(all(int(pid) != runtime.process.pid and int(result) for pid, result in calls))
        return len(calls)

    def test_session_reuse(self):
        agent, proxy = self.agent()
        runtime = self.observed_runtime(self.setup_lines(proxy, timeout=200, retries=1) +
                                       [self.endpoint_records("e", "B:")])
        for generation in range(1, 101):
            self.assertEqual(self.read(runtime, "A:" if generation % 2 else "B:"), (VALUE, "0"))
        self.assertEqual(self.session_opens(runtime), 1, "Compatible bindings did not retain one native session")
        discoveries = [r for r in proxy.records if r["event"] == "request" and not r["engine_id"]]
        self.assertEqual(len(discoveries), 1, "Warm reads repeated discovery")
        runtime.close()
        driver, audits = trace_evidence(runtime.work)
        self.assertEqual(sum(r["event"] == "complete" for r in driver), 100)
        self.assertEqual(len(audits), 100)
        self.assertTrue(all(r["pact"] == 1 and r["severity"] == 0 for r in audits))
        write_json(runtime.work / "reuse.json", {"reads": 100, "native_opens": 1, "discoveries": 1})

    def test_session_loss_recovery(self):
        agent, proxy = self.agent()
        runtime = self.observed_runtime(self.setup_lines(proxy, timeout=100, retries=0))
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        proxy.fault("drop-replies")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "3"))
        proxy.fault("normal")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assertEqual(self.session_opens(runtime), 2)

    def test_session_too_big(self):
        agent, proxy = self.agent()
        host = self.proxied(proxy)
        runtime = self.observed_runtime([
            f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")',
            'devSnmpSetParam("SessionTimeout", 100000)',
            'devSnmpSetParam("SessionRetries", 0)',
            f'dbLoadRecords("{ROOT}/tests/worker.db", "P=SNMPTEST:,R=A:,HOST={host},COMM=public")'])
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        self.assertEqual(self.session_opens(runtime), 1)
        proxy.fault("too-big", 0xA0)
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "3"))
        proxy.fault("normal")
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        runtime.close()
        requests = [row for row in proxy.records if row["event"] == "request"]
        responses = [row for row in proxy.records if row["event"] == "response"]
        self.assertEqual(len(requests), 3, "Unexpected retransmission or extra application request")
        self.assertEqual([row["error"] for row in responses], [0, 1, 0])
        self.assertEqual(responses[1]["original_error"], 0)
        self.assertEqual(responses[1]["varbinds"], [])
        self.assertEqual([row["id"] for row in responses], [row["id"] for row in requests])
        driver, audits = trace_evidence(runtime.work)
        self.assertEqual([row["generation"] for row in driver if row["event"] == "complete"], [1, 2, 3])
        self.assertEqual([row["severity"] for row in audits], [0, 3, 0])
        self.assertTrue(all(row["pact"] == 1 for row in audits))
        self.assertEqual(proxy.errors, [])
        write_json(runtime.work / "too-big.json", {"requests": len(requests),
                   "native_opens": self.session_opens(runtime), "response_errors": [0, 1, 0]})

    def engine_recovery(self, changed, pinned):
        agent, proxy = self.agent()
        lines = self.setup_lines(proxy, timeout=200, retries=1)
        if pinned:
            engine = "80001f8804" + b"fixture-agent".hex()
            lines.insert(-1, f'devSnmpSetEndpointParam("e", "securityEngineID", "{engine}")')
        lines += ['devSnmpSetParam("RequestTimeoutMSec", 2000)']
        runtime = self.observed_runtime(lines)
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        original, = {r["engine_id"] for r in proxy.records if r["event"] == "response" and r.get("engine_id")}
        first = len(proxy.records)
        agent.restart(WRONG_ENGINE if changed else original, 6)
        outcomes = [self.read(runtime, "A:") for _ in range(3 if changed else 1)]
        after = proxy.records[first:]
        if pinned:
            self.assertEqual(outcomes, [(VALUE, "3")] * 3)
            authenticated = [r for r in after if r["event"] == "request" and r.get("engine_id")]
            self.assertTrue(authenticated)
            self.assertTrue(all(r["engine_id"] == original for r in authenticated),
                            "Explicit engine identity silently rebound")
        else:
            self.assertEqual(outcomes[-1], (VALUE, "0"))
            if changed:
                self.assertTrue(any(r["event"] == "request" and r.get("engine_id") == WRONG_ENGINE for r in after))
            else:
                self.assertEqual(self.session_opens(runtime), 1)
                self.assertTrue(any(r["event"] == "response" and r.get("boots", 0) >= 6 for r in after))
        write_json(runtime.work / "engine-recovery.json", {"changed": changed, "pinned": pinned,
                   "outcomes": outcomes, "native_opens": self.session_opens(runtime)})

    def test_engine_reboot(self):
        self.engine_recovery(False, False)

    def test_engine_change(self):
        self.engine_recovery(True, False)

    def test_engine_pinned_change(self):
        self.engine_recovery(True, True)

    def test_profile_serialization(self):
        agent, proxy = self.agent()
        runtime = self.observed_runtime(self.setup_lines(proxy, timeout=2000, retries=0) +
                                       self.setup_lines(proxy, "f", "B:", timeout=2000, retries=0) +
                                       ['devSnmpSetParam("RequestTimeoutMSec", 4000)'])
        for prefix in ("A:", "B:"):
            self.assertEqual(self.read(runtime, prefix), (VALUE, "0"))
        self.assertEqual(self.session_opens(runtime), 2)
        self.assertEqual(len(self.children(runtime)), 1)
        proxy.fault("hold-requests")
        first = len(proxy.records)
        runtime.put("A:Name.PROC")
        runtime.wait_for(lambda: bool(proxy.held), "first profile's native request held")
        runtime.put("B:Name.PROC")
        time.sleep(0.1)
        self.assertEqual(sum(r["event"] == "request" for r in proxy.records[first:]), 1)
        proxy.fault("normal")
        proxy.release()
        runtime.wait_for(lambda: runtime.get("A:AuditName") == "2" and runtime.get("B:AuditName") == "2",
                         "serialized profile completions")
        self.assertEqual(runtime.get("A:Name.SEVR"), "0")
        self.assertEqual(runtime.get("B:Name.SEVR"), "0")
        self.assertEqual(self.session_opens(runtime), 2)

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
        self.discovery_isolation(False)

    def test_explicit_engine_isolation(self):
        self.discovery_isolation(True)

    def discovery_isolation(self, explicit):
        summaries = {}
        for mode in ("control", "cold", "restart"):
            agent, proxy = self.agent()
            other, second = self.agent()
            if mode == "cold":
                proxy.fault("drop-requests")
            lines = []
            for endpoint, prefix, observer in (("e", "A:", proxy), ("f", "B:", second)):
                binding = self.setup_lines(observer, endpoint, prefix, timeout=4000, retries=0)
                if explicit:
                    binding.insert(-1, f'devSnmpSetEndpointParam("{endpoint}", "securityEngineID", "{AGENT_ENGINE}")')
                lines += binding
            runtime = self.runtime(lines)
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
                               "explicit_engine_id": AGENT_ENGINE if explicit else None,
                               "p99_seconds": latency[(len(latency) * 99 + 99) // 100 - 1],
                               "record_deadline_ms": 400, "native_timeout_ms": 4000,
                               "requested_interval_seconds": ISOLATION_INTERVAL,
                               "mean_accepted_interval_seconds": (accepted[-1] - accepted[0]) / 1e9 / (len(accepted) - 1),
                               "evidence": str(runtime.work)}
            write_json(self.work / "isolation-summary.json", summaries)
            if mode != "control":
                self.assertLessEqual(summaries[mode]["p99_seconds"], summaries["control"]["p99_seconds"] + 0.1)
                dropped = [row for row in proxy.records if row["event"] == "request" and row["action"] == "drop"]
                self.assertTrue(dropped)
                if not explicit:
                    self.assertTrue(any(not row["engine_id"] for row in dropped))
            if explicit:
                for observer in (proxy, second):
                    identified = [row["engine_id"] for row in observer.records
                                  if row["event"] == "request" and row.get("engine_id")]
                    self.assertTrue(identified)
                    self.assertEqual(set(identified), {AGENT_ENGINE})
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
