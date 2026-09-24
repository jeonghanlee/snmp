"""Observe shipped output support against writable native snmpd and UDP faults."""

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
import tempfile
import time
import unittest

from ioc import IOC, ROOT, settings, write_json
from snmp_agent import Agent, Proxy


CASES = ("success", "agent_error", "queued_coalescing", "readback_suppression",
         "request_loss_zero", "request_loss_one", "request_loss_three", "request_loss_defaults",
         "reply_loss_zero", "reply_loss_one", "reply_loss_three", "reply_loss_defaults")
OUTPUTS = (("AnalogSet", "AnalogRead", 5, 25.5, 255, 2),
           ("IntegerSet", "IntegerRead", 6, -77, -77, 2),
           ("TextSet", "TextRead", 7, "applied", "applied", 4))
SHORT_TIMEOUT_US = 200000
QUEUE_TIMEOUT_US = 4000000
SKIP_READBACK_MS = 1000


class LegacySetTest(unittest.TestCase):
    def setUp(self):
        self.config = settings()
        self.work = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=self.config.get("output")))
        print(f"Evidence: {self.work}", flush=True)
        self.agent = Agent(self.work, self.config["profile"], writable=True)
        self.addCleanup(self.agent.close)
        self.proxy = Proxy(self.work, self.agent.port)
        self.addCleanup(self.proxy.close)
        host = f"127.0.0.1:{self.proxy.port}"
        self.host = host
        suffix = self._testMethodName.rsplit("_", 1)[-1]
        self.retries = {"zero": 0, "one": 1, "three": 3, "defaults": 5}.get(suffix, 0)
        self.timeout_us = 10000000 if suffix == "defaults" else SHORT_TIMEOUT_US
        if self._testMethodName == "test_queued_coalescing":
            self.timeout_us = QUEUE_TIMEOUT_US
        lines = ['devSnmpSetParam("DebugLevel", 2)',
                 'devSnmpSetParam("PassivePollMSec", 100)',
                 'devSnmpSetParam("DataStaleTimeoutMSec", 500)',
                 f'devSnmpSetParam("SetSkipReadbackMSec", {SKIP_READBACK_MS})',
                 f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")']
        if suffix != "defaults":
            lines += [f'devSnmpSetParam("SessionTimeout", {self.timeout_us})',
                      f'devSnmpSetParam("SessionRetries", {self.retries})']
        lines.append(f'dbLoadRecords("{ROOT}/tests/legacy_set.db", "P=SNMPTEST:,HOST={host}")')
        runtime_dir = self.work / "ioc"
        runtime_dir.mkdir()
        self.runtime = IOC(runtime_dir, lines)
        self.addCleanup(self.runtime.close)
        self.samples = []
        self.oracle_index = 0
        self.runtime.wait_for(lambda: self.runtime.get("AnalogSet") == "50" and
                              self.runtime.get("IntegerSet") == "600" and
                              self.runtime.get("TextSet") == r'\"initial\"', "native startup readback")
        self.assertEqual(self.sets(), [], "Startup or readback emitted a SET")
        write_json(self.work / "policy.json", {"timeout_us": self.timeout_us, "retries": self.retries,
                   "overrides_omitted": suffix == "defaults", "skip_readback_ms": SKIP_READBACK_MS})

    def sets(self):
        return [row for row in self.proxy.records if row["event"] == "request" and row.get("pdu") == 0xA3]

    def state(self):
        return json.loads(self.agent.values_path.read_text())

    def change_state(self, values=None, reject=False):
        state = self.state()
        state["reject_set"] = reject
        if values:
            state["values"].update({str(key): value for key, value in values.items()})
        temporary = self.agent.values_path.with_suffix(".external")
        write_json(temporary, state)
        temporary.replace(self.agent.values_path)

    def snapshot(self, label):
        names = [name + field for name, _, *_ in OUTPUTS for field in ("", ".PACT", ".UDF", ".STAT", ".SEVR")]
        values = self.runtime.get_many(names)
        self.samples.append({"time": time.monotonic_ns(), "label": label, "records": values})
        write_json(self.work / "record-samples.json", self.samples)
        return values

    def oracle(self, key, expected):
        result = self.agent.client("2c", None, f".1.3.6.1.4.1.55555.{key}.0")
        self.oracle_index += 1
        write_json(self.work / f"oracle-{self.oracle_index:04}.json", {"time": time.monotonic_ns(),
                   "key": key, "exit_code": result.returncode, "out": result.stdout, "err": result.stderr})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().endswith(": " + (json.dumps(expected) if isinstance(expected, str) else str(expected))),
                        result.stdout)

    def stable(self, output, readback, value, raw):
        expected = str(value) if not isinstance(raw, str) else '\\"' + raw + '\\"'
        def matching():
            values = self.runtime.get_many([output, readback, output + ".SEVR"])
            if values[output + ".SEVR"] != "0":
                return False
            if isinstance(raw, str):
                return values[output] == expected and values[readback] == expected
            try:
                return Decimal(values[output]) == Decimal(expected) == Decimal(values[readback])
            except InvalidOperation:
                return False
        self.runtime.wait_for(matching, "output and independent shared-OID readback")

    def test_success(self):
        for output, readback, key, value, raw, kind in OUTPUTS:
            self.snapshot("before-" + output)
            first = len(self.sets())
            self.runtime.put(output, value)
            self.snapshot("command-return-" + output)
            self.runtime.wait_for(lambda: self.state()["values"][str(key)] == raw, "real snmpd SET application")
            self.oracle(key, raw)
            self.stable(output, readback, value, raw)
            writes = self.sets()[first:]
            self.assertEqual(len(writes), 1)
            self.assertEqual(writes[0]["varbinds"], [{"oid": f".1.3.6.1.4.1.55555.{key}.0", "type": kind, "value": raw}])
            self.snapshot("readback-" + output)
        self.assertEqual(len(self.sets()), len(OUTPUTS))

    def test_agent_error(self):
        initial = self.state()["values"]
        self.change_state(reject=True)
        for output, _, key, value, _, _ in OUTPUTS:
            first = len(self.proxy.records)
            self.runtime.put(output, value)
            self.runtime.wait_for(lambda: any(row["event"] == "response" and row.get("error", 0) != 0
                                              for row in self.proxy.records[first:]), "native error response")
            self.assertEqual(self.state()["values"], initial)
            self.oracle(key, initial[str(key)])
            self.snapshot("agent-error-" + output)
        self.change_state()
        self.runtime.wait_for(lambda: self.runtime.get("AnalogSet") == "50" and
                              self.runtime.get("IntegerSet") == "600" and
                              self.runtime.get("TextSet") == r'\"initial\"', "readback after rejected writes")
        self.assertEqual(len(self.sets()), len(OUTPUTS), "Agent error caused module replay")

    def loss(self, mode):
        results = []
        for output, readback, key, value, raw, kind in OUTPUTS:
            initial = self.state()["values"][str(key)]
            first = len(self.sets())
            offset = (self.runtime.work / "ioc.log").stat().st_size
            self.proxy.fault(mode, 0xA3)
            start = time.monotonic_ns()
            self.runtime.put(output, value)
            self.snapshot("command-return-" + output)
            deadline = time.monotonic() + self.timeout_us * (self.retries + 1) / 1e6 + 10
            observed = None
            terminal = None
            previous = time.monotonic_ns()
            while time.monotonic() < deadline:
                self.snapshot("waiting-" + output)
                poll_started = time.monotonic_ns()
                log = (self.runtime.work / "ioc.log").read_text()[offset:]
                if f"SET .1.3.6.1.4.1.55555.{key}.0 failed : op=" in log:
                    observed = time.monotonic_ns()
                    terminal = "native-timeout-callback"
                    break
                if f"*** devSnmp: {self.host} deleted stale session" in log:
                    observed = time.monotonic_ns()
                    terminal = "module-stale-session-retirement"
                    break
                previous = poll_started
                time.sleep(0.1)
            self.assertIsNotNone(observed, "No actual legacy SET termination observed")
            if terminal == "module-stale-session-retirement":
                self.assertEqual(self.timeout_us, 10000000)
                self.assertEqual(self.retries, 5)
            writes = self.sets()[first:]
            self.assertEqual(len(writes), self.retries + 1, "Wire retry count differs from native policy")
            self.assertEqual(len({row["id"] for row in writes}), 1, "Module generated another SET transaction")
            for row in writes:
                self.assertEqual(row["varbinds"], [{"oid": f".1.3.6.1.4.1.55555.{key}.0", "type": kind, "value": raw}])
            expected = initial if mode == "drop-requests" else raw
            self.oracle(key, expected)
            self.proxy.fault("normal")
            expected_value = expected / 10 if key == 5 else expected
            self.stable(output, readback, expected_value, expected)
            self.snapshot("recovered-without-command-" + output)
            time.sleep(0.4)
            self.assertEqual(len(self.sets()) - first, self.retries + 1, "SET replayed after exhausted native retries")
            continuation = [row["time"] for row in self.proxy.records if row["event"] == "request" and
                            row.get("pdu") == 0xA0 and row["time"] > writes[-1]["time"]]
            self.assertTrue(continuation, "No actual GET continuation after the SET")
            results.append({"output": output, "mode": mode, "command_ns": start,
                            "previous_log_read_ns": previous, "terminal_log_observed_ns": observed,
                            "last_set_sent_ns": writes[-1]["time"], "transport_resumed_ns": min(continuation),
                            "terminal_kind": terminal,
                            "packets": len(writes), "request_id": writes[0]["id"], "agent_value": expected})
            write_json(self.work / "loss-observations.json", results)

    def test_request_loss_zero(self):
        self.loss("drop-requests")

    def test_request_loss_one(self):
        self.loss("drop-requests")

    def test_request_loss_three(self):
        self.loss("drop-requests")

    def test_request_loss_defaults(self):
        self.loss("drop-requests")

    def test_reply_loss_zero(self):
        self.loss("drop-replies")

    def test_reply_loss_one(self):
        self.loss("drop-replies")

    def test_reply_loss_three(self):
        self.loss("drop-replies")

    def test_reply_loss_defaults(self):
        self.loss("drop-replies")

    def test_queued_coalescing(self):
        self.proxy.fault("hold-requests", 0xA0)
        self.runtime.wait_for(lambda: bool(self.proxy.held), "real GET held outside snmpd")
        for value in (11.1, 22.2, 33.3):
            self.runtime.put("AnalogSet", value)
        self.runtime.put("IntegerSet", 444)
        self.runtime.put("TextSet", "queued")
        self.snapshot("writes-behind-held-get")
        self.assertEqual(self.sets(), [], "GET stopped blocking before every command was queued")
        self.proxy.fault("normal")
        self.proxy.release()
        self.runtime.wait_for(lambda: self.state()["values"] == {"5": 333, "6": 444, "7": "queued"},
                              "last queued command for every writable OID")
        for output, readback, key, value, raw in (("AnalogSet", "AnalogRead", 5, 33.3, 333),
                                                ("IntegerSet", "IntegerRead", 6, 444, 444),
                                                ("TextSet", "TextRead", 7, "queued", "queued")):
            self.oracle(key, raw)
            self.stable(output, readback, value, raw)
        writes = [item for row in self.sets() for item in row["varbinds"]]
        write_json(self.work / "queued-order.json", writes)
        self.assertEqual([(row["oid"], row["value"]) for row in writes],
                         [(".1.3.6.1.4.1.55555.5.0", 333), (".1.3.6.1.4.1.55555.6.0", 444),
                          (".1.3.6.1.4.1.55555.7.0", "queued")])
        releases = [row["time"] for row in self.proxy.records if row["event"] == "release"]
        self.assertEqual(len(releases), 1)
        self.assertLess(releases[0], self.sets()[0]["time"])

    def test_readback_suppression(self):
        start = time.monotonic_ns()
        self.runtime.put("AnalogSet", 25.5)
        self.runtime.wait_for(lambda: self.state()["values"]["5"] == 255, "native analog SET")
        self.change_state({5: 777})
        self.runtime.wait_for(lambda: self.runtime.get("AnalogRead") == "77.7", "independent shared-OID change")
        sample = self.snapshot("before-readback-suppression-expiry")
        self.assertLess(time.monotonic_ns() - start, SKIP_READBACK_MS * 1000000)
        self.assertEqual(sample["AnalogSet"], "25.5")
        self.runtime.wait_for(lambda: self.runtime.get("AnalogSet") == "77.7", "output readback suppression expiry")
        self.snapshot("after-readback-suppression-expiry")
        self.oracle(5, 777)
        self.assertEqual(len(self.sets()), 1, "Readback change echoed a SET")
