#!/usr/bin/env python3
"""Build exact inputs and run the complete local candidate qualification matrix."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

from ioc import BASELINE_COMMIT, ROOT, digest, now, write_json


DEADLINE_BASELINE = "68294c2a91e74b7559aea0aa1e1ae0fb87e2aa8a"
ROLLBACK_COMMIT = "30d8b81fb10ff1940d9ff29d46d6954679a1f5ba"
SUITES = ("sequencing", "failures", "lifecycle", "batch", "robustness", "pressure", "teardown", "accounting")
OBSERVER_FAILURES = {
    "wrong-value": r"'909' != '101'",
    "miswired": r"(?m)^AssertionError: 0 != 1 : FLNK must run before PACT clears$",
    "trace-loss": r"(?m)^AssertionError: .* : Missing or overflowing driver trace$",
}
DEADLINE_FAILURES = {"late_result_without_service_tick": r"'0' != '3'",
                     "queued_expiry_without_service_tick": "Expired queued record emitted an application GET"}


def probe(argv):
    try:
        result = subprocess.run(argv, text=True, capture_output=True, timeout=15)
        return {"argv": argv, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"argv": argv, "error": str(error)}


class Matrix:
    def __init__(self, args):
        self.args = args
        self.output = args.output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.steps = []
        self.manifest = {"started_at": now(), "argv": [sys.executable] + sys.argv, "cwd": os.getcwd(),
                         "platform": platform.platform(), "os_release": Path("/etc/os-release").read_text(),
                         "python": platform.python_version(), "architecture": platform.machine(),
                         "epics_base": str(args.base.resolve()), "container_image": args.image_id,
                         "profile_sha256": digest(args.profile), "partial": False, "passed": False,
                         "protocol_profile_sha256": digest(args.protocol_profile),
                         "steps": self.steps, "packages": {}, "tools": {}}
        for name, argv in (("compiler", ["g++", "--version"]), ("net_snmp", ["net-snmp-config", "--version"]),
                           ("crypto", ["openssl", "version", "-a"]), ("agent", ["snmpd", "-v"]),
                           ("client", ["snmpget", "--version"])):
            self.manifest["tools"][name] = probe(argv)
        for tool in ("snmpd", "snmpget", "g++", "net-snmp-config", "openssl"):
            path = shutil.which(tool)
            self.manifest["tools"][tool] = {"path": path, "sha256": digest(path) if path else None}
        if shutil.which("dpkg-query"):
            self.manifest["packages"] = probe(["dpkg-query", "-W", "libsnmp*", "libssl*", "libc6", "gcc*", "g++*"])
        elif shutil.which("rpm"):
            self.manifest["packages"] = probe(["rpm", "-q", "net-snmp", "net-snmp-libs", "net-snmp-devel",
                                               "openssl", "openssl-libs", "glibc", "gcc", "gcc-c++"])
        self.save()

    def save(self):
        write_json(self.output / "matrix.json", self.manifest)

    def execute(self, label, argv, result_path=None, expected_failure=None, acceptance_required=True):
        log = self.output / (label + ".log")
        row = {"label": label, "argv": [str(a) for a in argv], "cwd": str(ROOT), "started_at": now(),
               "expected_failure": expected_failure, "acceptance_required": acceptance_required,
               "log": str(log), "passed": False}
        self.steps.append(row)
        self.save()
        print("START " + label, flush=True)
        with log.open("w") as stream:
            result = subprocess.run(row["argv"], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        row.update(exit_code=result.returncode, finished_at=now(), log_sha256=digest(log))
        if result_path and result_path.is_file():
            evidence = json.loads(result_path.read_text())
            row.update(result_path=str(result_path), result_sha256=digest(result_path), results=evidence)
            if expected_failure:
                failed = [r for r in evidence["rows"] if r["outcome"] != "passed"]
                detail = "\n".join(r.get("detail") or "" for r in failed)
                run = json.loads((result_path.parent / "run.json").read_text())
                row["passed"] = (result.returncode == 1 and not evidence["passed"] and
                                 evidence["abort"] is None and not run["cleanup_errors"] and
                                 evidence["tests_run"] == 1 and bool(failed) and
                                 all(r["outcome"] == "failed" for r in failed) and
                                 re.search(expected_failure, detail) is not None)
            else:
                row["passed"] = result.returncode == 0 and evidence["passed"]
        elif result_path is None:
            row["passed"] = result.returncode == 0
        self.save()
        prefix = "" if acceptance_required else "HISTORICAL OBSERVATION "
        print(prefix + ("PASS " if row["passed"] else "FAIL ") + label, flush=True)
        return row["passed"]

    def build(self, label, *options):
        path = self.output / label
        passed = self.execute(label, [sys.executable, ROOT / "tests/build_fixture.py", "--base", self.args.base,
                                     "--output", path, *options])
        if not passed:
            raise RuntimeError("Build failed: " + label)
        products = list(path.glob("bin/*/snmp"))
        if len(products) != 1:
            raise RuntimeError("Expected one host IOC product: " + str(products))
        test = products[0].with_name("snmpRequestTest")
        return test if test.is_file() else products[0]

    def suite(self, label, ioc, suite, *options, expected_failure=None, acceptance_required=True):
        output = self.output / label
        profile = self.args.protocol_profile if suite == "protocol" else self.args.profile
        argv = [sys.executable, ROOT / "tests/run_snmp.py", "--ioc", ioc, "--profile", profile,
                "--suite", suite, "--output", output, *options]
        self.execute(label, argv, output / "results.json", expected_failure, acceptance_required)
        return output

    def run(self):
        baseline = self.build("baseline", "--revision", BASELINE_COMMIT)
        rollback = self.build("rollback", "--revision", ROLLBACK_COMMIT).with_name("snmp")
        candidate = self.build("candidate")
        asan = self.build("asan", "--sanitizer", "address")
        defective = self.build("deadline-baseline", "--revision", DEADLINE_BASELINE)
        legacy = self.suite("baseline-legacy", baseline, "legacy")
        wave = self.suite("baseline-waveforms", baseline, "conversion", "--case", "waveforms")
        self.suite("baseline-protocol", baseline, "protocol", "--dtyp", "Snmp", acceptance_required=False)
        self.suite("rollback-legacy", rollback, "legacy", "--baseline-evidence", legacy)
        self.suite("rollback-waveforms", rollback, "conversion", "--case", "waveforms", "--baseline-evidence", wave)
        self.suite("rollback-protocol", rollback, "protocol", "--dtyp", "Snmp")
        self.suite("candidate-registration", candidate, "registration", "--baseline-ioc", baseline)
        self.suite("candidate-legacy", candidate, "legacy", "--baseline-evidence", legacy)
        self.suite("candidate-conversion", candidate, "conversion", "--baseline-evidence", wave)
        for dtype in ("Snmp", "SnmpRequest"):
            self.suite("candidate-protocol-" + dtype, candidate, "protocol", "--dtyp", dtype)
        for suite in SUITES:
            self.suite("candidate-" + suite, candidate, suite)
        for control, reason in OBSERVER_FAILURES.items():
            self.suite("negative-" + control, candidate, "sequencing", "--negative-control", control,
                       expected_failure=reason)
        for case, reason in DEADLINE_FAILURES.items():
            self.suite("negative-" + case, defective, "robustness", "--case", case, expected_failure=reason)
        self.suite("negative-baseline-provenance", candidate, "legacy", "--baseline-evidence",
                   self.output / "candidate-legacy", expected_failure="Baseline provenance must be an unmodified git archive")
        for suite in ("protocol", "failures", "teardown"):
            self.suite("asan-" + suite, asan, suite)
        self.suite("asan-legacy", asan, "legacy", "--baseline-evidence", legacy)
        self.suite("asan-waveforms", asan, "conversion", "--case", "waveforms", "--baseline-evidence", wave)
        self.suite("rollback-terminal", rollback, "teardown", "--case", "base_exit_observer")
        pairs = {}
        for name, ioc, role in (("candidate", candidate, "candidate"),
                                ("rollback", rollback, "operational_rollback"),
                                ("baseline", baseline, "historical_comparator"),
                                ("asan", asan, "sanitized_candidate")):
            top = ioc.parents[2]
            manifest = top / "build-inputs.json"
            pairs[name] = {"role": role, "ioc": str(ioc), "ioc_sha256": digest(ioc),
                           "build_manifest": str(manifest), "build_manifest_sha256": digest(manifest),
                           "artifacts": json.loads(manifest.read_text())["artifacts"],
                           "startup_records": {str(p): digest(p) for p in self.output.glob(name + "-*/**/st.cmd")},
                           "database_inputs": {str(p.relative_to(ROOT)): digest(p) for p in
                                               list((ROOT / "tests").glob("*.db")) + list((ROOT / "examples").glob("*"))}}
        write_json(self.output / "artifact-pairs.json", pairs)
        self.manifest["artifact_pairs_sha256"] = digest(self.output / "artifact-pairs.json")
        self.manifest["all_steps_passed"] = all(row["passed"] for row in self.steps)
        self.manifest["historical_failures"] = [row["label"] for row in self.steps
                                                if not row["acceptance_required"] and not row["passed"]]
        self.manifest["passed"] = all(row["passed"] for row in self.steps if row["acceptance_required"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=ROOT / "tests/profiles/loopback.json")
    parser.add_argument("--protocol-profile", type=Path, default=ROOT / "tests/profiles/snmpv3.json")
    parser.add_argument("--image-id", help="Caller-recorded immutable container ID; retain container inspection externally")
    args = parser.parse_args()
    if not args.base.is_dir():
        parser.error("--base must name the installed Base directory")
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    matrix = Matrix(args)
    try:
        matrix.run()
    except BaseException as error:
        matrix.manifest.update(abort=repr(error), passed=False)
        raise
    finally:
        matrix.manifest["finished_at"] = now()
        matrix.save()
    print("Matrix: " + str(matrix.output / "matrix.json"), flush=True)
    if matrix.manifest.get("historical_failures"):
        print("Historical failures retained: " + ", ".join(matrix.manifest["historical_failures"]), flush=True)
    return 0 if matrix.manifest["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
