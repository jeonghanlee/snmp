"""Real private snmpd and a transparent UDP observation boundary."""

import json
import os
from pathlib import Path
import select
import shutil
import socket
import subprocess
import sys
import threading
import time

from ioc import ROOT, digest, write_json
from snmp_peer import items, oid_text


CONTACT = ".1.3.6.1.2.1.1.4.0"
NAME = ".1.3.6.1.2.1.1.5.0"
AUTH = "fixture-auth-test-only"
PRIV = "fixture-priv-test-only"
USERS = {"noAuthNoPriv": "fixtureNoAuth", "authNoPriv": "fixtureAuth", "authPriv": "fixturePriv"}


def packet_metadata(packet):
    top = list(items(next(items(packet))[1]))
    version = int.from_bytes(top[0][1], "big")
    result = {"version": version, "bytes": len(packet)}
    pdu = None
    if version == 3:
        header = list(items(top[1][1]))
        usm = list(items(next(items(top[2][1]))[1]))
        result.update(msgid=int.from_bytes(header[0][1], "big"), flags=int.from_bytes(header[2][1], "big"),
                      engine_id=usm[0][1].hex(), boots=int.from_bytes(usm[1][1], "big"),
                      engine_time=int.from_bytes(usm[2][1], "big"))
        if top[3][0] == 0x30:
            scoped = list(items(top[3][1]))
            result.update(context_engine_id=scoped[0][1].hex(), context=scoped[1][1].decode())
            pdu = scoped[2]
    else:
        pdu = top[2]
    if pdu:
        fields = list(items(pdu[1]))
        result.update(pdu=pdu[0], id=int.from_bytes(fields[0][1], "big", signed=True),
                      error=int.from_bytes(fields[1][1], "big"),
                      numeric_oids=[oid_text(next(items(binding))[1]) for _, binding, _ in items(fields[3][1])])
        result["varbinds"] = []
        for _, binding, _ in items(fields[3][1]):
            parts = list(items(binding))
            kind, value, _ = parts[1]
            value = (int.from_bytes(value, "big", signed=kind == 2) if kind in (2, 0x41, 0x42, 0x43) else
                     value.decode(errors="backslashreplace") if kind == 4 else value.hex())
            result["varbinds"].append({"oid": oid_text(parts[0][1]), "type": kind, "value": value})
    return result


def foreign_report_id(packet):
    """Rewrite an unauthenticated report's request ID from 0 to 5, keeping its length."""
    start = packet.rfind(b"\xa8")
    field = packet.find(b"\x02\x01\x00", start)
    if start < 0 or field < 0 or field - start > 4:
        raise ValueError("Report request ID not found")
    return packet[:field + 2] + b"\x05" + packet[field + 3:]


class Proxy:
    def __init__(self, work, port):
        self.front = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.back = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.front.bind(("127.0.0.1", 0))
        self.back.connect(("127.0.0.1", port))
        self.port = self.front.getsockname()[1]
        self.records, self.errors, self.clients = [], [], {}
        self.mode, self.pdu = "normal", None
        self.held, self.released = [], []
        self.lock = threading.Lock()
        self.closed = False
        self.log = (work / "wire.jsonl").open("w")
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            while not self.stop.is_set():
                with self.lock:
                    released, self.released = self.released, []
                for packet, key, address, request_pdu in released:
                    self.clients[key] = (address, request_pdu)
                    self.back.send(packet)
                    metadata = packet_metadata(packet)
                    metadata.update(event="release", action="forward", time=time.monotonic_ns())
                    self.record(metadata)
                ready, _, _ = select.select([self.front, self.back], [], [], 0.05)
                for sock in ready:
                    packet, address = sock.recvfrom(65535)
                    metadata = packet_metadata(packet)
                    key = (metadata["version"], metadata.get("msgid", metadata.get("id")))
                    request = sock is self.front
                    metadata.update(event="request" if request else "response", time=time.monotonic_ns())
                    destination = self.clients.get(key) if not request else None
                    request_pdu = metadata.get("pdu") if request else destination[1] if destination else None
                    with self.lock:
                        mode = self.mode if self.pdu is None or self.pdu == request_pdu else "normal"
                    drop = mode == ("drop-requests" if request else "drop-replies")
                    hold = request and mode == "hold-requests"
                    metadata["action"] = "drop" if drop else "hold" if hold else "forward"
                    if not request and mode == "report-foreign-id" and metadata.get("pdu") == 0xA8 \
                            and metadata.get("id") == 0:
                        packet = foreign_report_id(packet)
                        metadata["action"] = "forward-foreign-id"
                    if not request and destination is None:
                        metadata["action"] = "unmatched"
                    self.record(metadata)
                    if request:
                        if hold:
                            with self.lock:
                                self.held.append((packet, key, address, request_pdu))
                        elif not drop:
                            self.clients[key] = (address, request_pdu)
                            self.back.send(packet)
                    elif destination:
                        del self.clients[key]
                        if not drop:
                            self.front.sendto(packet, destination[0])
        except BaseException as error:
            self.errors.append(repr(error))

    def record(self, metadata):
        self.records.append(metadata)
        self.log.write(json.dumps(metadata) + "\n")
        self.log.flush()

    def fault(self, mode, pdu=None):
        if mode not in ("normal", "drop-requests", "drop-replies", "hold-requests", "report-foreign-id"):
            raise ValueError("Unknown UDP fault mode")
        with self.lock:
            self.mode, self.pdu = mode, pdu

    def release(self):
        with self.lock:
            self.released.extend(self.held)
            self.held.clear()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stop.set()
        self.thread.join(timeout=2)
        self.front.close()
        self.back.close()
        self.log.close()
        if self.thread.is_alive():
            raise AssertionError("UDP observer did not stop")
        if self.errors:
            raise AssertionError("UDP observer errors: " + repr(self.errors))


