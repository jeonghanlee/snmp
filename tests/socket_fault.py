"""Compile and control a fault at libc sockets, outside all native SNMP code."""

import json
from pathlib import Path
import subprocess

from ioc import ROOT, digest, write_json


class SocketFault:
    def __init__(self, work):
        self.work = Path(work)
        self.library = self.work / "socket-fault.so"
        self.control = self.work / "socket-control"
        self.log = self.work / "socket-fault.jsonl"
        source = ROOT / "tests/socket_fault.c"
        args = ["cc", "-std=c11", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                "-o", str(self.library), str(source), "-ldl", "-pthread"]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        write_json(self.work / "socket-build.json", dict(args=args, status=result.returncode,
                   stdout=result.stdout, stderr=result.stderr, source_sha256=digest(source),
                   library_sha256=digest(self.library) if not result.returncode else None))
        if result.returncode:
            raise AssertionError("Socket fixture build failed: " + result.stderr)

    def environment(self, port):
        return dict(LD_PRELOAD=str(self.library), SNMP_TEST_SOCKET_CONTROL=str(self.control),
                    SNMP_TEST_SOCKET_LOG=str(self.log), SNMP_TEST_SOCKET_PORT=str(port))

    def arm(self, stage):
        with self.control.open("x") as stream:
            stream.write({"open": "O", "send": "S"}[stage])

    def events(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
