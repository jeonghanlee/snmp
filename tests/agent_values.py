#!/usr/bin/env python3
"""Writable laboratory OIDs served through the real snmpd pass_persist interface."""

import json
from pathlib import Path
import sys
import time


PREFIX = ".1.3.6.1.4.1.55555."
KINDS = {5: "integer", 6: "integer", 7: "string"}


def main():
    state, log_path = map(Path, sys.argv[1:])
    while True:
        command = sys.stdin.readline().strip()
        if not command:
            return
        if command == "PING":
            print("PONG", flush=True)
            continue
        oid = sys.stdin.readline().strip()
        values = json.loads(state.read_text())
        known = {PREFIX + str(key) + ".0": key for key in KINDS}
        if command == "getnext":
            following = [name for name in known if tuple(map(int, name.strip('.').split('.'))) >
                         tuple(map(int, oid.strip('.').split('.')))]
            oid = min(following, key=lambda name: tuple(map(int, name.strip('.').split('.')))) if following else ""
        key = known.get(oid)
        if command in ("get", "getnext"):
            print(f"{oid}\n{KINDS[key]}\n{values['values'][str(key)]}" if key else "NONE", flush=True)
        elif command == "set":
            supplied = sys.stdin.readline().rstrip("\n")
            kind, _, value = supplied.partition(" ")
            error = None
            if key is None or values.get("reject_set"):
                error = "not-writable"
            elif kind != KINDS[key]:
                error = "wrong-type"
            elif kind == "integer":
                try:
                    value = int(value)
                except ValueError:
                    error = "wrong-value"
            elif kind == "string":
                try:
                    value = json.loads(value)
                    if not isinstance(value, str):
                        error = "wrong-value"
                except ValueError:
                    error = "wrong-value"
            if not error:
                values["values"][str(key)] = value
                temporary = state.with_suffix(".tmp")
                temporary.write_text(json.dumps(values) + "\n")
                temporary.replace(state)
            with log_path.open("a") as log:
                log.write(json.dumps({"time": time.monotonic_ns(), "oid": oid, "kind": kind,
                                      "supplied": supplied, "value": value, "error": error}) + "\n")
            print(error or "DONE", flush=True)
        else:
            raise RuntimeError("Unknown pass_persist command: " + command)


if __name__ == "__main__":
    main()