class Agent:
    def __init__(self, work, profile, writable=False):
        self.work = work / "agent"
        self.work.mkdir(mode=0o700)
        (self.work / "state").mkdir(mode=0o700)
        self.executable = shutil.which("snmpd")
        if not self.executable or not shutil.which("snmpget"):
            raise RuntimeError("Protocol suite requires real snmpd and snmpget in PATH")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reserve:
            reserve.bind(("127.0.0.1", 0))
            self.port = reserve.getsockname()[1]
        self.auth_type = profile["auth_type"]
        self.priv_type = profile["priv_type"]
        self.values_path = self.work / "values.json"
        extension = ""
        if writable:
            write_json(self.values_path, {"values": {"5": 500, "6": 600, "7": "initial"}, "reject_set": False})
            extension = f"pass_persist .1.3.6.1.4.1.55555 {sys.executable} {ROOT}/tests/agent_values.py {self.values_path} {self.work}/writes.jsonl\n"
        config = self.work / "snmpd.conf"
        config.write_text(f"agentaddress udp:127.0.0.1:{self.port}\nengineID fixture-agent\n"
                          "rwcommunity public 127.0.0.1\nsysName fixture-agent\n" +
                          "".join(f"createUser {user} {self.auth_type} {AUTH} {self.priv_type} {PRIV}\n"
                                  f"rwuser {user} {level}\n"
                                  for user, level in zip(USERS.values(), ("noauth", "auth", "priv"))) + extension)
        config.chmod(0o600)
        self.env = dict(os.environ, SNMP_PERSISTENT_DIR=str(self.work / "state"),
                        SNMPCONFPATH=str(self.work), MIBS="")
        self.log = (self.work / "snmpd.log").open("w")
        self.process = None
        try:
            self.config = config
            self.process = subprocess.Popen([self.executable, "-f", "-Lo", "-C", "-c", str(config),
                                             "-p", str(self.work / "snmpd.pid"), "-r"],
                                            env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + profile["action_timeout"]
            while time.monotonic() < deadline and self.process.poll() is None:
                result = self.client("2c", None, NAME)
                if result.returncode == 0 and "fixture-agent" in result.stdout:
                    write_json(self.work / "identity.json", {
                        "executable": self.executable, "sha256": digest(self.executable),
                        "version": subprocess.check_output([self.executable, "-v"], text=True, stderr=subprocess.STDOUT),
                        "pid": self.process.pid, "port": self.port, "auth_type": self.auth_type,
                        "priv_type": self.priv_type, "config_sha256": digest(config),
                    })
                    return
                time.sleep(0.02)
            raise AssertionError("Real snmpd failed readiness; evidence: " + str(self.work))
        except BaseException:
            self.close()
            raise

    def client(self, version, level, oid):
        security = ["-c", "public"] if version != "3" else ["-l", level, "-u", USERS[level]]
        if level in ("authNoPriv", "authPriv"):
            security += ["-a", self.auth_type, "-A", AUTH]
        if level == "authPriv":
            security += ["-x", self.priv_type, "-X", PRIV]
        return subprocess.run(["snmpget", "-v", version, *security, "-t", "0.2", "-r", "0", "-On",
                               f"127.0.0.1:{self.port}", oid], env=self.env, text=True,
                              capture_output=True, timeout=3)

    def restart(self, engine_id, boots):
        """Restart the real agent with the same engine ID and a higher engineBoots."""
        self.process.terminate()
        self.process.wait(timeout=3)
        config = self.work / "snmpd-restart.conf"
        config.write_text(self.config.read_text() + f"oldEngineID 0x{engine_id}\nengineBoots {boots}\n")
        config.chmod(0o600)
        self.process = subprocess.Popen([self.executable, "-f", "-Lo", "-C", "-c", str(config),
                                         "-p", str(self.work / "snmpd.pid"), "-r"],
                                        env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and self.process.poll() is None:
            if self.client("2c", None, NAME).returncode == 0:
                return
            time.sleep(0.05)
        raise AssertionError("Restarted snmpd failed readiness; evidence: " + str(self.work))

    def ioc_config(self, level):
        config = self.work / "ioc-v3.conf"
        lines = ["securityName " + USERS[level], "securityLevel " + level]
        if level in ("authNoPriv", "authPriv"):
            lines += ["authType " + self.auth_type, "authPassPhrase " + AUTH]
        if level == "authPriv":
            lines += ["privType " + self.priv_type, "privPassPhrase " + PRIV]
        config.write_text("\n".join(lines) + "\n")
        config.chmod(0o600)
        return config

    def close(self):
        forced = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
                forced = True
        self.log.close()
        write_json(self.work / "exit.json", {"exit_code": self.process.returncode if self.process else None,
                                            "forced": forced})
        if forced:
            raise AssertionError("Native agent did not stop within the shutdown bound")
