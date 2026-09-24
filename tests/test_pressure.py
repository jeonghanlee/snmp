"""Sustain real Base callback contention and observe owned IOC resources."""

from pathlib import Path
import os
import re
import time

from diagnostics import sample, verify as verify_diagnostics
from ioc import write_json
from request_cases import ScenarioTest


CASES = ("callback_queue_sixty_seconds",)
PRESSURE_SECONDS = 60.0
SAMPLE_SECONDS = 1.0
RSS_ALLOWANCE_KIB = 4096
FD_STABLE_NS = 100000000


def resources(runtime):
    proc = Path("/proc") / str(runtime.process.pid)
    status = (proc / "status").read_text()
    fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
    descriptors = {}
    for descriptor in (proc / "fd").iterdir():
        try:
            descriptors[descriptor.name] = os.readlink(descriptor)
        except FileNotFoundError:
            descriptors[descriptor.name] = "closed during observation"
    return {"time": time.monotonic_ns(), "pid": runtime.process.pid,
            "user_ticks": int(fields[11]), "system_ticks": int(fields[12]),
            "ticks_per_second": os.sysconf("SC_CLK_TCK"),
            "fds": len(descriptors), "fd_targets": descriptors,
            "rss_kib": int(re.search(r"^VmRSS:\s+(\d+)", status, re.M)[1]),
            "threads": int(re.search(r"^Threads:\s+(\d+)", status, re.M)[1])}


def settled_resources(scenario, phase, expected_fds=None):
    observations = []
    stable_since = None
    previous = None

    def stable():
        nonlocal stable_since, previous
        row = resources(scenario.runtime)
        observations.append(row)
        if expected_fds is not None and row["fds"] != expected_fds:
            stable_since = None
        elif stable_since is None or row["fds"] != previous:
            stable_since = row["time"]
        previous = row["fds"]
        return stable_since is not None and row["time"] - stable_since >= FD_STABLE_NS

    try:
        scenario.wait(stable, "stable " + phase + " FD count")
    finally:
        write_json(scenario.work / ("resource-" + phase + "-settlement.json"), observations)
    return observations


class PressureTest(ScenarioTest):
    def test_callback_queue_sixty_seconds(self):
        with self.scenario("sustained", fixture="batch.db", extra=(
                'callbackSetQueueSize(2)', 'devSnmpSetParam("RequestTimeoutMSec", 400)')) as s:
            records = {"R" + str(n): 100 + n for n in range(1, 22)}
            for cycle in range(10):
                s.put("Many21.PROC")
                s.done_many(records, cycle + 1)
            s.runtime.process.stdin.write("requestSustainCallbacks()\n")
            s.runtime.process.stdin.flush()
            s.wait(lambda: "SNMPSUSTAIN ready" in (s.work / "ioc.log").read_text(), "actual callback queue filled")
            try:
                first = len(s.peer.requests)
                s.peer.values.update({n: 200 + n for n in range(1, 22)})
                s.put("Many21.PROC")
                snapshots = {}
                def ready():
                    snapshots.update(sample(s))
                    return all(name in snapshots and snapshots[name]["state"] == "ready"
                               and snapshots[name]["callback_retries"] > 0 for name in records)
                s.wait(ready, "all 21 record slots ready with actual callback rejection")
                self.assertEqual(sum(len(r["oids"]) for r in s.peer.requests[first:]), 21)
                initial = {name: snapshots[name] for name in records}
                evidence = [settled_resources(s, "initial")[-1]]
                start = time.monotonic()
                for _ in range(3):
                    s.put("Many21.PROC")
                for name in records:
                    self.assertEqual(s.state(name)["rpro"], 1, "Base did not coalesce active PROC")
                while time.monotonic() - start < PRESSURE_SECONDS:
                    time.sleep(max(0, min(SAMPLE_SECONDS, PRESSURE_SECONDS - (time.monotonic() - start))))
                    evidence.append(resources(s.runtime))
                pressure_end_ns = evidence[-1]["time"]
                held = sample(s)
                for name in records:
                    row = held[name]
                    self.assertEqual((row["state"], row["accepted"], row["completed"], row["last_valid_generation"]),
                                     ("ready", 11, 10, 10))
                    self.assertEqual(row["terminal_ns"], initial[name]["terminal_ns"], "Ready result changed")
                    self.assertGreater(row["callback_retries"], initial[name]["callback_retries"])
                    self.assertGreaterEqual(row["last_valid_age_ms"], PRESSURE_SECONDS * 1000)
                    self.assertEqual(s.get(name + ".PACT"), "1")
                    self.assertEqual(s.get("Audit" + name), "10")
                self.assertEqual(sum(len(r["oids"]) for r in s.peer.requests[first:]), 21,
                                 "Active PROC bypassed the occupied record slots")
                s.runtime.process.stdin.write("requestQueueState()\n")
                s.runtime.process.stdin.flush()
                s.wait(lambda: "SNMPQUEUE time=" in (s.work / "ioc.log").read_text(), "Base queue counters")
                queue = re.search(r"SNMPQUEUE time=(\d+) size=(\d+) used=(\d+) overflow=(\d+) max=(\d+)",
                                  (s.work / "ioc.log").read_text())
                self.assertEqual(tuple(map(int, queue.groups()[1:3])), (2, 2))
                self.assertGreater(int(queue[4]), 0)
                s.peer.values.update({n: 300 + n for n in range(1, 22)})
            finally:
                s.runtime.process.stdin.write("requestReleaseCallbacks()\n")
                s.runtime.process.stdin.flush()
            for n in range(1, 22):
                s.expect("R" + str(n), 11, 200 + n)
            s.done_many({"R" + str(n): 300 + n for n in range(1, 22)}, 12)
            evidence.append(resources(s.runtime))
            write_json(s.work / "resources.json", evidence)
            at_completion = evidence[-1]
            evidence.extend(settled_resources(s, "final", evidence[0]["fds"]))
            write_json(s.work / "resources.json", evidence)
            elapsed = (evidence[-1]["time"] - evidence[0]["time"]) / 1e9
            ticks = sum(evidence[-1][name] - evidence[0][name] for name in ("user_ticks", "system_ticks"))
            write_json(s.work / "resource-summary.json", {
                "elapsed_seconds": elapsed, "cpu_seconds": ticks / evidence[0]["ticks_per_second"],
                "cpu_percent_one_core": 100 * ticks / evidence[0]["ticks_per_second"] / elapsed,
                "cpu_limit": None, "cpu_interpretation": "Measured observation; no site limit selected",
                "fd_initial": evidence[0]["fds"], "fd_final": evidence[-1]["fds"],
                "fd_at_completion": at_completion["fds"],
                "fd_settlement_seconds": (evidence[-1]["time"] - at_completion["time"]) / 1e9,
                "pressure_end_ns": pressure_end_ns,
                "rss_initial_kib": evidence[0]["rss_kib"], "rss_max_kib": max(r["rss_kib"] for r in evidence),
            })
            self.assertGreaterEqual(pressure_end_ns - evidence[0]["time"], int(PRESSURE_SECONDS * 1e9))
            self.assertEqual(evidence[-1]["fds"], evidence[0]["fds"], "File descriptors did not return to baseline")
            self.assertEqual({row["threads"] for row in evidence}, {evidence[0]["threads"]})
            self.assertLessEqual(max(row["rss_kib"] for row in evidence) - evidence[0]["rss_kib"], RSS_ALLOWANCE_KIB)
        verify_diagnostics(s)
