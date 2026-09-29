"""Observe FIFO admission on the shipped IOC/helper and external wire peer."""

import re
import time

from ioc import IOC, ROOT, settings, trace_evidence, write_json
from request_cases import Scenario, ScenarioTest
from snmp_peer import Peer, oid_bytes


CASES = ("fifo", "contiguous_batch", "legacy_replacement", "capacity_count", "capacity_bytes",
         "dynamic_capacity", "queue_size_validation", "expired_generation",
         "mixed_shutdown", "legacy_oid_failure")


class SchedulerTest(ScenarioTest):
    def setUp(self):
        super().setUp()
        self.assertTrue(settings().get("worker_helper"), "Scheduler qualification requires the actual helper")

    def test_legacy_oid_failure(self):
        peer = Peer(self.work)
        self.addCleanup(peer.close)
        host = f"127.0.0.1:{peer.server_address[1]}"
        directory = self.work / "ioc"
        directory.mkdir()
        runtime = IOC(directory, [
            'devSnmpSetParam("MaxOidCompFailures", 2)',
            'devSnmpSetParam("DataStaleTimeoutMSec", 500)',
            'devSnmpSetParam("SessionRetries", 0)',
            'devSnmpSetParam("SessionTimeout", 100000)',
            f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")',
            f'dbLoadRecords("{ROOT}/tests/legacy.db", "P=SNMPTEST:,HOST={host}")'], terminal=True)
        self.addCleanup(runtime.close)
        fields = ["Legacy", "Legacy.PACT", "Legacy.STAT", "Legacy.SEVR"]
        runtime.wait_for(lambda: runtime.get_many(fields) == dict(zip(fields, ("101", "0", "0", "0"))),
                         "valid legacy cache")
        observations = {"initial": runtime.get_many(fields)}
        peer.mode = "missing"
        first = len(peer.requests)
        runtime.wait_for(lambda: len(peer.requests) >= first + 5, "missing-variable replies")
        time.sleep(0.7)
        observations["missing"] = runtime.get_many(fields)
        self.assertEqual(observations["missing"], observations["initial"],
                         "Missing variables must not count as positional OID mismatches")
        peer.mode = "wrong_oid"
        first = len(peer.requests)
        runtime.wait_for(lambda: len(peer.requests) >= first + 5, "OID mismatch threshold exceeded")
        runtime.wait_for(lambda: runtime.get("Legacy.SEVR") == "3", "invalidated legacy cache")
        observations["wrong_oid"] = runtime.get_many(fields)
        self.assertEqual(observations["wrong_oid"]["Legacy"], "101")
        self.assertEqual(observations["wrong_oid"]["Legacy.STAT"], "13")
        peer.values[1] = 303
        peer.mode = "normal"
        runtime.wait_for(lambda: runtime.get_many(fields) == dict(zip(fields, ("303", "0", "0", "0"))),
                         "valid legacy recovery")
        observations["recovered"] = runtime.get_many(fields)
        runtime.close()
        self.assertEqual(peer.errors, [])
        write_json(self.work / "legacy-cache.json", observations)

    def blocked(self, scenario):
        first = len(scenario.peer.requests)
        scenario.peer.hold = True
        scenario.put("Block.PROC")
        scenario.wait(lambda: any(row["oids"] == [99] for row in scenario.peer.requests[first:]),
                      "actual blocking native transaction")
        return len(scenario.peer.requests)

    def release(self, scenario):
        scenario.peer.hold = False
        scenario.peer.release()
        scenario.done("Block", 1, 199)

    def test_fifo(self):
        with self.scenario("fifo", fixture="batch.db", writable=True,
                           overrides=("request_set.db",)) as s:
            first = self.blocked(s)
            s.put("R1.PROC")
            s.put("IntegerSet", 777)
            s.put("R2.PROC")
            self.assertEqual(len(s.peer.requests), first)
            self.release(s)
            s.done("R1", 1, 101)
            s.done("IntegerSet", 1, 777)
            s.done("R2", 1, 102)
            self.assertEqual([(r["pdu"], r["oids"]) for r in s.peer.requests[first:]],
                             [(0xA0, [1]), (0xA3, [6]), (0xA0, [2])])

    def test_contiguous_batch(self):
        with self.scenario("contiguous", fixture="batch.db", writable=True,
                           overrides=("request_set.db",)) as s:
            first = self.blocked(s)
            for record in ("R1", "R2"):
                s.put(record + ".PROC")
            s.put("IntegerSet", 778)
            s.put("R3.PROC")
            self.release(s)
            for number in (1, 2, 3):
                s.done("R" + str(number), 1, 100 + number)
            s.done("IntegerSet", 1, 778)
            self.assertEqual([(r["pdu"], r["oids"]) for r in s.peer.requests[first:]],
                             [(0xA0, [1, 2]), (0xA3, [6]), (0xA0, [3])])

    def test_legacy_replacement(self):
        with self.scenario("legacy-position", fixture="batch.db", writable=True,
                           overrides=("request_set.db", "request_set_shared.db")) as s:
            s.wait(lambda: s.get("LegacySet") == "111", "legacy startup readback")
            first = self.blocked(s)
            s.put("LegacySet", 700)
            s.put("R1.PROC")
            s.put("LegacySet", 701)
            s.put("IntegerSet", 779)
            s.put("R2.PROC")
            self.release(s)
            s.done("R1", 1, 101)
            s.done("IntegerSet", 1, 779)
            s.done("R2", 1, 102)
            relevant = [r for r in s.peer.requests[first:]
                        if r["pdu"] == 0xA3 or any(oid in (1, 2) for oid in r["oids"])]
            self.assertEqual([(r["pdu"], r["oids"]) for r in relevant],
                             [(0xA3, [11]), (0xA0, [1]), (0xA3, [6]), (0xA0, [2])])
            self.assertEqual(relevant[0]["sets"][0]["value"], 701)

    def test_capacity_count(self):
        self.capacity(False)

    def test_capacity_bytes(self):
        self.capacity(True)

    def capacity(self, byte_bound):
        limits = settings()["profile"]["limits"]
        # This shipped numeric OID and integer SET encode a 164-byte ticket.
        charge = 164
        limit = limits["queue_bytes_per_worker"] // charge if byte_bound else limits["pending_per_worker"]
        configured = limit + 1 if byte_bound else limit
        overflow = f"Q{limit}"
        peer = Peer(self.work, writable=True)
        self.addCleanup(peer.close)
        peer.values[6] = 600
        peer.names[oid_bytes((1, 3, 6, 1, 4, 1, 55555, 6, 0))] = 6
        peer.hold = True
        host = f"127.0.0.1:{peer.server_address[1]}"
        names = ["Block"] + [f"Q{i}" for i in range(limit + 1)]
        lines = [f'devSnmpSetParam("RequestTrace", {0 if byte_bound else 1})',
                 'devSnmpSetParam("SessionTimeout", 60000000)',
                 'devSnmpSetParam("SessionRetries", 0)',
                 'devSnmpSetParam("RequestTimeoutMSec", 30000)']
        if byte_bound:
            lines.append(f'devSnmpSetQueueSize("{host}", {configured})')
        lines += [f'dbLoadRecords("{ROOT}/tests/queue_record.db", "P=SNMPTEST:,R={name},HOST={host}")'
                  for name in names]
        directory = self.work / "ioc"
        directory.mkdir()
        runtime = IOC(directory, lines, terminal=True, startup_timeout=60 if byte_bound else None)
        self.addCleanup(runtime.close)
        runtime.put("Block", 900)
        runtime.wait_for(lambda: len(peer.held) == 1, "active native SET before queue admission")
        runtime.process.stdin.write("".join(f'dbpf("SNMPTEST:Q{i}", "{i + 1}")\n' for i in range(limit + 1)))
        runtime.process.stdin.flush()
        runtime.wait_for(lambda: runtime.get("Audit" + overflow) == "1", "overflow completion")
        self.assertEqual(runtime.get(overflow + ".SEVR"), "3")
        self.assertEqual(runtime.get(overflow + ".STAT"), "2")
        self.assertEqual(len(peer.requests), 1, "Queued work bypassed the active transaction")
        runtime.process.stdin.write("snmpr(0)\n")
        runtime.process.stdin.flush()
        pattern = rf"SNMPQUEUE epoch=\d+ count={limit} bytes=(\d+) high_count={limit} high_bytes=\d+ rejected=1"
        runtime.wait_for(lambda: re.search(pattern, (directory / "ioc.log").read_text()), "bounded queue counters")
        charged = int(re.search(pattern, (directory / "ioc.log").read_text()).group(1))
        self.assertEqual(charged, limit * charge)
        if byte_bound:
            self.assertLess(limit, configured, "Count must not explain byte rejection")
            self.assertLessEqual(charged, limits["queue_bytes_per_worker"])
            self.assertGreater(charged + charge, limits["queue_bytes_per_worker"])
        peer.hold = False
        peer.release()
        for offset in range(0, len(names), 256):
            batch = names[offset:offset + 256]
            runtime.wait_for(lambda: all(value == "1" for value in
                                        runtime.get_many(["Audit" + name for name in batch]).values()),
                             "all admitted records complete exactly once")
        self.assertEqual(len(peer.requests), limit + 1)
        self.assertEqual([row["sets"][0]["value"] for row in peer.requests], [900] + list(range(1, limit + 1)))
        self.assertEqual(len({row["id"] for row in peer.requests}), limit + 1)
        runtime.close()
        driver, audits = trace_evidence(directory)
        if not byte_bound:
            self.assertEqual(len([row for row in driver if row["event"] == "accepted"]), limit + 2)
            self.assertEqual(len([row for row in driver if row["event"] == "complete"]), limit + 2)
            self.assertEqual(len([row for row in driver if row["event"] == "admission_full"]), 1)
        self.assertEqual(len(audits), limit + 2)
        self.assertTrue(all(row["pact"] == 1 and row["count"] == 1 for row in audits))
        self.assertNotIn("overflow=1", (directory / "ioc.log").read_text())
        for audit in audits:
            rejected = audit["record"] == "SNMPTEST:Audit" + overflow
            self.assertEqual(audit["severity"], 3 if rejected else 0)
            self.assertEqual(audit["status"], 2 if rejected else 0)
        self.assertEqual(peer.errors, [])
        write_json(self.work / "capacity.json", {"pending_limit": configured, "pending_count": limit,
                   "charged_bytes": charged, "byte_bound": byte_bound, "rejected": 1,
                   "wire_transactions": len(peer.requests), "completions": len(audits)})

    def test_dynamic_capacity(self):
        peers = []
        hosts = []
        names = []
        rejected = {"AFull", "BFull", "AShrink", "BUnchanged", "AAbove", "AEqual"}
        lines = ['devSnmpSetParam("RequestTrace", 1)',
                 'devSnmpSetParam("SessionTimeout", 60000000)',
                 'devSnmpSetParam("SessionRetries", 0)',
                 'devSnmpSetParam("RequestTimeoutMSec", 30000)']
        for label, count, failures in (("A", 5, ("Full", "Shrink", "Above", "Equal")),
                                       ("B", 3, ("Full", "Unchanged"))):
            directory = self.work / label
            directory.mkdir()
            peer = Peer(directory, writable=True)
            self.addCleanup(peer.close)
            peer.values[6] = 600
            peer.names[oid_bytes((1, 3, 6, 1, 4, 1, 55555, 6, 0))] = 6
            peer.hold = True
            peers.append(peer)
            host = f"127.0.0.1:{peer.server_address[1]}"
            hosts.append(host)
            lines += [f'epicsEnvSet("QUEUE_{label}", "{2 if label == "A" else 3}")',
                      f'devSnmpSetQueueSize("{host}", $(QUEUE_{label}))']
            records = [label + "Block"] + [f"{label}{i}" for i in range(count)]
            records += [label + suffix for suffix in failures]
            names.extend(records)
            lines += [f'dbLoadRecords("{ROOT}/tests/queue_record.db", "P=SNMPTEST:,R={name},HOST={host}")'
                      for name in records]
        directory = self.work / "ioc"
        directory.mkdir()
        runtime = IOC(directory, lines, terminal=True)
        self.addCleanup(runtime.close)
        observations = []

        def command(text):
            runtime.process.stdin.write(text + "\n")
            runtime.process.stdin.flush()

        def snapshot(label, counts, limits):
            offset = len((directory / "ioc.log").read_text())
            command("snmpr(0)")
            pattern = r"SNMPQUEUE epoch=(\d+) count=(\d+) bytes=(\d+).* pending_limit=(\d+)"
            def rows():
                return re.findall(pattern, (directory / "ioc.log").read_text()[offset:])
            runtime.wait_for(lambda: len(rows()) == 2, "both configured-address queue reports")
            values = sorted(rows(), key=lambda row: int(row[0]))
            self.assertEqual([int(row[1]) for row in values], counts)
            self.assertEqual([int(row[3]) for row in values], limits)
            self.assertTrue(all(int(row[2]) == int(row[1]) * 164 for row in values))
            observations.append({"phase": label, "queues": values})

        def reject(name):
            runtime.put(name, 999)
            runtime.wait_for(lambda: runtime.get("Audit" + name) == "1", "rejected request completes")
            self.assertEqual(runtime.get(name + ".STAT"), "2")
            self.assertEqual(runtime.get(name + ".SEVR"), "3")

        for label, peer in zip(("A", "B"), peers):
            runtime.put(label + "Block", 900)
            runtime.wait_for(lambda: len(peer.held) == 1, "active native SET")
            for i in range(2 if label == "A" else 3):
                runtime.put(f"{label}{i}", i + (1 if label == "A" else 11))
            reject(label + "Full")
        snapshot("startup macros", [2, 3], [2, 3])
        command('epicsEnvSet("QUEUE_A", "4")')
        snapshot("environment alone does not resize", [2, 3], [2, 3])
        command(f'devSnmpSetQueueSize("{hosts[0]}", $(QUEUE_A))')
        for i in range(2, 4):
            runtime.put(f"A{i}", i + 1)
        reject("BUnchanged")
        snapshot("increase only affects addressed queue", [4, 3], [4, 3])
        command(f'devSnmpSetQueueSize("{hosts[0]}", 2)')
        reject("AShrink")
        snapshot("decrease retains queued tickets", [4, 3], [2, 3])
        self.assertTrue(all(len(peer.requests) == 1 for peer in peers))
        for value in (0, -1):
            command(f'devSnmpSetQueueSize("{hosts[0]}", {value})')
        command('devSnmpSetQueueSize("127.0.0.1:1", 2)')
        snapshot("invalid updates retain limit and tickets", [4, 3], [2, 3])
        self.assertEqual((directory / "ioc.log").read_text().count(
            "devSnmpSetQueueSize: queue size must be positive"), 2)
        self.assertIn("queue address has no configured worker", (directory / "ioc.log").read_text())
        for expected, denied in ((2, "AAbove"), (3, "AEqual"), (4, None)):
            peers[0].release()
            runtime.wait_for(lambda: len(peers[0].requests) == expected and len(peers[0].held) == 1,
                             "next original SET owns native transaction")
            if denied:
                reject(denied)
            else:
                runtime.put("A4", 5)
            snapshot(denied or "admit below reduced limit", [max(2, 5 - expected), 3], [2, 3])
        for peer in peers:
            peer.hold = False
            peer.release()
        runtime.wait_for(lambda: all(value == "1" for value in
                                    runtime.get_many(["Audit" + name for name in names]).values()),
                         "retained and rejected requests complete once")
        snapshot("drained", [0, 0], [2, 3])
        self.assertEqual([r["sets"][0]["value"] for r in peers[0].requests], [900, 1, 2, 3, 4, 5])
        self.assertEqual([r["sets"][0]["value"] for r in peers[1].requests], [900, 11, 12, 13])
        runtime.close()
        driver, audits = trace_evidence(directory)
        for event in ("accepted", "complete"):
            self.assertEqual(len([row for row in driver if row["event"] == event]), len(names))
        self.assertEqual(len([row for row in driver if row["event"] == "admission_full"]), len(rejected))
        self.assertEqual(len(audits), len(names))
        self.assertEqual({row["record"] for row in audits}, {"SNMPTEST:Audit" + name for name in names})
        for audit in audits:
            failed = audit["record"][len("SNMPTEST:Audit"):] in rejected
            self.assertEqual((audit["pact"], audit["count"], audit["severity"], audit["status"]),
                             (1, 1, 3 if failed else 0, 2 if failed else 0))
        self.assertTrue(all(not peer.errors for peer in peers))
        self.assertNotIn("overflow=1", (directory / "ioc.log").read_text())
        write_json(self.work / "dynamic-capacity.json", observations)

    def test_queue_size_validation(self):
        peer = Peer(self.work)
        self.addCleanup(peer.close)
        host = f"127.0.0.1:{peer.server_address[1]}"
        directory = self.work / "ioc"
        directory.mkdir()
        runtime = IOC(directory, [
            'devSnmpSetQueueSize("", 2)',
            'devSnmpSetQueueSize("bad address", 2)',
            f'devSnmpSetQueueSize("{host}", 0)',
            f'devSnmpSetQueueSize("{host}", -1)',
            f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_2c")',
            f'dbLoadRecords("{ROOT}/tests/batch.db", "P=SNMPTEST:,HOST={host},HOST_B={host}")'],
            terminal=True)
        self.addCleanup(runtime.close)
        runtime.put("R1.PROC", 1)
        runtime.wait_for(lambda: runtime.get("AuditR1") == "1", "real read completes")
        self.assertEqual(runtime.get("R1"), "101")
        self.assertEqual(runtime.get("R1.SEVR"), "0")
        runtime.process.stdin.write("snmpr(0)\n")
        runtime.process.stdin.flush()
        runtime.wait_for(lambda: "pending_limit=1024" in (directory / "ioc.log").read_text(),
                         "invalid startup values retain default")
        log = (directory / "ioc.log").read_text()
        self.assertEqual(log.count("devSnmpSetQueueSize: queue size must be positive"), 2)
        self.assertEqual(log.count("devSnmpSetQueueSize: queue address must contain"), 2)
        self.assertEqual(peer.errors, [])

    def test_expired_generation(self):
        with self.scenario("expired", fixture="batch.db", timeout_us=4000000,
                           extra=('devSnmpSetParam("RequestTimeoutMSec", 400)',)) as s:
            s.put("Block.PROC")
            s.done("Block", 1, 199)
            s.put("R1.PROC")
            s.done("R1", 1, 101)
            self.blocked(s)
            s.put("R1.PROC")
            s.done("Block", 2, 199, severity=3, status=10)
            s.done("R1", 2, 101, severity=3, status=10, failure="queued")
            self.assertEqual([r["oids"] for r in s.peer.requests], [[99], [1], [99]])
            s.peer.values[1] = 301
            s.put("R1.PROC")
            s.peer.hold = False
            s.peer.release()
            s.done("R1", 3, 301)
            self.assertEqual([r["oids"] for r in s.peer.requests], [[99], [1], [99], [1]])
            self.assertEqual(s.get("AuditBlock"), "2", "Late response repeated FLNK")

    def test_mixed_shutdown(self):
        observations = []
        for cycle in range(20):
            mode = "explicit" if cycle % 2 else "eof"
            s = Scenario(self, f"shutdown-{cycle}", fixture="batch.db", writable=True,
                         timeout_us=4000000, ioc_options={"terminal": True},
                         overrides=("request_set.db", "request_set_shared.db"))
            try:
                s.wait(lambda: s.get("LegacySet") == "111", "legacy startup before mixed shutdown")
                first = self.blocked(s)
                s.put("R1.PROC")
                s.put("IntegerSet", 800)
                s.put("LegacySet", 801)
                s.runtime.close(mode=mode)
                driver, audits = trace_evidence(s.work)
                self.assertEqual(len(s.peer.requests), first, "Shutdown transmitted queued work")
                self.assertEqual(audits, [], "Shutdown fabricated a completion FLNK")
                self.assertEqual(sum(row["event"] == "accepted" for row in driver), 3)
                self.assertNotIn("SNMPAUDIT_ERROR", (s.work / "ioc.log").read_text())
                observations.append({"cycle": cycle, "mode": mode, "accepted": 3,
                                     "flnk": 0, "exit_code": s.runtime.process.returncode})
            finally:
                s.close(verify=False)
        write_json(self.work / "shutdown.json", observations)
