"""Real record conversions and independently built legacy waveform comparison."""

import json
from pathlib import Path

from ioc import IOC, ROOT, digest, is_legacy_baseline, settings, verified_baseline, write_json
from request_cases import ScenarioTest
from snmp_peer import Peer


CASES = ("requests_and_mixed", "waveforms")
WAVE_TYPES = ("STRING", "CHAR", "UCHAR")
WAVE_LENGTHS = (16, 128)
SIGNED = (-2147483648, -1, 0, 2147483647)
TEXT = ("", "alpha", "longer-text", "x", "a" * 60, "end")


class ConversionTest(ScenarioTest):
    def test_requests_and_mixed(self):
        extra = ('devSnmpSetParam("PassivePollMSec", 100)',
                 'devSnmpSetParam("SetSkipReadbackMSec", 100)')
        with self.scenario("conversions", fixture="conversion.db", values={3: "initial"}, extra=extra) as s:
            s.wait(lambda: s.get("LegacyText") == r'\"initial\"', "initial legacy string")
            s.put("Text.PROC")
            s.done("Text", 1, 0, text='"initial"')
            prior_text = '"initial"'
            for cycle in range(self.cycles()):
                value = 1000 + cycle
                raw = 123 if cycle % 2 == 0 else 246
                signed = SIGNED[cycle % len(SIGNED)]
                text = TEXT[cycle % len(TEXT)]
                with s.peer.lock:
                    s.peer.values.update({1: value, 2: signed, 3: text, 4: raw})
                s.wait(lambda: s.get("Legacy") == str(value) and s.get("Readback") == str(value),
                       "legacy input and output readback share the new device value")
                self.assertEqual(s.get("AuditVal"), str(cycle))
                self.assertEqual(s.get("Val.PACT"), "0")
                s.put("All.PROC")
                s.done("Val", cycle + 1, value)
                s.done("Raw", cycle + 1, raw / 10, raw=raw)
                s.done("Integer", cycle + 1, signed)
                if text:
                    prior_text = ('"' + text + '"')[:39]
                    severity, status = 0, 0
                else:
                    severity, status = 3, 1
                s.done("Text", cycle + 2, 0, severity=severity, status=status, text=prior_text)
                ca_text = prior_text.replace('"', '\\"')
                self.assertEqual(s.get("Text"), ca_text)
                s.wait(lambda: s.get("LegacyText") == ca_text and
                       s.get("LegacyText.SEVR") == str(severity) and
                       s.get("LegacyText.STAT") == str(status), "legacy and request text contract")

    def test_waveforms(self):
        config = settings()
        build = json.loads((Path(config["ioc"]).resolve().parents[2] / "build-inputs.json").read_text())
        baseline = is_legacy_baseline(build)
        if not baseline:
            self.assertTrue(config.get("baseline_evidence"), "Waveform candidate requires independent baseline")
        peer = Peer(self.work)
        runtime = None
        observations = []
        try:
            host = f"127.0.0.1:{peer.server_address[1]}"
            runtime = IOC(self.work, [
                'devSnmpSetParam("PassivePollMSec", 100)',
                'devSnmpSetParam("SessionRetries", 0)',
                f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")',
                f'dbLoadRecords("{ROOT}/tests/waveform.db", "P=SNMPTEST:,HOST={host}")',
            ], require_shutdown=not baseline)
            for cycle in range(self.cycles()):
                text = f"{cycle:05d}"
                peer.values[3] = text
                values = {}
                for kind in WAVE_TYPES:
                    for length in WAVE_LENGTHS:
                        record = f"Wave{kind}{length}"
                        expected = b' "' + text.encode() + b'"'
                        def sample():
                            value = runtime.get(record, options=("-#", "1") if kind == "STRING" else ())
                            fields = {name: runtime.get(record + "." + name)
                                      for name in ("NORD", "PACT", "UDF", "STAT", "SEVR")}
                            values[record] = dict(value=value, **fields)
                            if kind == "STRING":
                                matched = value == '1  \\"' + text + '\\"'
                            else:
                                array = [int(part) for part in value.split()]
                                matched = (array == [length] + list(expected) + [0] * (length - len(expected)))
                            return matched and fields == dict(NORD=str(len(expected)), PACT="0", UDF="0", STAT="0", SEVR="0")
                        runtime.wait_for(sample, "waveform conversion: " + record)
                observations.append(values)
            self.assertEqual(peer.errors, [])
            self.assertTrue(peer.requests)
            self.assertTrue(all(row["pdu"] == 0xA0 for row in peer.requests), "Waveform read caused SET")
        finally:
            try:
                if runtime:
                    runtime.close()
            finally:
                peer.close()
                write_json(self.work / "waveform-observations.json", observations)
        if baseline:
            return
        source_dir, metadata = verified_baseline(self, "conversion", "test_waveforms", (
            "tests/waveform.db", "tests/identity.db", "tests/ioc.py", "tests/request_cases.py",
            "tests/test_conversion.py", "tests/snmp_peer.py"))
        source = source_dir / "waveform-observations.json"
        expected = json.loads(source.read_text())
        write_json(self.work / "baseline-comparison.json", {
            "baseline": str(source), "baseline_sha256": digest(source),
            "baseline_commit": metadata["build_manifest"]["source_commit"],
            "baseline_build_sha256": metadata["build_manifest_sha256"],
            "expected": expected, "observed": observations, "equal": expected == observations,
        })
        self.assertEqual(expected, observations, "Legacy waveform baseline differs")
