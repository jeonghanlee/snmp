"""Compare the same delivered legacy records on independent native module builds."""

import json
from pathlib import Path
import tempfile
import unittest

from ioc import IOC, ROOT, digest, is_legacy_baseline, settings, trace_evidence, verified_baseline, write_json
from snmp_peer import Peer, oid_bytes


RECORDS = ("Analog", "Integer", "Text", "Wave", "AnalogSet", "IntegerSet", "TextSet")


class LegacyTest(unittest.TestCase):
    def setUp(self):
        config = settings()
        self.work = Path(tempfile.mkdtemp(prefix="legacy-", dir=config.get("output")))
        print(f"Evidence: {self.work}", flush=True)
        self.peer = Peer(self.work, writable=True)
        self.peer.values.update({5: 500, 6: 600, 7: "initial"})
        self.peer.names.update({oid_bytes((1, 3, 6, 1, 4, 1, 55555, key, 0)): key for key in (5, 6, 7)})
        self.addCleanup(self.peer.close)
        host = f"127.0.0.1:{self.peer.server_address[1]}"
        profile = config["profile"]
        lines = [
            'devSnmpSetParam("PassivePollMSec", 100)',
            'devSnmpSetParam("SetSkipReadbackMSec", 100)',
            'devSnmpSetParam("SessionRetries", 0)',
            f'devSnmpSetParam("DataStaleTimeoutMSec", {profile["legacy_stale_ms"]})',
            f'devSnmpSetParam("SessionTimeout", {profile.get("fault_timeout_us", 200000)})',
            f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")',
            f'dbLoadRecords("{ROOT}/tests/legacy_matrix.db", "P=SNMPTEST:,HOST={host}")',
        ]
        build = Path(config["ioc"]).resolve().parents[2] / "build-inputs.json"
        baseline = build.is_file() and is_legacy_baseline(json.loads(build.read_text()))
        self.runtime = IOC(self.work, lines, require_shutdown=not baseline)
        self.addCleanup(self.cleanup)
        self.observations = {}

    def cleanup(self):
        self.runtime.close()
        trace_evidence(self.work)
        self.assertEqual(self.peer.errors, [])

    def snapshot(self, label, expected=None):
        for record in RECORDS:
            self.runtime.client(["caget", "-w", "0.4", "-a", self.runtime.prefix + record])
        def sample():
            values = {record: {field: self.runtime.get(record + field)
                               for field in ("", ".PACT", ".UDF", ".STAT", ".SEVR")} for record in RECORDS}
            with (self.work / "legacy-samples.jsonl").open("a") as log:
                log.write(json.dumps({"phase": label, "values": values}) + "\n")
            self.observations[label] = values
            if expected is None:
                return True
            return (all(values[record][""] == value for record, value in expected.items()) and
                    all(values[record][field] == "0" for record in RECORDS
                        for field in (".PACT", ".UDF", ".STAT", ".SEVR")))
        self.runtime.wait_for(sample, "observed legacy readback state: " + label)
        self.observations[label]["Analog"][".RVAL"] = self.runtime.get("Analog.RVAL")
        self.observations[label]["AnalogSet"][".RVAL"] = self.runtime.get("AnalogSet.RVAL")
        self.observations[label]["Wave"][".NORD"] = self.runtime.get("Wave.NORD")
        write_json(self.work / "legacy-observations.json", self.observations)

    def test_inputs_and_outputs(self):
        runtime = self.runtime
        runtime.wait_for(lambda: all(runtime.get(record + ".UDF") == "0" for record in RECORDS),
                         "all legacy inputs and output readbacks")
        self.snapshot("initial", {"Analog": "12.3", "Integer": "202", "Text": r'\"hello\"',
                                  "AnalogSet": "50", "IntegerSet": "600", "TextSet": r'\"initial\"'})
        initial = self.observations["initial"]
        self.assertEqual(initial["Analog"][".RVAL"], "123")
        wave = [int(part) for part in initial["Wave"][""].split()]
        self.assertEqual(wave[0], 128)
        self.assertEqual(bytes(wave[1:9]), b' "hello"')
        self.assertEqual(wave[9:], [0] * 120)
        self.assertEqual(initial["Wave"][".NORD"], "8")
        self.assertFalse(any(row["pdu"] == 0xA3 for row in self.peer.requests), "Readback caused a SET")
        for record, key, value, raw, kind in (("AnalogSet", 5, 25.5, 255, 2),
                                              ("IntegerSet", 6, -77, -77, 2),
                                              ("TextSet", 7, "applied", "applied", 4)):
            runtime.put(record, value)
            runtime.wait_for(lambda: self.peer.values[key] == raw, "actual peer SET application")
            writes = [item for row in self.peer.requests for item in row["sets"] if item["key"] == key]
            self.assertEqual(len(writes), 1)
            self.assertEqual((writes[0]["value"], writes[0]["type"]), (raw, kind))
        self.peer.values.update({2: -333, 3: "changed", 4: 246, 5: 777, 6: 888, 7: "external"})
        runtime.wait_for(lambda: runtime.get("Analog") == "24.6" and runtime.get("Integer") == "-333"
                         and runtime.get("Text") == r'\"changed\"', "changed legacy inputs")
        runtime.wait_for(lambda: runtime.get("AnalogSet") == "77.7" and runtime.get("IntegerSet") == "888"
                         and runtime.get("TextSet") == r'\"external\"', "independent output readback")
        self.assertEqual(sum(row["pdu"] == 0xA3 for row in self.peer.requests), 3, "Readback echoed a SET")
        changed = {"Analog": "24.6", "Integer": "-333", "Text": r'\"changed\"',
                   "AnalogSet": "77.7", "IntegerSet": "888", "TextSet": r'\"external\"'}
        self.snapshot("changed", changed)
        self.peer.mode = "drop"
        runtime.wait_for(lambda: all(runtime.get(record + ".SEVR") == "3" for record in RECORDS[4:]),
                         "legacy output readback communication alarm")
        runtime.wait_for(lambda: all(runtime.get(record + ".PACT") == "1" for record in RECORDS[:4]),
                         "legacy inputs waiting for cache recovery")
        self.snapshot("timeout")
        self.peer.mode = "normal"
        runtime.wait_for(lambda: all(runtime.get(record + ".SEVR") == "0" for record in RECORDS),
                         "legacy alarm recovery")
        runtime.wait_for(lambda: runtime.get("TextSet") == r'\"external\"'
                         and all(runtime.get(record + ".PACT") == "0" for record in RECORDS),
                         "legacy value and activity recovery")
        self.snapshot("recovered", changed)
        for record in RECORDS:
            for field in ("", ".PACT", ".UDF", ".SEVR"):
                self.assertEqual(self.observations["changed"][record][field],
                                 self.observations["recovered"][record][field], (record, field))
        self.assertEqual(sum(row["pdu"] == 0xA3 for row in self.peer.requests), 3)
        self.compare_baseline()

    def compare_baseline(self):
        baseline = settings().get("baseline_evidence")
        if not baseline:
            return
        source_dir, metadata = verified_baseline(self, "legacy", "test_inputs_and_outputs", (
            "tests/legacy_matrix.db", "tests/identity.db", "tests/ioc.py",
            "tests/test_legacy.py", "tests/snmp_peer.py"))
        build = metadata["build_manifest"]
        source = source_dir / "legacy-observations.json"
        expected = json.loads(source.read_text())
        observed = json.loads(json.dumps(self.observations))
        for values in (expected, observed):
            for record in RECORDS[:4]:
                for field in (".STAT", ".SEVR"):
                    del values["timeout"][record][field]
        write_json(self.work / "baseline-comparison.json", {
            "baseline": str(source), "baseline_sha256": digest(source),
            "baseline_commit": build["source_commit"],
            "baseline_build_sha256": metadata["build_manifest_sha256"],
            "excluded": "timeout input STAT/SEVR: Base active-scan alarm timing",
            "expected": expected, "observed": observed, "equal": expected == observed,
        })
        self.assertEqual(expected, observed, "Legacy baseline differs")
