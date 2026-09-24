"""Suspend only a named thread of the test-owned Linux IOC through ptrace."""

from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import time

from ioc import write_json


PTRACE_DETACH = 17
PTRACE_SEIZE = 0x4206
PTRACE_INTERRUPT = 0x4207
WAIT_ALL = 0x40000000
STOP_TIMEOUT = 2.0


@contextmanager
def paused_thread(runtime, name):
    """Keep the real code and clock intact while delaying one owned worker."""
    process = runtime.process
    if process.poll() is not None:
        raise AssertionError("Cannot suspend an exited IOC")
    tasks = Path("/proc") / str(process.pid) / "task"
    matches = [p for p in tasks.iterdir() if (p / "comm").read_text().strip() == name]
    if len(matches) != 1:
        raise AssertionError(f"Expected one owned thread named {name}: {matches}")
    thread = matches[0]
    tid = int(thread.name)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.ptrace.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
    libc.ptrace.restype = ctypes.c_long
    evidence = dict(pid=process.pid, tid=tid, name=name, requested=time.monotonic_ns(),
                    before_status=(thread / "status").read_text(),
                    before_wchan=(thread / "wchan").read_text())
    path = runtime.work / f"thread-{evidence['requested']}.json"

    def control(operation):
        if libc.ptrace(operation, tid, None, None) == -1:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))

    attached = stopped = False
    try:
        control(PTRACE_SEIZE)
        attached = True
        control(PTRACE_INTERRUPT)
        deadline = time.monotonic() + STOP_TIMEOUT
        while time.monotonic() < deadline:
            child, status = os.waitpid(tid, os.WNOHANG | WAIT_ALL)
            if child:
                if not os.WIFSTOPPED(status):
                    raise AssertionError(f"Unexpected owned-thread wait status {status}")
                stopped = True
                evidence.update(stopped=time.monotonic_ns(), wait_status=status,
                                stopped_status=(thread / "status").read_text())
                write_json(path, evidence)
                break
            time.sleep(0.001)
        if not stopped:
            raise AssertionError("Owned thread did not enter ptrace stop")
        yield evidence
    finally:
        if attached:
            if stopped:
                evidence["resume_requested"] = time.monotonic_ns()
                control(PTRACE_DETACH)
                evidence["resumed"] = time.monotonic_ns()
            else:
                # A failed stop is an infrastructure failure, never a passed case.
                process.kill()
                process.wait()
                evidence["forced_cleanup"] = True
        evidence["finished"] = time.monotonic_ns()
        write_json(path, evidence)
