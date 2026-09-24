#!/usr/bin/env python3
"""Build an immutable baseline or candidate copy without changing an installation."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", help="Git revision for an unmodified baseline")
    parser.add_argument("--sanitizer", choices=("address",), help="Instrument the isolated module and IOC")
    args = parser.parse_args()
    base, output = args.base.resolve(), args.output.resolve()
    if not (base / "configure/CONFIG_BASE_VERSION").is_file():
        parser.error("--base must identify an installed EPICS Base")
    if any(char.isspace() for char in str(base) + str(output)):
        parser.error("EPICS build paths must not contain whitespace")
    output.mkdir(parents=True, exist_ok=False)
    revision = args.revision or "HEAD"
    commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", revision], text=True).strip()
    if args.revision:
        archive = subprocess.check_output(["git", "-C", str(ROOT), "archive", args.revision])
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            for member in source.getmembers():
                name = Path(member.name)
                if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
                    raise RuntimeError("Unsupported archive member: " + member.name)
            source.extractall(output)
        diff = b""
    else:
        names = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-co", "--exclude-standard", "-z"])
        for name in sorted(set(names.split(b"\0")) - {b""}):
            relative = Path(os.fsdecode(name))
            source = ROOT / relative
            if not source.is_file():
                continue
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        diff = subprocess.check_output(["git", "-C", str(ROOT), "diff", "HEAD", "--binary"])
    files = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}
    manifest = {
        "started_at": datetime.now(timezone.utc).isoformat(), "source_commit": commit,
        "argv": [sys.executable] + sys.argv, "cwd": os.getcwd(), "sanitizer": args.sanitizer,
        "source_kind": "git-archive" if args.revision else "working-copy",
        "dirty_diff_sha256": hashlib.sha256(diff).hexdigest(), "sources": files,
        "epics_base": str(base), "base_config_sha256": digest(base / "configure/CONFIG_BASE_VERSION"),
    }
    (output / "configure/RELEASE.local").write_text(f"EPICS_BASE={base}\n")
    configuration = "CHECK_RELEASE=NO\nPROD_LDFLAGS += -Wl,--enable-new-dtags\n"
    if args.sanitizer:
        flags = "-fsanitize=address -fno-omit-frame-pointer"
        configuration += f"USR_CFLAGS += {flags}\nUSR_CXXFLAGS += {flags}\nUSR_LDFLAGS += -fsanitize=address\n"
    (output / "configure/CONFIG_SITE.local").write_text(configuration)
    evidence = output / "work"
    evidence.mkdir(exist_ok=True)
    environment = dict(os.environ)
    environment.pop("INSTALL_LOCATION", None)
    with (evidence / "build.log").open("w") as log:
        result = subprocess.run(["make", "-j4"], cwd=output, env=environment,
                                stdout=log, stderr=subprocess.STDOUT)
    manifest["build_exit"] = result.returncode
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    artifacts = [p for pattern in ("bin/*/snmp*", "lib/*/libdevSnmp*", "dbd/*.dbd")
                 for p in output.glob(pattern) if p.is_file()]
    manifest["artifacts"] = {str(p.relative_to(output)): digest(p) for p in sorted(artifacts)}
    (output / "build-inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(output / "build-inputs.json", flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
