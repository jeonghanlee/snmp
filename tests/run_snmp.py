#!/usr/bin/env python3
"""Run real IOC suites with explicit inputs, retained evidence and strict totals."""

import argparse
from datetime import datetime, timezone
import json
import hashlib
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from ioc import ACTIVE, ROOT, digest, now, write_json


SEQUENCING = (
    "idle_delayed_and_unchanged", "serial_forward_link", "late_shared_oid_request",
    "batch_oid_mapping_and_conversion", "active_proc_coalesces", "periodic_scan_while_active",
    "mixed_legacy_idle", "signed_and_changing_values", "legacy_polling_does_not_starve_request",
)
FAILURES = (
    "timeout_recovery_preserves_value", "terminal_protocol_errors", "late_reply_after_timeout",
    "type_and_buffer_errors", "deadline_independent_of_network", "shutdown_eof_pending",
    "shutdown_explicit_pending", "shutdown_callback_pending", "callback_queue_pressure", "queued_deadline",
)
LIMITS = ("deadline_completion_seconds", "healthy_max_seconds", "healthy_p99_delta_seconds",
          "pending_per_worker", "queue_bytes_per_worker")


class Results(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []

    def startTest(self, test):
        self.started = time.monotonic()
        super().startTest(test)

    def record(self, test, outcome, detail=None):
        self.rows.append({"case": test.id(), "outcome": outcome, "detail": detail,
                          "seconds": time.monotonic() - self.started,
                          "evidence": str(getattr(test, "work", "unavailable"))})

    def addSuccess(self, test):
        self.record(test, "passed")
        super().addSuccess(test)

    def addFailure(self, test, error):
        self.record(test, "failed", self._exc_info_to_string(error, test))
        super().addFailure(test, error)

    def addError(self, test, error):
        self.record(test, "error", self._exc_info_to_string(error, test))
        super().addError(test, error)

    def addSkip(self, test, reason):
        self.record(test, "incomplete", reason)
        super().addSkip(test, reason)


def probe(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
        return {"status": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": str(error)}


def interrupt(signum, frame):
    raise KeyboardInterrupt(f"Signal {signum}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ioc", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--suite", choices=("legacy", "sequencing", "failures", "protocol", "lifecycle", "batch", "conversion", "robustness", "pressure", "teardown", "accounting", "registration", "v3-baseline", "legacy-set"), required=True)
    parser.add_argument("--output", type=Path, help="New evidence directory; never overwritten")
    parser.add_argument("--negative-control", choices=("wrong-value", "miswired", "trace-loss"))
    parser.add_argument("--case", help="One case, explicitly reported as partial coverage")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--cycles", type=int, help="Partial lifecycle repetitions for development")
    parser.add_argument("--dtyp", choices=("Snmp", "SnmpRequest"), default="SnmpRequest")
    parser.add_argument("--baseline-evidence", type=Path, help="Successful legacy run to compare")
    parser.add_argument("--baseline-ioc", type=Path, help="Original archived IOC for actual registration mismatch tests")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    for name in LIMITS:
        value = profile.get("limits", {}).get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            parser.error("Missing positive acceptance limit: " + name)
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    if args.cycles is not None and (args.cycles < 1 or args.suite not in ("lifecycle", "batch", "conversion", "robustness")):
        parser.error("--cycles must be positive and requires lifecycle, batch, conversion or robustness")
    if not args.ioc.is_file():
        parser.error("--ioc must name the actual built executable")
    build = args.ioc.resolve().parents[2] / "build-inputs.json"
    if not build.is_file() or json.loads(build.read_text()).get("build_exit") != 0:
        parser.error("--ioc requires a successful tests/build_fixture.py build manifest")
    if args.negative_control and args.suite not in ("sequencing", "lifecycle"):
        parser.error("Observer negative controls require sequencing or lifecycle")
    if args.baseline_evidence and args.suite not in ("legacy", "conversion"):
        parser.error("--baseline-evidence requires legacy or conversion")
    if args.suite == "registration" and not args.baseline_ioc:
        parser.error("--suite registration requires --baseline-ioc")
    if args.baseline_ioc and (args.suite != "registration" or not args.baseline_ioc.is_file()):
        parser.error("--baseline-ioc requires registration and an actual executable")
    if args.output:
        work = args.output.resolve()
        work.mkdir(parents=True, exist_ok=False)
    else:
        parent = ROOT / "work/snmp-tests"
        parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-"), dir=parent))
    dtype = "Snmp" if args.suite == "legacy" else args.dtyp
    config = {"ioc": str(args.ioc.resolve()), "profile": profile, "output": str(work),
              "cycles": args.cycles,
              "negative_control": args.negative_control, "dtyp": dtype,
              "baseline_ioc": str(args.baseline_ioc.resolve()) if args.baseline_ioc else None,
              "baseline_evidence": str(args.baseline_evidence.resolve()) if args.baseline_evidence else None}
    write_json(work / "config.json", config)
    os.environ["SNMP_TEST_RUN_CONFIG"] = str(work / "config.json")
    print(f"Evidence: {work}", flush=True)
    fixtures = {str(path.relative_to(ROOT)): digest(path) for path in sorted((ROOT / "tests").rglob("*"))
                if path.is_file() and "__pycache__" not in path.parts}
    dirty_diff = subprocess.run(["git", "-C", str(ROOT), "diff", "HEAD", "--binary"], capture_output=True)
    metadata = {"started_at": now(), "argv": [sys.executable] + sys.argv, "cwd": os.getcwd(),
                "suite": args.suite, "profile": profile,
                "profile_path": str(args.profile.resolve()), "profile_sha256": digest(args.profile),
                "seed": 0, "platform": platform.platform(), "architecture": platform.machine(),
                "os_release": Path("/etc/os-release").read_text(), "python": platform.python_version(),
                "base_client": probe(["caget", "-h"]), "net_snmp": probe(["net-snmp-config", "--version"]),
                "source_commit": probe(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
                "dirty_diff_sha256": hashlib.sha256(dirty_diff.stdout).hexdigest() if not dirty_diff.returncode else None,
                "fixtures": fixtures, "build_manifest": json.loads(build.read_text()) if build.is_file() else None,
                "build_manifest_path": str(build), "build_manifest_sha256": digest(build),
                "dtyp": dtype,
                "partial": bool(args.case or args.negative_control or args.cycles),
                "repetitions": args.repeat, "cycles_override": args.cycles}
    write_json(work / "run.json", metadata)
    signal.signal(signal.SIGTERM, interrupt)
    result, abort = None, None
    try:
        if args.suite in ("sequencing", "failures"):
            from test_request import RequestTest
            case_class = RequestTest
            names = SEQUENCING if args.suite == "sequencing" else FAILURES
        elif args.suite == "legacy":
            from test_legacy import LegacyTest
            case_class, names = LegacyTest, ("inputs_and_outputs",)
        elif args.suite == "protocol":
            from test_protocol import ProtocolTest
            case_class, names = ProtocolTest, ("v1", "v2c", "v3_no_auth", "v3_auth", "v3_priv")
        elif args.suite == "v3-baseline":
            from test_snmpv3 import SnmpV3Test, CASES
            case_class, names = SnmpV3Test, CASES
        elif args.suite == "legacy-set":
            from test_legacy_set import LegacySetTest, CASES
            case_class, names = LegacySetTest, CASES
        elif args.suite == "lifecycle":
            from test_lifecycle import LifecycleTest, CASES
            case_class, names = LifecycleTest, CASES
        elif args.suite == "batch":
            from test_batch import BatchTest, CASES
            case_class, names = BatchTest, CASES
        elif args.suite == "robustness":
            from test_robustness import RobustnessTest, CASES
            case_class, names = RobustnessTest, CASES
        elif args.suite == "pressure":
            from test_pressure import PressureTest, CASES
            case_class, names = PressureTest, CASES
        elif args.suite == "teardown":
            from test_teardown import TeardownTest, CASES
            case_class, names = TeardownTest, CASES
        elif args.suite == "accounting":
            from test_accounting import AccountingTest, CASES
            case_class, names = AccountingTest, CASES
        elif args.suite == "registration":
            from test_registration import RegistrationTest, CASES
            case_class, names = RegistrationTest, CASES
        else:
            from test_conversion import ConversionTest, CASES
            case_class, names = ConversionTest, CASES
        if args.negative_control:
            names = ("idle_and_held_values",) if args.suite == "lifecycle" else ("idle_delayed_and_unchanged",)
        if args.case:
            if args.case not in names:
                raise ValueError("Case is not in the selected suite: " + args.case)
            names = (args.case,)
        metadata["expected_cases"] = [case_class.__name__ + ".test_" + name for name in names]
        expected = len(names) * args.repeat
        suite = unittest.TestSuite(case_class("test_" + name) for _ in range(args.repeat) for name in names)
        result = unittest.TextTestRunner(verbosity=2, resultclass=Results).run(suite)
        complete = result.testsRun == expected and not result.skipped
        passed = result.wasSuccessful() and complete
    except BaseException as error:
        abort, passed = repr(error), False
        print("ABORT:", abort, flush=True)
    finally:
        cleanup = []
        for runtime in list(ACTIVE):
            try:
                runtime.close()
            except BaseException as error:
                cleanup.append(str(error))
        if cleanup:
            passed = False
        metadata.update(finished_at=now(), abort=abort, cleanup_errors=cleanup)
        write_json(work / "run.json", metadata)
        write_json(work / "results.json", {"passed": passed, "abort": abort,
                                           "tests_run": result.testsRun if result else 0,
                                           "rows": result.rows if result else []})
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
