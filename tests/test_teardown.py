"""Owned terminal EOF, explicit exit and crash recovery use real IOC teardown."""

import re
import json
from pathlib import Path
import tempfile

from diagnostics import sample
from ioc import IOC, ROOT, is_legacy_baseline, settings, write_json
from request_cases import Scenario, ScenarioTest
from snmp_peer import Peer


CASES = ("eof_network", "explicit_network", "eof_callback", "explicit_callback", "forced_recovery", "base_exit_observer")
STARTS = 20
MARKERS = ("request shutdown entered", "completion worker stopped", "request callbacks drained",
           "network workers stopped", "shutdown complete")


class TeardownTest(ScenarioTest):
    def test_base_exit_observer(self):
        build = json.loads((Path(settings()["ioc"]).resolve().parents[2] / "build-inputs.json").read_text())
        baseline = is_legacy_baseline(build)
        results = []
        for mode in ("eof", "explicit"):
            work = Path(tempfile.mkdtemp(prefix="base-exit-" + mode + "-", dir=self.work))
            peer = Peer(work)
            runtime = None
            try:
                peer.hold = True
                host = f"127.0.0.1:{peer.server_address[1]}"
                lines = ['var atExitDebug 1', 'devSnmpSetParam("SessionRetries", 0)',
                         'devSnmpSetParam("SessionTimeout", 2000000)',
                         f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")',
                         f'dbLoadRecords("{ROOT}/tests/legacy.db", "P=SNMPTEST:,HOST={host}")']
                runtime = IOC(work, lines, terminal=True, require_shutdown=not baseline)
                runtime.wait_for(lambda: bool(peer.held), "actual legacy network work")
                runtime.close(mode=mode)
                log = (work / "ioc.log").read_text()
                hooks = re.findall(r"atExit [^\n]+", log)
                self.assertTrue(hooks, "Missing actual Base exit hooks")
                self.assertTrue(any("snmpAtExit" in hook for hook in hooks), "Missing actual module exit hook")
                self.assertNotIn("Variable atExitDebug not found", log)
                results.append(dict(mode=mode, hooks=hooks, baseline=baseline, evidence=str(work),
                                    exit_code=runtime.metadata["exit_code"], cleanup_error=runtime.metadata["cleanup_error"]))
            finally:
                if runtime:
                    runtime.close()
                peer.close()
        write_json(self.work / "exit-observations.json", results)

    def shutdowns(self, mode, pending):
        for number in range(STARTS):
            s = Scenario(self, f"{mode}-{pending}-{number}", ioc_options={"terminal": True})
            try:
                if pending == "network":
                    s.peer.hold = True
                    s.put("A.PROC")
                    s.wait(lambda: bool(s.peer.held), "real outstanding UDP request")
                    self.assertEqual(sample(s)["A"]["state"], "inflight")
                else:
                    s.runtime.process.stdin.write("requestBlockCallbacks()\n")
                    s.runtime.process.stdin.flush()
                    s.wait(lambda: "SNMPBLOCK ready" in (s.work / "ioc.log").read_text(), "real Base callback blocker")
                    s.put("A.PROC")
                    s.wait(lambda: sample(s)["A"]["state"] == "scheduled", "actual pending request callback")
                self.assertEqual(s.get("A.PACT"), "1")
                self.assertEqual(s.get("AuditA"), "0")
                s.runtime.close(mode=mode)
                log = (s.work / "ioc.log").read_text()
                offsets = []
                for marker in MARKERS:
                    self.assertEqual(log.count("devSnmp: " + marker), 1, marker)
                    offsets.append(log.index("devSnmp: " + marker))
                self.assertEqual(offsets, sorted(offsets))
                self.assertNotRegex(log[offsets[0]:], r"SNMPAUDIT \d+")
                self.assertTrue(s.runtime.metadata["terminal"]["isatty"])
                self.assertEqual(s.runtime.metadata["terminal"]["path"], s.runtime.metadata["terminal"]["child_fd0"])
                self.assertEqual(s.runtime.metadata["exit_code"], 0)
                self.assertIsNone(s.runtime.metadata["cleanup_error"])
            finally:
                s.close(verify=False)

    def test_forced_recovery(self):
        for number in range(STARTS):
            s = Scenario(self, f"forced-{number}", ioc_options={"terminal": True}, hold=True)
            try:
                s.put("A.PROC")
                s.wait(lambda: bool(s.peer.held), "pending request before owned crash")
                s.runtime.close(mode="forced")
                self.assertEqual(s.runtime.metadata["exit_code"], -9)
                self.assertNotIn("devSnmp: shutdown complete", (s.work / "ioc.log").read_text())
            finally:
                s.close(verify=False)
            with self.scenario(f"recovery-{number}", ioc_options={"terminal": True}) as recovered:
                recovered.put("A.PROC")
                recovered.done("A", 1, 101)


for _mode in ("eof", "explicit"):
    for _pending in ("network", "callback"):
        def _case(self, mode=_mode, pending=_pending):
            self.shutdowns(mode, pending)
        setattr(TeardownTest, "test_" + _mode + "_" + _pending, _case)
