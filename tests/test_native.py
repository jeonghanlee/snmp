"""Exercise the module's native Single Session adapter against real agents."""

import json
from pathlib import Path
import resource
import subprocess
import tempfile
import time
import unittest

from ioc import IOC, settings, write_json
from snmp_agent import AUTH, CONTACT, NAME, PRIV, USERS, Agent, Proxy
from socket_fault import SocketFault


CASES = ("response_v2c", "response_v3", "concurrent_requests", "request_loss_retries_0",
         "request_loss_retries_1", "request_loss_retries_3", "reply_loss", "close_with_pending",
         "open_failure", "send_failure", "security_error_unknown_user", "security_error_wrong_key",
         "reissue_from_completion", "agent_restart", "report_foreign_id", "resend_send_failure", "mixed_deadlines",
         "failed_and_healthy", "high_descriptor")
SHORT_TIMEOUT_US = 200000
LONG_TIMEOUT_US = 1000000
TIMING_TOLERANCE_MS = 150
CONCURRENT_REQUESTS = 20
DESCRIPTOR_FLOOR = 1100
OVERSIZED_REPEAT = 6000
FAILED_SENDS = 20
FAILED_SEND_RSS_LIMIT_KIB = 20000
WRONG_AUTH = "wrong-auth-test-only"
RESTART_GAP_MS = 3000
RESTART_BOOTS = 6
NOT_IN_TIME_WINDOW = ".1.3.6.1.6.3.15.1.1.2.0"
RESEND_TIMEOUT_US = 1500000
GET = 0xA0
VALUE = b"fixture-agent"


