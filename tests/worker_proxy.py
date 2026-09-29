#!/usr/bin/env python3
"""Inject faults only in the socket between the real IOC and real helper."""

import ctypes
import json
import os
from pathlib import Path
import signal
import socket
import struct
import sys
import threading
import time


HEADER = struct.Struct("!IHHIIQQ")
LIMIT = 256 * 1024


def main():
    parent = int(sys.argv[2])
    if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != parent:
        return 2
    outer = socket.socket(fileno=3)
    outer.setblocking(True)
    inner, child = socket.socketpair()
    executable = os.environ["SNMP_WORKER_TARGET"]
    mode = os.environ.get("SNMP_WORKER_FAULT", "fragment")
    actions = [(os.POSIX_SPAWN_DUP2, child.fileno(), 3),
               (os.POSIX_SPAWN_CLOSE, child.fileno()), (os.POSIX_SPAWN_CLOSE, inner.fileno())]
    pid = os.posix_spawn(executable, [executable, "--parent", str(os.getpid())], os.environ,
                         file_actions=actions)
    child.close()
    evidence = Path(os.environ["SNMP_WORKER_PROXY_LOG"] + f"-{os.getpid()}.jsonl")
    log = os.open(evidence, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    stopped = threading.Event()

    def exact(source, length):
        data = bytearray()
        while len(data) < length:
            chunk = source.recv(length - len(data))
            if not chunk:
                raise EOFError
            data.extend(chunk)
        return bytes(data)

    def relay(source, destination, direction):
        try:
            while not stopped.is_set():
                header = exact(source, HEADER.size)
                magic, version, kind, length, reserved, epoch, transaction = HEADER.unpack(header)
                if length > LIMIT - HEADER.size:
                    raise ValueError("Oversized source frame")
                packet = header + exact(source, length)
                os.write(log, (json.dumps(dict(time_ns=time.monotonic_ns(), direction=direction,
                                               kind=kind, epoch=epoch, transaction=transaction,
                                               length=len(packet), helper_pid=pid)) + "\n").encode())
                if direction == "to-worker" and kind == 1 and mode == "build":
                    packet = packet[:36] + bytes([packet[36] ^ 1]) + packet[37:]
                if direction == "to-ioc" and kind == 2:
                    if mode == "magic":
                        packet = b"FAIL" + packet[4:]
                    elif mode == "version":
                        packet = packet[:4] + b"\x00\x02" + packet[6:]
                    elif mode == "kind":
                        packet = packet[:6] + b"\xff\xff" + packet[8:]
                    elif mode == "oversize":
                        packet = packet[:8] + struct.pack("!I", LIMIT) + packet[12:]
                    elif mode == "reserved":
                        packet = packet[:12] + struct.pack("!I", 1) + packet[16:]
                if direction == "to-worker" and kind == 5 and mode == "partial-request":
                    destination.sendall(packet[:1])
                    stopped.wait(30)
                    return
                if direction == "to-ioc" and kind == 6:
                    if mode == "epoch":
                        packet = packet[:16] + struct.pack("!Q", epoch + 1) + packet[24:]
                    elif mode == "identity":
                        packet = packet[:24] + struct.pack("!Q", transaction + 1) + packet[32:]
                    elif mode == "truncate":
                        destination.sendall(packet[:17])
                        raise EOFError
                    elif mode == "duplicate":
                        packet += packet
                    elif mode == "slow-result":
                        for byte in packet:
                            destination.sendall(bytes([byte]))
                            time.sleep(0.05)
                        continue
                for start in range(0, len(packet), 7 if mode == "fragment" else len(packet)):
                    destination.sendall(packet[start:start + (7 if mode == "fragment" else len(packet))])
        except (OSError, EOFError, ValueError):
            pass
        finally:
            stopped.set()
            for connection in (outer, inner):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    threads = [threading.Thread(target=relay, args=(outer, inner, "to-worker")),
               threading.Thread(target=relay, args=(inner, outer, "to-ioc"))]
    for thread in threads:
        thread.start()
    stopped.wait()
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    os.waitpid(pid, 0)
    for thread in threads:
        thread.join(timeout=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
