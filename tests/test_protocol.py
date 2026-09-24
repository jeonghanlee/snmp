"""Exercise native protocol and USM through actual IOC GET, SET and readback."""

import json
from pathlib import Path
import tempfile
import unittest

from ioc import IOC, ROOT, is_legacy_baseline, settings, trace_evidence, write_json
from snmp_agent import Agent, Proxy, CONTACT, NAME


class ProtocolTest(unittest.TestCase):
    def exercise(self, version, level=None):
        config = settings()
        self.work = Path(tempfile.mkdtemp(prefix=f"protocol-{version}-{level}-", dir=config.get("output")))
        print(f"Evidence: {self.work}", flush=True)
        profile = config["profile"]
        self.assertIn(version, profile["protocols"], "Undeclared protocol cell")
        if level:
            self.assertIn(level, profile["security_levels"], "Undeclared security level")
        agent = Agent(self.work, profile)
        self.addCleanup(agent.close)
        proxy = Proxy(self.work, agent.port)
        self.addCleanup(proxy.close)
        host = f"127.0.0.1:{proxy.port}"
        dtype = config.get("dtyp", "SnmpRequest")
        lines = ['devSnmpSetParam("PassivePollMSec", 100)',
                 'devSnmpSetParam("SetSkipReadbackMSec", 100)',
                 f'devSnmpSetParam("SessionTimeout", {profile["session_timeout_us"]})',
                 f'devSnmpSetParam("SessionRetries", {profile["session_retries"]})',
                 f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_{version}")']
        if dtype == "SnmpRequest":
            lines += ['devSnmpSetParam("RequestTrace", 1)',
                      f'devSnmpSetParam("RequestTimeoutMSec", {profile["request_timeout_ms"]})']
        if level:
            lines.append(f'devSnmpSetSnmpV3ConfigFile("{host}", "{agent.ioc_config(level)}")')
        lines.append(f'dbLoadRecords("{ROOT}/tests/protocol.db", "P=SNMPTEST:,HOST={host},DTYP={dtype}")')
        build = Path(config["ioc"]).resolve().parents[2] / "build-inputs.json"
        baseline = build.is_file() and is_legacy_baseline(json.loads(build.read_text()))
        runtime = IOC(self.work, lines, require_shutdown=not baseline)
        self.addCleanup(runtime.close)
        runtime.put("Name.PROC")
        runtime.wait_for(lambda: runtime.get("Name.PACT") == "0" and runtime.get("Name") == r'\"fixture-agent\"',
                         "native agent identity through the IOC")
        self.assertEqual(runtime.get("Name.SEVR"), "0")
        runtime.put("ContactSet", "fixture-applied")
        def applied():
            result = agent.client(version, level, CONTACT)
            write_json(self.work / "agent-readback.json", {"status": result.returncode,
                                                           "out": result.stdout, "err": result.stderr})
            return result.returncode == 0 and "fixture-applied" in result.stdout
        runtime.wait_for(applied, "native SET application observed by an independent native client")
        runtime.put("Contact.PROC")
        runtime.wait_for(lambda: runtime.get("Contact.PACT") == "0" and runtime.get("Contact") == r'\"fixture-applied\"',
                         "IOC native readback")
        self.assertEqual(runtime.get("Contact.SEVR"), "0")
        runtime.close()
        trace_evidence(self.work)
        self.assertEqual(proxy.errors, [])
        requests = [row for row in proxy.records if row["event"] == "request"]
        responses = [row for row in proxy.records if row["event"] == "response"]
        self.assertTrue(requests and responses, "No real protocol exchange")
        self.assertTrue(all(row["version"] == {"1": 0, "2c": 1, "3": 3}[version] for row in requests))
        if version == "3":
            self.assertTrue(any(not row["engine_id"] for row in requests), "Discovery was not observed")
            flags = {"noAuthNoPriv": 0, "authNoPriv": 1, "authPriv": 3}[level]
            self.assertTrue(any(row["engine_id"] and row["flags"] & 3 == flags for row in requests))
            self.assertTrue(any(row["engine_id"] and row["flags"] & 3 == flags for row in responses))
        if level != "authPriv":
            self.assertTrue(any(row.get("pdu") == 0xA3 and CONTACT in row["numeric_oids"] for row in requests))
            self.assertTrue(any(row.get("pdu") == 0xA0 and NAME in row["numeric_oids"] for row in requests))

    def test_v1(self):
        self.exercise("1")

    def test_v2c(self):
        self.exercise("2c")

    def test_v3_no_auth(self):
        self.exercise("3", "noAuthNoPriv")

    def test_v3_auth(self):
        self.exercise("3", "authNoPriv")

    def test_v3_priv(self):
        self.exercise("3", "authPriv")