class NativeTest(unittest.TestCase):
    def setUp(self):
        self.config = settings()
        self.profile = self.config["profile"]
        self.work = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=self.config.get("output")))
        print(f"Evidence: {self.work}", flush=True)
        self.agent = Agent(self.work, self.profile)
        self.addCleanup(self.agent.close)
        self.proxy = Proxy(self.work, self.agent.port)
        self.addCleanup(self.proxy.close)
        self.proxied = f"127.0.0.1:{self.proxy.port}"
        self.direct = f"127.0.0.1:{self.agent.port}"
        (self.work / "ioc").mkdir()
        environment = None
        if self._testMethodName == "test_resend_send_failure":
            self.fault = SocketFault(self.work)
            environment = self.fault.environment(self.proxy.port)
        self.runtime = IOC(self.work / "ioc", ['devSnmpSetParam("SessionTimeout", 1000000)'],
                           process_env=environment)
        self.addCleanup(self.runtime.close)

    def command(self, line, label, during=None):
        self.runtime.process.stdin.write(line + "\n")
        self.runtime.process.stdin.flush()
        if during:
            self.runtime.wait_for(lambda: any(e["event"] == "gap" for e in self.events(label)),
                                  "native probe pause", timeout=60)
            during()
        self.runtime.wait_for(lambda: any(e["event"] in ("summary", "invalid_arguments")
                                          for e in self.events(label)), "native probe summary", timeout=60)
        events = self.events(label)
        write_json(self.work / f"events-{label}.json", events)
        self.assertNotIn("invalid_arguments", [e["event"] for e in events])
        return events

    def events(self, label):
        found = []
        for line in (self.work / "ioc" / "ioc.log").read_text().splitlines():
            if line.startswith("SNMPNATIVE {"):
                event = json.loads(line[len("SNMPNATIVE "):])
                if event.get("label") == label:
                    found.append(event)
        return found

    def probe(self, label, peer, user="-", timeout_us=LONG_TIMEOUT_US, retries=0, oids=NAME, requests=1,
              close_after_ms=-1, floor=0, repeat=1, action="none", auth=AUTH, during=None):
        return self.command(f'nativeProbe("{label}", "{peer}", "{user}", "{auth}", "{PRIV}", {timeout_us}, '
                            f'{retries}, "{oids}", {requests}, {close_after_ms}, {floor}, {repeat}, '
                            f'"{action}")', label, during)

    def mixed(self, label, first, first_timeout_us, second, second_timeout_us, retries=0):
        return self.command(f'nativeProbeMixed("{label}", "{first}", {first_timeout_us}, "{second}", '
                            f'{second_timeout_us}, {retries}, "{NAME}")', label)

    def summary(self, events, accepted):
        summaries = [e for e in events if e["event"] == "summary"]
        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertEqual(summary["accepted"], accepted)
        self.assertEqual(summary["completed_transactions"], accepted, "Every accepted request completes")
        self.assertEqual(summary["delivered"], accepted, "Exactly one completion per request")
        self.assertEqual(summary["duplicates"], 0)
        self.assertEqual(summary["pending"], 0)
        self.assertEqual(summary["adapter_completions"], accepted)
        return summary

    def completions(self, events):
        return [e for e in events if e["event"] == "completion"]

    def requests(self, pdu=GET):
        return [r for r in self.proxy.records if r["event"] == "request" and r.get("pdu") == pdu]

    def assert_value(self, completion, count=1):
        self.assertEqual(completion["outcome"], "response")
        self.assertEqual(completion["error_status"], 0)
        self.assertEqual(len(completion["values"]), count)
        for value in completion["values"]:
            self.assertTrue(value["valid"], completion)
        self.assertIn(VALUE, bytes.fromhex(completion["values"][0]["text"]))

    def native_client_requests(self, retries):
        before = len(self.requests())
        result = subprocess.run(["snmpget", "-v", "2c", "-c", "public", "-t", str(SHORT_TIMEOUT_US / 1e6),
                                 "-r", str(retries), "-On", self.proxied, NAME], env=self.agent.env,
                                text=True, capture_output=True, timeout=10)
        write_json(self.work / f"snmpget-retries-{retries}.json",
                   {"exit_code": result.returncode, "out": result.stdout, "err": result.stderr})
        self.assertNotEqual(result.returncode, 0, "The native client must also time out")
        time.sleep(0.2)
        return self.requests()[before:]

    def test_response_v2c(self):
        events = self.probe("v2c", self.proxied, oids=f"{NAME},{CONTACT}")
        self.summary(events, 1)
        completion, = self.completions(events)
        self.assert_value(completion, 2)
        self.assertEqual(completion["resends"], 0)
        self.assertEqual(len(self.requests()), 1)

    def test_response_v3(self):
        events = self.probe("v3", self.proxied, user=USERS["authPriv"])
        self.summary(events, 1)
        completion, = self.completions(events)
        self.assert_value(completion)
        packets = [r for r in self.proxy.records if r["event"] == "request"]
        self.assertTrue(all(p["version"] == 3 for p in packets))
        self.assertGreaterEqual(len(packets), 2, "Library discovery precedes the authenticated GET")

    def test_concurrent_requests(self):
        events = self.probe("concurrent", self.proxied, requests=CONCURRENT_REQUESTS)
        self.summary(events, CONCURRENT_REQUESTS)
        completions = self.completions(events)
        for completion in completions:
            self.assert_value(completion)
        self.assertEqual(len({c["transaction"] for c in completions}), CONCURRENT_REQUESTS)
        self.assertEqual(len({r["id"] for r in self.requests()}), CONCURRENT_REQUESTS)

    def request_loss(self, retries):
        self.proxy.fault("drop-requests")
        events = self.probe(f"loss-{retries}", self.proxied, timeout_us=SHORT_TIMEOUT_US, retries=retries)
        self.summary(events, 1)
        completion, = self.completions(events)
        self.assertEqual(completion["outcome"], "timeout")
        self.assertEqual(completion["resends"], retries, "One RESEND callback per library retransmission")
        adapter = self.requests()
        self.assertEqual(len(adapter), retries + 1, "Only library retransmissions reach the wire")
        self.assertEqual(len({r["id"] for r in adapter}), 1, "Retransmissions reuse the request ID")
        expected = (retries + 1) * SHORT_TIMEOUT_US / 1000
        self.assertLess(abs(completion["elapsed_ms"] - expected), TIMING_TOLERANCE_MS + 60, completion)
        native = self.native_client_requests(retries)
        self.assertEqual(len(native), len(adapter), "Adapter and snmpget send the same attempts")
        write_json(self.work / "retry-comparison.json", {"retries": retries, "adapter_packets": len(adapter),
                   "snmpget_packets": len(native), "resend_callbacks": completion["resends"],
                   "elapsed_ms": completion["elapsed_ms"], "expected_ms": expected})

    def test_request_loss_retries_0(self):
        self.request_loss(0)

    def test_request_loss_retries_1(self):
        self.request_loss(1)

    def test_request_loss_retries_3(self):
        self.request_loss(3)

    def test_reply_loss(self):
        self.proxy.fault("drop-replies")
        events = self.probe("reply-loss", self.proxied, timeout_us=SHORT_TIMEOUT_US, retries=1)
        self.summary(events, 1)
        completion, = self.completions(events)
        self.assertEqual(completion["outcome"], "timeout")
        self.assertEqual(completion["resends"], 1)
        self.assertEqual(len(self.requests()), 2)
        dropped = [r for r in self.proxy.records if r["event"] == "response" and r["action"] == "drop"]
        self.assertEqual(len(dropped), 2, "The agent answered both attempts")

    def test_close_with_pending(self):
        self.proxy.fault("hold-requests")
        events = self.probe("close", self.proxied, requests=3, close_after_ms=300)
        summary = self.summary(events, 3)
        self.assertEqual(summary["stop"], "closed_with_pending")
        completions = self.completions(events)
        for completion in completions:
            self.assertEqual(completion["outcome"], "closed")
        write_json(self.work / "close-delivery.json", {
            "library_callbacks_while_closing": sum(c["session_open"] for c in completions),
            "adapter_sweep": sum(not c["session_open"] for c in completions)})
        self.proxy.release()
        time.sleep(1.0)
        self.assertIsNone(self.runtime.process.poll(), "Late replies to a closed session are harmless")
        released = [r for r in self.proxy.records if r["event"] == "release"]
        self.assertEqual(len(released), 3)

    def test_open_failure(self):
        events = self.probe("open-failure", "udp:invalid-host.invalid:161")
        opened, = [e for e in events if e["event"] == "open"]
        self.assertFalse(opened["success"])
        self.assertTrue(opened["error"])
        self.summary(events, 0)
        self.assertEqual(self.completions(events), [])

    def test_send_failure(self):
        events = self.probe("send-failure", self.proxied, requests=FAILED_SENDS, repeat=OVERSIZED_REPEAT)
        sends = [e for e in events if e["event"] == "send"]
        self.assertEqual(len(sends), FAILED_SENDS)
        for send in sends:
            self.assertFalse(send["sent"], send)
            self.assertTrue(send["error"])
        summary = self.summary(events, 0)
        self.assertEqual(self.completions(events), [], "A rejected request has no completion")
        self.assertEqual(self.requests(), [], "Nothing reached the wire")
        opened, = [e for e in events if e["event"] == "open"]
        growth = summary["rss_kib"] - opened["rss_kib"]
        write_json(self.work / "send-failure-memory.json", {"sends": FAILED_SENDS, "repeat": OVERSIZED_REPEAT,
                   "rss_before_kib": opened["rss_kib"], "rss_after_kib": summary["rss_kib"], "growth_kib": growth})
        self.assertLess(growth, FAILED_SEND_RSS_LIMIT_KIB, "Rejected PDUs are released")

    def security_error(self, label, user, auth):
        events = self.probe(label, self.proxied, user=user, auth=auth)
        self.summary(events, 1)
        completion, = self.completions(events)
        self.assertEqual(completion["outcome"], "security_error")
        reports = [r for r in self.proxy.records if r["event"] == "response" and r.get("pdu") == 0xA8]
        self.assertGreaterEqual(len(reports), 2, "The agent reported the USM failure")
        time.sleep(0.5)
        self.assertIsNone(self.runtime.process.poll())

    def test_security_error_unknown_user(self):
        self.security_error("unknown-user", "nosuchuser", AUTH)

    def test_security_error_wrong_key(self):
        self.security_error("wrong-key", USERS["authPriv"], WRONG_AUTH)

    def test_reissue_from_completion(self):
        events = self.probe("reissue", self.proxied, action="reissue")
        reissue, = [e for e in events if e["event"] == "reissue"]
        self.assertTrue(reissue["sent"], reissue)
        self.summary(events, 2)
        completions = self.completions(events)
        self.assertEqual([c["transaction"] for c in completions], [reissue["from"], reissue["transaction"]])
        for completion in completions:
            self.assert_value(completion)
        self.assertEqual(len(self.requests()), 2)

    def test_agent_restart(self):
        def restart():
            engine, = {r["engine_id"] for r in self.proxy.records if r["event"] == "response" and r.get("engine_id")}
            self.restarted_at = len(self.proxy.records)
            self.agent.restart(engine, RESTART_BOOTS)
        events = self.probe("restart", self.proxied, user=USERS["authPriv"], retries=2, requests=2,
                            action=f"gap:{RESTART_GAP_MS}", during=restart)
        self.summary(events, 2)
        completions = self.completions(events)
        for completion in completions:
            self.assert_value(completion)
        after = self.proxy.records[self.restarted_at:]
        reports = [r for r in after if r["event"] == "response" and r.get("pdu") == 0xA8]
        self.assertTrue(any(NOT_IN_TIME_WINDOW in r.get("numeric_oids", []) for r in reports),
                        "The restarted agent reported notInTimeWindow before the library recovered")
        self.assertGreater(max(r.get("boots", 0) for r in after if r["event"] == "response"), RESTART_BOOTS - 1)
        write_json(self.work / "restart-recovery.json", {"second_resends": completions[1]["resends"],
                   "reports_after_restart": len(reports)})

    def test_report_foreign_id(self):
        self.proxy.fault("report-foreign-id")
        events = self.probe("foreign-id", self.proxied, user=USERS["authPriv"], auth=WRONG_AUTH)
        summary = self.summary(events, 1)
        self.assertEqual(summary["stop"], "drained", "The request completed before close")
        completion, = self.completions(events)
        self.assertEqual(completion["outcome"], "security_error")
        self.assertTrue(any(r["action"] == "forward-foreign-id" for r in self.proxy.records))

    def test_resend_send_failure(self):
        def fail_retransmission():
            before = len(self.proxy.records)
            self.proxy.fault("drop-requests")
            deadline = time.monotonic() + RESTART_GAP_MS / 1000 + 5
            while not [r for r in self.proxy.records[before:] if r["event"] == "request" and r["action"] == "drop"]:
                self.assertLess(time.monotonic(), deadline, "The second request's first attempt was not observed")
                time.sleep(0.005)
            self.fault.arm("send")
        events = self.probe("resend-failure", self.proxied, user=USERS["authPriv"], timeout_us=RESEND_TIMEOUT_US,
                            retries=1, requests=2, action=f"gap:{RESTART_GAP_MS}", during=fail_retransmission)
        summary = self.summary(events, 2)
        self.assertEqual(summary["stop"], "drained", "The failed retransmission completed before close")
        first, second = self.completions(events)
        self.assert_value(first)
        self.assertEqual(second["outcome"], "send_failed", second)
        faults = self.fault.events()
        self.assertEqual(len(faults), 1, faults)
        self.assertIn(faults[0]["operation"], ("sendto", "sendmsg"), "The retransmission send failed at libc")
        dropped = [r for r in self.proxy.records if r["event"] == "request" and r["action"] == "drop"]
        self.assertEqual(len(dropped), 1, "Only the first attempt reached the wire")

    def test_mixed_deadlines(self):
        self.proxy.fault("drop-requests")
        events = self.mixed("mixed", self.proxied, SHORT_TIMEOUT_US, self.proxied, LONG_TIMEOUT_US)
        start, = [e for e in events if e["event"] == "mixed_start"]
        self.assertEqual(start["accepted"], 2)
        self.summary(events, 2)
        by_transaction = {c["transaction"]: c for c in self.completions(events)}
        short, long_ = by_transaction[start["first"]], by_transaction[start["second"]]
        self.assertEqual((short["outcome"], long_["outcome"]), ("timeout", "timeout"))
        self.assertLess(abs(short["elapsed_ms"] - SHORT_TIMEOUT_US / 1000), TIMING_TOLERANCE_MS, short)
        self.assertLess(abs(long_["elapsed_ms"] - LONG_TIMEOUT_US / 1000), TIMING_TOLERANCE_MS, long_)

    def test_failed_and_healthy(self):
        self.proxy.fault("drop-requests")
        events = self.mixed("failed-healthy", self.proxied, LONG_TIMEOUT_US, self.direct, LONG_TIMEOUT_US,
                            retries=2)
        start, = [e for e in events if e["event"] == "mixed_start"]
        self.summary(events, 2)
        by_transaction = {c["transaction"]: c for c in self.completions(events)}
        failed, healthy = by_transaction[start["first"]], by_transaction[start["second"]]
        self.assertEqual(failed["outcome"], "timeout")
        self.assert_value(healthy)
        self.assertLess(healthy["elapsed_ms"], 500, "A silent endpoint does not delay a healthy one")
        self.assertGreater(failed["elapsed_ms"], 3 * LONG_TIMEOUT_US / 1000 - TIMING_TOLERANCE_MS)

    def test_high_descriptor(self):
        soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        self.assertGreater(soft, DESCRIPTOR_FLOOR + 100, "Raise the descriptor limit for this case")
        events = self.probe("high-fd", self.proxied, floor=DESCRIPTOR_FLOOR)
        opened, = [e for e in events if e["event"] == "open"]
        self.assertTrue(opened["success"])
        self.assertTrue(opened["occupied"], "Every descriptor below the floor was occupied at open")
        self.assertGreaterEqual(opened["highest_socket"], DESCRIPTOR_FLOOR, "The session socket is above FD_SETSIZE")
        self.summary(events, 1)
        completion, = self.completions(events)
        self.assert_value(completion)
