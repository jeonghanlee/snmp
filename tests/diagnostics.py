"""Read actual driver snapshots and compare them with wire and FLNK evidence."""

import re
import time

from ioc import write_json


def sample(scenario):
    start = time.monotonic_ns()
    scenario.runtime.process.stdin.write("requestDiagnostics()\n")
    scenario.runtime.process.stdin.flush()
    scenario.wait(lambda: any(int(stamp) >= start for stamp in re.findall(r"SNMPDIAG_END (\d+)",
                  (scenario.work / "ioc.log").read_text())), "complete request snapshot")
    return {row["record"].split(":")[-1]: row for row in observations(scenario.work) if row["time"] >= start}


def observations(work):
    rows = []
    for match in re.finditer(r"SNMPDIAG (\d+) (\S+) ([^\n]+)", (work / "ioc.log").read_text()):
        row = {"time": int(match[1]), "record": match[2]}
        for field in match[3].split():
            key, value = field.split("=", 1)
            row[key] = value if key == "state" else float(value) if key.endswith("_ms") else int(value)
        rows.append(row)
    return rows


def verify(scenario):
    """Check each real application before FLNK, plus the final idle snapshot."""
    test = scenario.test
    rows = observations(scenario.work)
    test.assertTrue(rows, "Missing actual request diagnostics")
    valid, failed, last_valid = {}, {}, {}
    for key, expected in sorted(scenario.expected.items()):
        record, generation = key
        events = [e for e in scenario.driver if (e["record"], e["generation"]) == key]
        audit = next(a for a in scenario.audits if a["record"].replace("Audit", "") == record and a["count"] == generation)
        applied, complete = events[-2:]
        snapshots = [row for row in rows if row["record"] == record and row["generation"] == generation
                     and applied["time"] <= row["time"] <= audit["time"]]
        test.assertEqual(len(snapshots), 1, (key, "Missing unique FLNK diagnostic"))
        row = snapshots[0]
        success = applied["success"]
        valid[record] = valid.get(record, 0) + int(success)
        failed[record] = failed.get(record, 0) + int(not success)
        if success:
            last_valid[record] = (generation, row["applied_ns"])
        test.assertEqual((row["state"], row["callback"], row["completed_ns"]), ("idle", 1, 0))
        test.assertEqual((row["accepted"], row["valid"], row["failed"], row["completed"]),
                         (generation, valid[record], failed[record], generation - 1))
        test.assertEqual((row["last_valid_generation"], row["last_valid_ns"]), last_valid.get(record, (0, 0)))
        for event, field in (("accepted", "accepted_ns"), ("claimed", "claimed_ns"),
                             ("dispatch", "dispatched_ns"), ("result", "terminal_ns"), ("applied", "applied_ns")):
            observed = [e for e in events if e["event"] == event]
            if observed:
                test.assertLessEqual(row[field], observed[0]["time"])
            else:
                test.assertEqual(row[field], 0, (key, field))
        test.assertLessEqual(row["accepted_ns"], row["terminal_ns"])
        test.assertLessEqual(row["terminal_ns"], row["applied_ns"])
        if row["last_valid_ns"]:
            test.assertAlmostEqual(row["last_valid_age_ms"], (row["time"] - row["last_valid_ns"]) / 1e6, places=5)
        else:
            test.assertEqual(row["last_valid_age_ms"], -1)
    for record in valid:
        row = [r for r in rows if r["record"] == record][-1]
        test.assertEqual((row["state"], row["callback"], row["completed"]), ("idle", 0, row["generation"]))
        test.assertEqual(row["valid"] + row["failed"], row["accepted"])
        test.assertEqual(row["queue_age_ms"], 0)
        test.assertAlmostEqual(row["total_ms"], (row["completed_ns"] - row["accepted_ns"]) / 1e6, places=5)
        if row["dispatched_ns"]:
            test.assertAlmostEqual(row["total_ms"], sum(row[k] for k in
                                   ("queue_ms", "network_ms", "callback_ms", "processing_ms")), places=4)
    write_json(scenario.work / "diagnostics.json", rows)
