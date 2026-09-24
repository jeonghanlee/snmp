"""Exercise delivered examples, registration products and rejected configuration."""

import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import unittest

from ioc import IOC, ROOT, digest, is_legacy_baseline, now, settings, write_json
from snmp_peer import Peer


CASES = ("production_example", "test_example", "invalid_records", "parameters", "mismatched_registration")
DSETS = ("devSnmpRequestAi", "devSnmpRequestLi", "devSnmpRequestSi")
INPUT = "@{host} public .1.3.6.1.4.1.55555.1.0 INTEGER: {length}"


class RegistrationTest(unittest.TestCase):
    def setUp(self):
        self.config = settings()
        self.work = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=self.config["output"]))
        self.top = Path(self.config["ioc"]).parents[2]
        self.arch = Path(self.config["ioc"]).parent.name
        self.peer = Peer(self.work)
        self.addCleanup(self.peer.close)
        self.host = f"127.0.0.1:{self.peer.server_address[1]}"

    def child(self, label):
        work = self.work / label
        work.mkdir()
        return work

    def example(self, name):
        executable = self.top / "bin" / self.arch / name
        dbd = self.top / "dbd" / (name + ".dbd")
        generated = list(self.top.glob("**/O.*/" + name + "_registerRecordDeviceDriver.cpp"))
        self.assertEqual(len(generated), 1)
        symbols = subprocess.check_output(["nm", "-D", str(self.top / "lib" / self.arch / "libdevSnmp.so")], text=True)
        (self.work / "exported-symbols.txt").write_text(symbols)
        for dset in DSETS:
            self.assertIn(dset, dbd.read_text())
            self.assertIn("pvar_dset_" + dset, generated[0].read_text())
            self.assertRegex(symbols, r"(?m)^\S+\s+\S\s+pvar_dset_" + dset + r"$")
        inputs = [dbd, generated[0], ROOT / "examples/request-inputs.db", ROOT / "examples/request-inputs.iocsh"]
        write_json(self.work / "registration-inputs.json", {str(p): digest(p) for p in inputs})
        runtime = IOC(self.work, [
            'devSnmpSetParam("PassivePollMSec", 100)',
            'devSnmpSetParam("SessionRetries", 0)',
            'devSnmpSetParam("SessionTimeout", 200000)',
            f'iocshLoad("{ROOT}/examples/request-inputs.iocsh", "SNMP={ROOT},P=SNMPTEST:,HOST={self.host}")',
        ], executable=executable)
        try:
            runtime.wait_for(lambda: runtime.get("Legacy") == "123", "legacy read through delivered example")
            for cycle in range(3):
                self.peer.values.update({1: 101 + cycle, 2: 202 + cycle, 3: "example" + str(cycle), 4: 123 + cycle})
                for record, expected in (("Analog", str(101 + cycle)), ("Integer", str(202 + cycle)),
                                         ("Text", '\\"example' + str(cycle) + '\\"')):
                    runtime.put(record + ".PROC")
                    runtime.wait_for(lambda: runtime.get(record) == expected and runtime.get(record + ".PACT") == "0",
                                     "actual registered " + record + " completion")
                    self.assertEqual(runtime.get_many([record + suffix for suffix in (".UDF", ".STAT", ".SEVR")]),
                                     {record + suffix: "0" for suffix in (".UDF", ".STAT", ".SEVR")})
                self.assertEqual(runtime.get("TextAtCompletion"), runtime.get("Text"))
                runtime.wait_for(lambda: runtime.get("Legacy") == str(123 + cycle), "legacy polling remains active")
            self.assertEqual(self.peer.errors, [])
            self.assertTrue(self.peer.requests)
            self.assertTrue(all(r["pdu"] == 0xA0 for r in self.peer.requests), "Input example issued SET")
        finally:
            runtime.close()

    def test_production_example(self):
        self.example("snmp")

    def test_test_example(self):
        self.example("snmpRequestTest")

    def test_invalid_records(self):
        valid = INPUT.format(host=self.host, length=128)
        cases = (("io-intr", valid, "I/O Intr", "invalid INP or SCAN"),
                 ("missing", "", "Passive", "invalid input configuration"),
                 ("constant", "42", "Passive", "invalid input configuration"),
                 ("malformed", "@bad", "Passive", "invalid input configuration"),
                 ("short", INPUT.format(host=self.host, length=1), "Passive", "invalid input configuration"),
                 ("long", INPUT.format(host=self.host, length=65537), "Passive", "invalid input configuration"),
                 ("flag", valid + " s?", "Passive", "invalid input configuration"),
                 ("oid", valid.replace(".1.3.6.1.4.1.55555.1.0", "SNMP_TEST_NO_SUCH_OID"),
                  "Passive", "invalid input configuration"))
        for label, inp, scan, message in cases:
            work = self.child(label)
            runtime = IOC(work, [
                f'dbLoadRecords("{ROOT}/tests/registration.db", "P=SNMPTEST:,SCAN={scan},INP={inp}")',
            ], require_shutdown=False)
            try:
                runtime.put("Input.PROC")
                runtime.wait_for(lambda: runtime.get("Input.SEVR") == "3", "invalid record alarm")
                self.assertEqual(runtime.get("Input.UDF"), "1")
            finally:
                runtime.close()
            self.assertIn("SnmpRequest: " + message, (work / "ioc.log").read_text(), label)
        self.assertEqual(self.peer.requests, [], "Rejected records issued wire requests")

    def test_parameters(self):
        invalid = (("RequestTimeoutMSec", -1), ("RequestTimeoutMSec", 0), ("RequestTimeoutMSec", 3600001),
                   ("RequestTrace", -1), ("RequestTrace", 2))
        lines = ['devSnmpSetParam("RequestTimeoutMSec", 1)',
                 'devSnmpSetParam("RequestTimeoutMSec", 3600000)',
                 'devSnmpSetParam("RequestTimeoutMSec", 400)',
                 'devSnmpSetParam("RequestTrace", 0)', 'devSnmpSetParam("RequestTrace", 1)']
        lines += [f'devSnmpSetParam("{name}", {value})' for name, value in invalid]
        lines += ['devSnmpSetParam()', 'devSnmpSetParam("SessionTimeout", 60000000)',
                  'devSnmpSetParam("SessionRetries", 0)',
                  f'dbLoadRecords("{ROOT}/tests/registration.db", "P=SNMPTEST:,INP={INPUT.format(host=self.host, length=128)}")']
        runtime = IOC(self.work, lines, terminal=True)
        try:
            prompts = runtime.terminal_prompts()
            runtime.process.stdin.write('devSnmpSetParam("RequestTimeoutMSec", 5000)\n'
                                        'devSnmpSetParam("RequestTrace", 0)\ndevSnmpSetParam()\n')
            runtime.process.stdin.flush()
            runtime.wait_for(lambda: runtime.terminal_prompts() >= prompts + 3, "post-init parameter rejection")
            self.peer.mode = "drop"
            start = time.monotonic()
            runtime.put("Input.PROC")
            runtime.wait_for(lambda: bool(self.peer.requests), "real unanswered request")
            runtime.wait_for(lambda: runtime.get("Input.SEVR") == "3" and runtime.get("Input.PACT") == "0",
                             "unchanged 400 ms acquisition deadline")
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, self.config["profile"]["limits"]["deadline_completion_seconds"])
            write_json(self.work / "parameter-timing.json", {"elapsed_seconds": elapsed})
        finally:
            runtime.close()
        log = (self.work / "ioc.log").read_text()
        self.assertEqual(log.count("devSnmp: invalid or post-init request parameter:"), len(invalid) + 2)
        self.assertEqual(re.findall(r"(?m)^RequestTimeoutMSec\s+(\d+)\s*$", log), ["400", "400"])
        self.assertEqual(re.findall(r"(?m)^RequestTrace\s+(\d+)\s*$", log), ["1", "1"])

    def test_mismatched_registration(self):
        old = Path(self.config["baseline_ioc"])
        old_top = old.parents[2]
        manifest = json.loads((old_top / "build-inputs.json").read_text())
        self.assertTrue(is_legacy_baseline(manifest), "Mismatch test requires the unmodified archived baseline")
        self.assertEqual(manifest["artifacts"][str(old.relative_to(old_top))], digest(old))
        new = self.top / "bin" / self.arch / "snmp"
        for label, executable, dbd in (("old-ioc-new-dbd", old, self.top / "dbd/snmp.dbd"),
                                       ("new-ioc-old-dbd", new, old_top / "dbd/snmp.dbd")):
            work = self.child(label)
            startup = work / "st.cmd"
            startup.write_text(f'dbLoadDatabase("{dbd}")\nsnmp_registerRecordDeviceDriver(pdbbase)\n'
                               f'dbLoadRecords("{ROOT}/tests/registration.db", "P=SNMPTEST:,INP={INPUT.format(host=self.host, length=128)}")\n'
                               'iocInit\n')
            native = work / "native"
            native.mkdir()
            with socket.socket() as reserve:
                reserve.bind(("127.0.0.1", 0))
                port = reserve.getsockname()[1]
            environment = dict(os.environ, SNMPCONFPATH=str(native), SNMP_PERSISTENT_DIR=str(native), MIBS="",
                               EPICS_CAS_INTF_ADDR_LIST="127.0.0.1", EPICS_CAS_SERVER_PORT=str(port),
                               EPICS_CAS_AUTO_BEACON_ADDR_LIST="NO", EPICS_CAS_BEACON_ADDR_LIST="")
            started = now()
            argv = [str(executable), str(startup)]
            result = subprocess.run(argv, input="exit\n", text=True, env=environment, cwd=executable.parents[2],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
            (work / "ioc.log").write_text(result.stdout)
            write_json(work / "mismatch.json", {"argv": argv, "cwd": str(executable.parents[2]),
                       "started_at": started, "finished_at": now(), "exit_code": result.returncode,
                       "ioc_sha256": digest(executable), "dbd_sha256": digest(dbd),
                       "startup_sha256": digest(startup), "baseline_manifest_sha256": digest(old_top / "build-inputs.json")})
            self.assertEqual(result.returncode, 0, "Mismatch caused a crash instead of a visible registration failure")
            if label == "old-ioc-new-dbd":
                self.assertRegex(result.stdout, r"(?i)device support.*not found")
            else:
                self.assertIn("no such device support for 'ai'", result.stdout)
                self.assertIn("Failed to load", result.stdout)
        self.assertEqual(self.peer.requests, [], "Mismatched request binding reached the peer")
