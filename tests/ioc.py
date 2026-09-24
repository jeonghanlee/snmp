"""Owned real IOC processes, CA clients and immutable run identity evidence."""

from datetime import datetime, timezone
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = []
WAIT = 10.0
BASELINE_COMMIT = "db9ebf51bc81d6f63d9395513d94d60b3b7eda83"


def is_legacy_baseline(build):
    return (build.get("source_kind") == "git-archive" and
            build.get("source_commit") == BASELINE_COMMIT and
            build.get("dirty_diff_sha256") == hashlib.sha256(b"").hexdigest())


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def settings():
    config = os.environ.get("SNMP_TEST_RUN_CONFIG")
    if config:
        return json.loads(Path(config).read_text())
    return {"ioc": str(ROOT / "bin/linux-x86_64/snmpRequestTest"),
            "negative_control": None, "profile": {"action_timeout": WAIT}}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


class IOC:
    def __init__(self, work, lines, prefix="SNMPTEST:", require_shutdown=True):
        self.work = Path(work)
        self.config = settings()
        self.executable = Path(self.config["ioc"]).resolve()
        self.top = self.executable.parents[2]
        self.dbd = self.top / "dbd" / (self.executable.name + ".dbd")
        self.prefix = prefix
        self.instance = uuid.uuid4().hex
        self.require_shutdown = require_shutdown
        self.process = None
        self.repeater = None
        self.closed = False
        self.log = self.commands = None
        self.deadline = float(self.config["profile"].get("action_timeout", WAIT))
        for tool in ("caget", "caput", "caRepeater"):
            if not shutil.which(tool):
                raise RuntimeError("Selected Base client is missing from PATH: " + tool)
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            port = reserve.getsockname()[1]
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reserve:
            reserve.bind(("127.0.0.1", 0))
            repeater_port = reserve.getsockname()[1]
        native_config = self.work / "native-config"
        native_state = self.work / "native-state"
        native_config.mkdir(mode=0o700)
        native_state.mkdir(mode=0o700)
        self.env = dict(os.environ, EPICS_CAS_INTF_ADDR_LIST="127.0.0.1",
                        EPICS_CA_ADDR_LIST=f"127.0.0.1:{port}", EPICS_CA_AUTO_ADDR_LIST="NO",
                        EPICS_CA_NAME_SERVERS="", EPICS_CAS_AUTO_BEACON_ADDR_LIST="NO",
                        EPICS_CAS_BEACON_ADDR_LIST="", EPICS_CA_SERVER_PORT=str(port),
                        EPICS_CAS_SERVER_PORT=str(port), EPICS_CA_REPEATER_PORT=str(repeater_port),
                        SNMPCONFPATH=str(native_config), SNMP_PERSISTENT_DIR=str(native_state), MIBS="")
        self.metadata = {"started_at": now(), "instance": self.instance,
                         "ioc": str(self.executable), "ioc_sha256": digest(self.executable),
                         "dbd": str(self.dbd), "dbd_sha256": digest(self.dbd), "ca_port": port,
                         "repeater_port": repeater_port}
        startup = [f'dbLoadDatabase({json.dumps(str(self.dbd))})',
                   f'{self.executable.name}_registerRecordDeviceDriver(pdbbase)'] + lines
        startup += [f'dbLoadRecords("{ROOT}/tests/identity.db", "P={prefix},INSTANCE={self.instance}")',
                    "iocInit"]
        (self.work / "st.cmd").write_text("\n".join(startup) + "\n")
        fixture_paths = [Path(match.group(1)) for line in startup
                         for match in re.finditer(r'dbLoadRecords\("([^\"]+)"', line)]
        self.metadata["fixtures"] = {str(path): digest(path) for path in fixture_paths}
        self.log = (self.work / "ioc.log").open("w")
        self.commands = (self.work / "ca.jsonl").open("w")
        ACTIVE.append(self)
        try:
            self.repeater = subprocess.Popen(["caRepeater"], env=self.env,
                                             stdout=self.log, stderr=subprocess.STDOUT)
            self.metadata["repeater_pid"] = self.repeater.pid
            deadline = time.monotonic() + self.deadline
            while True:
                if self.repeater.poll() is not None or time.monotonic() >= deadline:
                    raise AssertionError("Owned CA repeater failed readiness")
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                    try:
                        probe.bind(("127.0.0.1", repeater_port))
                    except OSError as error:
                        if error.errno != errno.EADDRINUSE:
                            raise
                        break
                time.sleep(0.01)
            self.process = subprocess.Popen([str(self.executable), str(self.work / "st.cmd")],
                                            cwd=self.top, env=self.env, stdin=subprocess.PIPE,
                                            stdout=self.log, stderr=subprocess.STDOUT, text=True)
            self.metadata["pid"] = self.process.pid
            self.wait_for(lambda: self.get("TestInstance") == self.instance, "owned IOC instance readiness")
            self.verify_runtime()
        except BaseException:
            self.close(check=False)
            raise

    def verify_runtime(self):
        proc = Path("/proc") / str(self.process.pid)
        if (proc / "exe").resolve() != self.executable:
            raise AssertionError("Unexpected running IOC executable")
        paths = {line.split()[-1] for line in (proc / "maps").read_text().splitlines()
                 if "/" in line and ".so" in line.split()[-1]}
        libraries = {p: digest(p) for p in sorted(paths) if Path(p).is_file()}
        expected = (self.top / "lib" / self.executable.parent.name / "libdevSnmp.so").resolve()
        loaded = [Path(p).resolve() for p in libraries if Path(p).name.startswith("libdevSnmp.so")]
        if loaded != [expected]:
            raise AssertionError(f"Wrong loaded module: expected {expected}, observed {loaded}")
        self.metadata["loaded_libraries"] = libraries
        self.metadata["clients"] = {tool: {"path": shutil.which(tool), "sha256": digest(shutil.which(tool))}
                                    for tool in ("caget", "caput", "caRepeater")}
        native = [path for path in libraries if re.match(r"libnetsnmp\.so", Path(path).name)]
        if len(native) != 1:
            raise AssertionError("Expected one actual native Net-SNMP library")
        library = ctypes.CDLL(native[0])
        library.netsnmp_get_version.restype = ctypes.c_char_p
        native_version = library.netsnmp_get_version().decode()
        self.metadata["net_snmp_version"] = native_version
        allowed = self.config["profile"].get("net_snmp_versions")
        if allowed and native_version not in allowed:
            raise AssertionError("Undeclared native Net-SNMP version: " + native_version)
        manifest = self.top / "build-inputs.json"
        if manifest.is_file():
            build = json.loads(manifest.read_text())
            for path in (self.executable, self.dbd, expected):
                if build["artifacts"].get(str(path.relative_to(self.top))) != digest(path):
                    raise AssertionError("Artifact differs from build evidence: " + str(path))
            for tool in self.metadata["clients"].values():
                if Path(tool["path"]).resolve().parents[2] != Path(build["epics_base"]).resolve():
                    raise AssertionError("CA client does not belong to the selected Base")
            base_lib = (Path(build["epics_base"]) / "lib" / self.executable.parent.name).resolve()
            for path in libraries:
                if re.match(r"lib(Com|ca|dbCore|dbRecStd)\.so", Path(path).name):
                    if Path(path).resolve().parent != base_lib:
                        raise AssertionError("IOC loaded another Base: " + path)
            self.metadata["build_manifest_sha256"] = digest(manifest)
        self.metadata["startup_sha256"] = digest(self.work / "st.cmd")
        write_json(self.work / "run.json", self.metadata)

    def client(self, args):
        result = subprocess.run(args, env=self.env, text=True, capture_output=True, timeout=4)
        self.commands.write(json.dumps({"time": time.monotonic_ns(), "args": args,
                                        "status": result.returncode, "out": result.stdout,
                                        "err": result.stderr}) + "\n")
        self.commands.flush()
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def get(self, name, options=()):
        return self.client(["caget", "-w", "0.4", "-t", "-n", *options, self.prefix + name])

    def put(self, name, value=1, wait=False):
        return self.client(["caput", "-w", "0.4", "-t", *(["-c"] if wait else []),
                            self.prefix + name, str(value)])

    def wait_for(self, predicate, description="condition", timeout=None):
        deadline = time.monotonic() + (self.deadline if timeout is None else timeout)
        last = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError(f"IOC exited before {description}; evidence: {self.work}")
            if self.repeater.poll() is not None:
                raise AssertionError("Owned CA repeater exited during the test")
            try:
                if predicate():
                    return
                last = None
            except RuntimeError as error:
                last = str(error)
            time.sleep(0.02)
        raise AssertionError(f"Wait expired: {description}; last error: {last}; evidence: {self.work}")

    def close(self, check=True):
        if self.closed:
            return
        self.closed = True
        error = None
        try:
            if self.process is not None:
                if self.process.poll() is None:
                    proc = Path("/proc") / str(self.process.pid)
                    try:
                        self.metadata["final_fd_count"] = len(list((proc / "fd").iterdir()))
                        self.metadata["final_status"] = (proc / "status").read_text()
                    except FileNotFoundError:
                        self.metadata["resource_snapshot"] = "process exited during collection"
                    try:
                        self.process.communicate("snmpr(0)\n", timeout=self.deadline)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
                        error = "IOC did not exit on stdin EOF"
                self.metadata["exit_code"] = self.process.returncode
                if self.process.returncode != 0:
                    error = error or f"IOC exit code {self.process.returncode}"
        finally:
            if self.process is not None and self.process.poll() is None:
                self.process.kill()
                self.process.wait()
                error = error or "Forced owned-process cleanup"
            if self.repeater is not None:
                if self.repeater.poll() is None:
                    self.repeater.terminate()
                    try:
                        self.repeater.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.repeater.kill()
                        self.repeater.wait()
                        error = error or "Forced CA repeater cleanup"
                self.metadata["repeater_exit_code"] = self.repeater.returncode
            if self.log is not None:
                self.log.close()
            if self.commands is not None:
                self.commands.close()
            log = (self.work / "ioc.log").read_text()
            version = re.search(r"## EPICS R(\d+\.\d+\.\d+)", log)
            required_base = self.config["profile"].get("base_version")
            if version:
                self.metadata["base_version"] = version.group(1)
            if not version or required_base and version.group(1) != required_base:
                error = error or "Missing or unexpected actual Base version banner"
            self.metadata["finished_at"] = now()
            self.metadata["cleanup_error"] = error
            write_json(self.work / "run.json", self.metadata)
            if self in ACTIVE:
                ACTIVE.remove(self)
        log = (self.work / "ioc.log").read_text()
        if check:
            if error:
                raise AssertionError(error)
            if self.require_shutdown and "devSnmp: shutdown complete" not in log:
                raise AssertionError("Missing module shutdown confirmation")


def trace_evidence(work):
    """Decode only actual IOC observations; an absent trace remains absent."""
    work = Path(work)
    log = (work / "ioc.log").read_text()
    driver, flnk = [], []
    for match in re.finditer(r"SNMPREQ (\d+) (\d+) (\S+) (\d+) (\w+) ([01])([^\n]*)", log):
        sequence, stamp, record, generation, event, success, extra = match.groups()
        driver.append(dict(sequence=int(sequence), time=int(stamp), record=record,
                           generation=int(generation), event=event, success=bool(int(success)), extra=extra.strip()))
    for match in re.finditer(r"SNMPAUDIT (\d+) (\S+) (\S+) (\d+) (\d+) (\d+)", log):
        stamp, record, value, pact, severity, count = match.groups()
        flnk.append(dict(time=int(stamp), record=record, value=value, pact=int(pact),
                         severity=int(severity), count=int(count)))
    for name, rows in (("driver.jsonl", driver), ("flnk.jsonl", flnk)):
        (work / name).write_text("".join(json.dumps(row) + "\n" for row in rows))
    return driver, flnk
