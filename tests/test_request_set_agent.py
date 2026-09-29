"""Request outputs against actual snmpd, including its native float watcher."""

import json
import time

from ioc import IOC, ROOT, settings, trace_evidence, write_json
from request_cases import PREFIX, ScenarioTest
from snmp_agent import AUTH, USERS, Agent, Proxy


CASES = ("v2c", "named_endpoint", "unknown_user", "wrong_key", "session_retirement")
FLOAT_OID = ".1.3.6.1.4.1.55556.9.0"
INTEGER_OID = ".1.3.6.1.4.1.55555.6.0"


class RequestSetAgentTest(ScenarioTest):
    def start(self, named=False, fault=None):
        agent = Agent(self.work, settings()["profile"], writable=True, opaque_float=True)
        self.addCleanup(agent.close)
        proxy = Proxy(self.work, agent.port)
        self.addCleanup(proxy.close)
        host = f"127.0.0.1:{proxy.port}"
        lines = ['devSnmpSetParam("RequestTrace", 1)',
                 'devSnmpSetParam("RequestTimeoutMSec", 10000)',
                 'devSnmpSetParam("SessionTimeout", 200000)',
                 'devSnmpSetParam("SessionRetries", 0)']
        community = "public"
        if named:
            keys = self.work / "keys"
            keys.write_text("authPassPhrase " + ("wrong-auth-test-only" if fault == "key" else AUTH) + "\n")
            keys.chmod(0o600)
            profile = self.work / "profile"
            user = "nosuchuser" if fault == "user" else USERS["authNoPriv"]
            profile.write_text(f"securityName {user}\nsecurityLevel authNoPriv\nauthType SHA\ncredentialFile {keys}\n")
            lines += [f'devSnmpLoadV3Profile("p", "{profile}")',
                      f'devSnmpDefineEndpoint("e", "udp:{host}", "p")',
                      'devSnmpSetEndpointParam("e", "timeoutMSec", "200")',
                      'devSnmpSetEndpointParam("e", "retries", "0")']
            host, community = "endpoint:e", "-"
        else:
            lines.append(f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")')
        lines.append(f'dbLoadRecords("{ROOT}/tests/request_set_agent.db", "P={PREFIX},HOST={host},COMM={community}")')
        work = self.work / "ioc"
        work.mkdir()
        runtime = IOC(work, lines)
        self.addCleanup(runtime.close)
        return agent, proxy, runtime

    def completion(self, runtime, record, count, status=0):
        runtime.wait_for(lambda: runtime.get("Audit" + record) == str(count) and
                         runtime.get(record + ".PACT") == "0", "native SET completion")
        self.assertEqual(runtime.get(record + ".STAT"), str(status))
        self.assertEqual(runtime.get(record + ".SEVR"), "3" if status else "0")

    def verify(self, runtime, expected):
        runtime.close()
        driver, audits = trace_evidence(runtime.work)
        groups = {}
        for row in driver:
            groups.setdefault((row["record"], row["generation"]), []).append(row)
        self.assertEqual(set(groups), {(PREFIX + record, generation) for record, generation in expected})
        self.assertEqual(len(audits), len(expected))
        for (record, generation), status in expected.items():
            events = groups[PREFIX + record, generation]
            self.assertEqual([r["event"] for r in events],
                             ["accepted", "claimed", "dispatch", "result", "applied", "complete"])
            self.assertEqual([r["time"] for r in events], sorted(r["time"] for r in events))
            audit, = [a for a in audits if a["record"] == PREFIX + "Audit" + record and a["count"] == generation]
            self.assertEqual((audit["pact"], audit["status"], audit["severity"]), (1, status, 3 if status else 0))
            self.assertLessEqual(events[-2]["time"], audit["time"])
            self.assertLessEqual(audit["time"], events[-1]["time"])
            self.assertEqual(events[-2]["success"], status == 0)
            self.assertTrue(events[-1]["success"])
        write_json(self.work / "acceptance.json", dict(generations=len(groups), audits=len(audits), passed=True))

    def success(self, named):
        agent, proxy, runtime = self.start(named)
        expected = {}
        for cycle in range(self.cycles()):
            for record, value, oid, wire in (
                    ("AnalogSet", 12 + cycle, ".1.3.6.1.4.1.55555.5.0", 120 + 10 * cycle),
                    ("EngineeringSet", 20 + cycle, ".1.3.6.1.4.1.55555.5.0", 20 + cycle),
                    ("IntegerSet", 41 + cycle, INTEGER_OID, 41 + cycle),
                    ("FloatSet", 3.5 + cycle, FLOAT_OID, 3.5 + cycle),
                    ("TextSet", "value" + str(cycle), ".1.3.6.1.4.1.55555.7.0", "value" + str(cycle))):
                runtime.put(record, value)
                self.completion(runtime, record, cycle + 1)
                oracle = agent.client("2c", None, oid)
                write_json(self.work / f"oracle-{record}-{cycle}.json", dict(status=oracle.returncode,
                           stdout=oracle.stdout, stderr=oracle.stderr))
                self.assertEqual(oracle.returncode, 0, oracle.stderr)
                returned_oid, scalar = oracle.stdout.strip().split(" = ", 1)
                self.assertEqual(returned_oid, oid)
                kind = "STRING: " if isinstance(wire, str) else "Opaque: Float: " if isinstance(wire, float) else "INTEGER: "
                self.assertTrue(scalar.startswith(kind), scalar)
                encoded = scalar[len(kind):]
                observed = json.loads(encoded) if isinstance(wire, str) else float(encoded) if isinstance(wire, float) else int(encoded)
                self.assertEqual(observed, wire)
                expected[record, cycle + 1] = (value, wire)
        # Coexistence uses a real request input and legacy output on the same endpoint.
        runtime.put("IntegerRead.PROC")
        runtime.wait_for(lambda: runtime.get("IntegerRead.PACT") == "0" and
                         runtime.get("IntegerRead") == str(40 + self.cycles()), "request input readback")
        runtime.put("LegacySet", 81)
        runtime.wait_for(lambda: json.loads(agent.values_path.read_text())["values"]["5"] == 81,
                         "legacy SET on shared endpoint")
        runtime.close()
        # The input has no output FLNK audit; keep its six events separate.
        driver, audits = trace_evidence(runtime.work)
        output_events = [r for r in driver if r["record"] != PREFIX + "IntegerRead"]
        self.assertEqual(len(output_events), 6 * len(expected))
        self.assertEqual(len(audits), len(expected))
        for (record, generation), (value, wire) in expected.items():
            events = [r for r in output_events if r["record"] == PREFIX + record and r["generation"] == generation]
            self.assertEqual([r["event"] for r in events], ["accepted", "claimed", "dispatch", "result", "applied", "complete"])
            self.assertEqual([r["time"] for r in events], sorted(r["time"] for r in events))
            self.assertTrue(all(r["success"] for r in events[-3:]))
            audit, = [a for a in audits if a["record"] == PREFIX + "Audit" + record and a["count"] == generation]
            self.assertEqual((audit["status"], audit["severity"], audit["pact"]), (0, 0, 1))
            self.assertEqual(audit["text"] if isinstance(value, str) else float(audit["value"]), value)
            if record in ("AnalogSet", "EngineeringSet"):
                self.assertEqual(audit["raw"], wire)
            self.assertLessEqual(events[-2]["time"], audit["time"])
            self.assertLessEqual(audit["time"], events[-1]["time"])
            identity = dict(field.split("=", 1) for field in events[2]["extra"].split())
            matched = [r for r in proxy.records if r["event"] == "response" and r.get("pdu") == 0xA2 and
                       r.get("id") == int(identity["wire"]) and identity["oid"] in r.get("numeric_oids", [])]
            self.assertEqual(len(matched), 1)
            self.assertEqual(matched[0]["error"], 0)
            self.assertLessEqual(matched[0]["time"], events[-3]["time"])
        write_json(self.work / "acceptance.json", dict(generations=len(expected), audits=len(audits), passed=True))

    def test_v2c(self):
        self.success(False)

    def test_named_endpoint(self):
        self.success(True)

    def security(self, fault):
        agent, proxy, runtime = self.start(True, fault)
        started = time.monotonic()
        runtime.put("IntegerSet", 45)
        self.completion(runtime, "IntegerSet", 1, status=2)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(json.loads(agent.values_path.read_text())["values"]["6"], 600)
        failure_oid = ".1.3.6.1.6.3.15.1.1." + ("3" if fault == "user" else "5") + ".0"
        self.assertTrue(any(r["event"] == "response" and r.get("pdu") == 0xA8 and
                            failure_oid in r.get("numeric_oids", []) for r in proxy.records))
        self.verify(runtime, {("IntegerSet", 1): 2})

    def test_unknown_user(self):
        self.security("user")

    def test_wrong_key(self):
        self.security("key")

    def test_session_retirement(self):
        with self.scenario("retirement", fixture="request_set.db", writable=True, hold=True,
                           timeout_us=70000000, max_oids=20, extra=('devSnmpSetParam("RequestTimeoutMSec", 90000)',
                                                      'devSnmpSetParam("DebugLevel", 2)')) as s:
            started = time.monotonic()
            s.put("IntegerSet", 75)
            s.wait(lambda: len(s.peer.held) == 1, "SET held beyond retirement")
            s.wait(lambda: "deleted stale session" in (s.work / "ioc.log").read_text(),
                   "real sixty-second retirement", timeout=70)
            s.done("IntegerSet", 1, 75, severity=3, status=10)
            elapsed = time.monotonic() - started
            s.peer.release()
            s.peer.hold = False
            s.put("IntegerSet", 76)
            s.done("IntegerSet", 2, 76)
            write_json(s.work / "retirement.json", dict(elapsed_seconds=elapsed))
        self.assertGreaterEqual(elapsed, 60)
        self.assertLess(elapsed, 70)
