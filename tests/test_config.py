"""Exercise named SNMPv3 profiles, endpoints and engine identity through the actual IOC."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from ioc import IOC, ROOT, settings, write_json
from snmp_agent import AUTH, NAME, PRIV, USERS, Agent, Proxy


CASES = ("named_endpoint_reads", "security_levels", "sha2_algorithms", "invalid_configuration",
         "iocsh_error_propagation", "security_failures", "engine_identity", "engine_boundaries")
SENTINEL = "sentinel-secret-7d41c9"
AGENT_ENGINE = "80001f8804" + b"fixture-agent".hex()
WRONG_ENGINE = "80001f8804" + b"another-agent".hex()
SHA2 = ("SHA-224", "SHA-256", "SHA-384", "SHA-512")
LEVEL_FLAGS = {"noAuthNoPriv": 0, "authNoPriv": 1, "authPriv": 3}
VALUE = r'\"fixture-agent\"'


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.config = settings()
        self.profile = self.config["profile"]
        self.work = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=self.config.get("output")))
        print(f"Evidence: {self.work}", flush=True)
        self.files = self.work / "config"
        self.files.mkdir(mode=0o700)
        self.runtimes = 0

    def agent(self, auth_type=None):
        base = self.fresh("agent")
        agent = Agent(base, dict(self.profile, auth_type=auth_type or self.profile["auth_type"]))
        self.addCleanup(agent.close)
        proxy = Proxy(base, agent.port)
        self.addCleanup(proxy.close)
        return agent, proxy

    def fresh(self, stem):
        index = 0
        while (self.work / f"{stem}-{index}").exists():
            index += 1
        path = self.work / f"{stem}-{index}"
        path.mkdir()
        return path

    def write(self, name, text, mode=0o600):
        path = self.files / name
        path.write_text(text)
        path.chmod(mode)
        return path

    def profile_file(self, name, level, user, auth=None, priv=None, context=None, auth_pass=AUTH, priv_pass=PRIV,
                     extra=""):
        lines = [f"securityName {user}", f"securityLevel {level}"]
        if level != "noAuthNoPriv":
            lines.append(f"authType {auth or self.profile['auth_type']}")
            credentials = [f"authPassPhrase {auth_pass}"]
            if level == "authPriv":
                credentials.append(f"privPassPhrase {priv_pass}")
            lines.append(f"credentialFile {self.write(name + '.keys', chr(10).join(credentials) + chr(10))}")
        if level == "authPriv":
            lines.append(f"privType {priv or 'AES128'}")
        if context is not None:
            lines.append(f"contextName {context}")
        return self.write(name + ".conf", "\n".join(lines) + "\n" + extra, 0o644)

    def runtime(self, lines):
        work = self.fresh("ioc")
        runtime = IOC(work, ['devSnmpSetParam("RequestTrace", 1)',
                             f'devSnmpSetParam("RequestTimeoutMSec", {self.profile["request_timeout_ms"]})',
                             f'devSnmpSetParam("SessionTimeout", {self.profile["session_timeout_us"]})',
                             f'devSnmpSetParam("SessionRetries", {self.profile["session_retries"]})'] + lines)
        self.addCleanup(runtime.close)
        return runtime

    def endpoint_records(self, endpoint, prefix, community=None):
        macros = f"P=SNMPTEST:,R={prefix},EP={endpoint}" + (f",COMM={community}" if community else "")
        return f'dbLoadRecords("{ROOT}/tests/endpoint.db", "{macros}")'

    def read(self, runtime, prefix):
        """Process one request-mode read and wait for its audited completion."""
        before = int(float(runtime.get(f"{prefix}AuditName")))
        runtime.put(f"{prefix}Name.PROC")
        runtime.wait_for(lambda: int(float(runtime.get(f"{prefix}AuditName"))) > before and
                         runtime.get(f"{prefix}Name.PACT") == "0", f"{prefix}Name completion")
        return runtime.get(f"{prefix}Name"), runtime.get(f"{prefix}Name.SEVR")

    def log(self, runtime):
        return (runtime.work / "ioc.log").read_text()

    def assert_no_secret(self, runtime):
        text = self.log(runtime) + (runtime.work / "st.cmd").read_text()
        for secret in (AUTH, PRIV, SENTINEL):
            self.assertNotIn(secret, text, "A secret reached the IOC log or startup file")

    def assert_logged(self, runtime, fragments):
        """Wait for every expected message; IOC output reaches the log as it is flushed."""
        missing = list(fragments)
        def present():
            text = self.log(runtime)
            missing[:] = [fragment for fragment in fragments if fragment not in text]
            return not missing
        try:
            runtime.wait_for(present, "expected configuration errors")
        finally:
            write_json(runtime.work / "expected-errors.json", {"expected": fragments, "missing": missing})

    def command(self, runtime, line, fragment):
        before = len(self.log(runtime))
        runtime.process.stdin.write(line + "\n")
        runtime.process.stdin.flush()
        runtime.wait_for(lambda: fragment in self.log(runtime)[before:], f"response to {line}")

    def test_named_endpoint_reads(self):
        agent, proxy = self.agent()
        profile = self.profile_file("read", "authPriv", USERS["authPriv"])
        runtime = self.runtime([
            f'devSnmpLoadV3Profile("pduRead", "{profile}")',
            f'devSnmpDefineEndpoint("pduARead", "udp:{self.proxied(proxy)}", "pduRead")',
            'devSnmpSetEndpointParam("pduARead", "timeoutMSec", "2000")',
            'devSnmpSetEndpointParam("pduARead", "retries", "0")',
            'devSnmpSetEndpointParam("pduARead", "maxOidsPerReq", "20")',
            self.endpoint_records("pduARead", "A:"),
            f'dbLoadRecords("{ROOT}/tests/snmpv3.db", "P=SNMPTEST:,R=Legacy:,HOST={self.proxied(proxy)}")'])
        self.assertEqual(self.read(runtime, "A:"), (VALUE, "0"))
        runtime.wait_for(lambda: runtime.get("A:LegacyName") == VALUE, "legacy polled read through the endpoint")
        self.assertEqual(self.read(runtime, "Legacy:"), (VALUE, "0"), "An unchanged legacy link still works")
        self.assertNotIn("devSnmp ERROR", self.log(runtime))
        v3 = [r for r in proxy.records if r["event"] == "request" and r["version"] == 3 and r["engine_id"]]
        self.assertTrue(v3 and all(r["flags"] & 3 == 3 for r in v3), "Endpoint traffic is authPriv")
        self.assert_no_secret(runtime)

    def proxied(self, proxy):
        return f"127.0.0.1:{proxy.port}"

    def test_security_levels(self):
        agent, proxy = self.agent()
        lines = []
        for level, user in USERS.items():
            path = self.profile_file(level, level, user)
            lines += [f'devSnmpLoadV3Profile("{level}", "{path}")',
                      f'devSnmpDefineEndpoint("{level}", "udp:{self.proxied(proxy)}", "{level}")',
                      self.endpoint_records(level, f"{level}:")]
        runtime = self.runtime(lines)
        for level in USERS:
            self.assertEqual(self.read(runtime, f"{level}:"), (VALUE, "0"), level)
        engines = [r for r in proxy.records if r["event"] == "request" and r["version"] == 3 and r["engine_id"]]
        observed = {r["flags"] & 3 for r in engines}
        self.assertEqual(observed, set(LEVEL_FLAGS.values()), "Each profile's own level reached the wire")
        self.assert_no_secret(runtime)

    def test_sha2_algorithms(self):
        results = {}
        for algorithm in SHA2:
            agent, proxy = self.agent(algorithm)
            profile = self.profile_file(algorithm, "authPriv", USERS["authPriv"], auth=algorithm)
            runtime = self.runtime([f'devSnmpLoadV3Profile("p", "{profile}")',
                                    f'devSnmpDefineEndpoint("e", "udp:{self.proxied(proxy)}", "p")',
                                    self.endpoint_records("e", "S:")])
            results[algorithm] = self.read(runtime, "S:")
            runtime.close()
            self.assert_no_secret(runtime)
            agent.close()
        write_json(self.work / "sha2-results.json", results)
        self.assertEqual(results, {algorithm: (VALUE, "0") for algorithm in SHA2})

    def test_invalid_configuration(self):
        agent, proxy = self.agent()
        target = f"udp:{self.proxied(proxy)}"
        good = self.profile_file("good", "authPriv", USERS["authPriv"])
        other = self.profile_file("other", "authPriv", USERS["authPriv"], auth_pass=SENTINEL)
        big = self.write("big.conf", "# " + "x" * 17000 + "\n", 0o644)
        long_line = self.write("long.conf", "securityName " + "u" * 5000 + "\n", 0o644)
        nul = self.files / "nul.conf"
        nul.write_bytes(b"securityName a\0b\nsecurityLevel noAuthNoPriv\n")
        link = self.files / "link.keys"
        link.symlink_to(self.files / "good.keys")
        readable = self.write("readable.keys", f"authPassPhrase {SENTINEL}\nprivPassPhrase {SENTINEL}\n", 0o640)
        short = self.write("short.keys", "authPassPhrase short\nprivPassPhrase shortpriv\n")
        fifo = self.files / "fifo.keys"
        os.mkfifo(fifo, 0o600)
        unterminated = self.write("unterminated.keys", f"authPassPhrase {SENTINEL}\nprivPassPhrase abcdefgh")
        legacy_leak = self.files / "leak-v3.conf"
        legacy_leak.write_text(f"defSecurityName leakuser\nauthPassPhrase\t{SENTINEL} with space\n"
                               f"bogus\t{SENTINEL} tail\nprivPassPhrase " + SENTINEL * 80 + "\n")
        legacy_leak.chmod(0o600)
        cases = [
            ('devSnmpLoadV3Profile("good", "{}")'.format(good), None),
            ('devSnmpLoadV3Profile("good", "{}")'.format(good), "duplicate profile good"),
            ('devSnmpLoadV3Profile("1bad", "{}")'.format(good), "invalid profile name"),
            ('devSnmpLoadV3Profile("rel", "relative.conf")', "profile file path must be absolute"),
            ('devSnmpLoadV3Profile("big", "{}")'.format(big), "profile file exceeds 16 KiB"),
            ('devSnmpLoadV3Profile("long", "{}")'.format(long_line), "line 1: line exceeds 4096 bytes"),
            ('devSnmpLoadV3Profile("nul", "{}")'.format(nul), "profile file contains a NUL byte"),
        ]
        profile_errors = [
            ("missing", "securityName u\n", "profile requires securityName and securityLevel"),
            ("level", "securityName u\nsecurityLevel secure\n", "profile securityLevel is not noAuthNoPriv"),
            ("unknown", "securityName u\nsecurityLevel noAuthNoPriv\nbogus x\n", "profile file line 3: unknown field"),
            ("inline", f"securityName u\nsecurityLevel noAuthNoPriv\nauthPassPhrase {SENTINEL}\n",
             "profile file line 3: unknown field"),
            ("dupkey", "securityName u\nsecurityName v\nsecurityLevel noAuthNoPriv\n", "profile file line 2: duplicate field securityName"),
            ("longname", "securityName " + "n" * 33 + "\nsecurityLevel noAuthNoPriv\n", "profile securityName exceeds 32 bytes"),
            ("md5", f"securityName u\nsecurityLevel authNoPriv\nauthType MD5\ncredentialFile {self.files}/good.keys\n",
             "profile authType is not permitted by policy"),
            ("aes256", f"securityName u\nsecurityLevel authPriv\nauthType SHA\nprivType AES256\n"
                       f"credentialFile {self.files}/good.keys\n", "profile privType is not permitted by policy"),
            ("privlevel", f"securityName u\nsecurityLevel authNoPriv\nauthType SHA\nprivType AES128\n"
                          f"credentialFile {self.files}/good.keys\n", "profile privType is used only by authPriv"),
            ("credlevel", f"securityName u\nsecurityLevel noAuthNoPriv\ncredentialFile {self.files}/good.keys\n",
             "profile credentialFile is not used by noAuthNoPriv"),
            ("noauth", "securityName u\nsecurityLevel authNoPriv\n", "profile requires authType"),
            ("symlink", f"securityName u\nsecurityLevel authPriv\nauthType SHA\nprivType AES128\n"
                        f"credentialFile {link}\n", "credential file is a symbolic link"),
            ("readable", f"securityName u\nsecurityLevel authPriv\nauthType SHA\nprivType AES128\n"
                         f"credentialFile {readable}\n", "credential file must not grant group or other permissions"),
            ("short", f"securityName u\nsecurityLevel authPriv\nauthType SHA\nprivType AES128\n"
                      f"credentialFile {short}\n", "credential authPassPhrase must be 8 through 1024 bytes"),
            ("fifo", f"securityName u\nsecurityLevel authPriv\nauthType SHA\nprivType AES128\n"
                     f"credentialFile {fifo}\n", "credential file is not a regular file"),
            ("unterminated", f"securityName u\nsecurityLevel authPriv\nauthType SHA\nprivType AES128\n"
                             f"credentialFile {unterminated}\n",
             "credential file line 2: line is not terminated by a newline"),
            ("noprofilenewline", "securityName u\nsecurityLevel noAuthNoPriv",
             "profile file line 2: line is not terminated by a newline"),
        ]
        for name, text, fragment in profile_errors:
            path = self.write(name + ".conf", text, 0o644)
            cases.append((f'devSnmpLoadV3Profile("{name}", "{path}")', f"profile {name}: {fragment}"))
        cases += [
            ('devSnmpLoadV3Profile("other", "{}")'.format(other), None),
            (f'devSnmpDefineEndpoint("ep", "{target}", "good")', None),
            (f'devSnmpDefineEndpoint("ep", "{target}", "good")', "duplicate endpoint ep"),
            (f'devSnmpDefineEndpoint("nop", "{target}", "absent")', "endpoint nop: unknown profile"),
            ('devSnmpDefineEndpoint("spaced", "udp:127.0.0.1 1", "good")', "endpoint spaced: invalid address"),
            (f'devSnmpDefineEndpoint("clash", "{target}", "other")', "endpoint clash: endpoint profile conflicts"),
            (f'devSnmpDefineEndpoint("bad", "{target}", "good")', None),
            ('devSnmpSetEndpointParam("bad", "colour", "red")', "endpoint bad: unknown parameter"),
            ('devSnmpSetEndpointParam("absent", "retries", "1")', "unknown endpoint"),
        ]
        for field, value, fragment in [("timeoutMSec", "0", "timeoutMSec must be 1 through 60000"),
                                       ("timeoutMSec", "60001", "timeoutMSec must be 1 through 60000"),
                                       ("timeoutMSec", "1.5", "timeoutMSec must be 1 through 60000"),
                                       ("timeoutMSec", "+5", "timeoutMSec must be 1 through 60000"),
                                       ("retries", "6", "retries must be 0 through 5"),
                                       ("maxOidsPerReq", "1025", "maxOidsPerReq must be 1 through 1024"),
                                       ("securityEngineID", "0x", "securityEngineID needs an even number"),
                                       ("securityEngineID", "0x123", "securityEngineID needs an even number"),
                                       ("securityEngineID", "zz00112233", "securityEngineID contains a non-hex"),
                                       ("securityEngineID", "00112233", "securityEngineID must be 5 through 32"),
                                       ("securityEngineID", "01" * 33, "securityEngineID must be 5 through 32"),
                                       ("securityEngineID", "00" * 5, "securityEngineID must not be all zero or all 0xFF"),
                                       ("contextEngineID", "ff" * 8, "contextEngineID must not be all zero or all 0xFF")]:
            cases.append((f'devSnmpSetEndpointParam("bad", "{field}", "{value}")', f"endpoint bad: {fragment}"))
        cases += [
            ('devSnmpSetSnmpV3Param("endpoint:ep", "securityName", "u")', "'endpoint:ep' is a reserved named-endpoint key"),
            ('devSnmpSetMaxOidsPerReq("endpoint:other", 5)', "'endpoint:other' is a reserved named-endpoint key"),
            ('devSnmpSetSnmpVersion("leak.invalid", "SNMP_VERSION_3")', None),
            ('devSnmpSetSnmpVersion("missing.invalid", "SNMP_VERSION_3")', None),
            ('devSnmpSetSnmpV3Param("missing.invalid", "securityEngineID")',
             "host 'missing.invalid' SNMPv3 parameter call is missing its value"),
            (f'devSnmpSetSnmpV3ConfigFile("leak.invalid", "{legacy_leak}")',
             "unknown SNMPv3 parameter at config file line 3 in"),
            (f'devSnmpSetSnmpV3ConfigFile("leak.invalid", "{legacy_leak}")',
             "SNMPv3 config file line 4 in"),
            ('devSnmpSetSnmpVersion("badversion.invalid", "SNMP_VERSION_9")', "unknown SNMP version"),
            (f'devSnmpSetSnmpVersion("{self.proxied(proxy)}", "SNMP_VERSION_3")', None),
            (f'devSnmpSetSnmpV3Param("{self.proxied(proxy)}", "securityEngineID", "0x12")',
             "securityEngineID needs an even number"),
        ]
        lines = [line for line, _ in cases]
        lines += [self.endpoint_records("ep", "Bad:", community="public"),
                  self.endpoint_records("bad", "Rejected:"),
                  self.endpoint_records("absent", "Unknown:"),
                  self.endpoint_records("ep", "Good:"),
                  f'dbLoadRecords("{ROOT}/tests/snmpv3.db", "P=SNMPTEST:,R=Legacy:,HOST={self.proxied(proxy)}")',
                  f'dbLoadRecords("{ROOT}/tests/snmpv3.db", "P=SNMPTEST:,R=Version:,HOST=badversion.invalid")',
                  f'dbLoadRecords("{ROOT}/tests/snmpv3.db", "P=SNMPTEST:,R=Missing:,HOST=missing.invalid")']
        runtime = self.runtime(lines)
        self.assert_logged(runtime, [fragment for _, fragment in cases if fragment] + [
            "Bad:Name: named endpoint link requires the '-' community placeholder",
            "Unknown:Name: unknown named endpoint",
            "Rejected:Name: named endpoint has invalid startup configuration",
            "Legacy:Name not bound: host '" + self.proxied(proxy) + "' has invalid startup configuration",
            "Version:Name not bound: host 'badversion.invalid' has invalid startup configuration",
            "Missing:Name not bound: host 'missing.invalid' has invalid startup configuration"])
        self.assertEqual(self.read(runtime, "Good:"), (VALUE, "0"), "Valid definitions still work")
        for prefix in ("Bad:", "Unknown:", "Rejected:", "Legacy:", "Version:", "Missing:"):
            self.assertEqual(self.read(runtime, prefix)[1], "3", f"{prefix} binding failed explicitly")
        for line, fragment in [
                ('devSnmpLoadV3Profile("late", "{}")'.format(good), "configuration is frozen after iocInit"),
                (f'devSnmpDefineEndpoint("late", "{target}", "good")', "configuration is frozen after iocInit"),
                ('devSnmpSetEndpointParam("ep", "retries", "1")', "configuration is frozen after iocInit"),
                (f'devSnmpSetSnmpV3Param("{self.proxied(proxy)}", "securityName", "u")', "rejected")]:
            self.command(runtime, line, fragment)
        self.assert_no_secret(runtime)

    def test_iocsh_error_propagation(self):
        ioc = Path(self.config["ioc"]).resolve()
        top = ioc.parents[2]
        outcomes = {}
        for label, command in (("failure", 'devSnmpLoadV3Profile("p", "relative.conf")'),
                               ("success", 'devSnmpSetParam("RequestTrace", 1)')):
            script = self.write(f"{label}.cmd", "\n".join([
                f'dbLoadDatabase("{top}/dbd/{ioc.name}.dbd")', f"{ioc.name}_registerRecordDeviceDriver(pdbbase)",
                "on error break", command, "echo REACHED_AFTER_COMMAND", "exit"]) + "\n", 0o644)
            env = dict(os.environ, SNMPCONFPATH=str(self.files), SNMP_PERSISTENT_DIR=str(self.files), MIBS="")
            result = subprocess.run([str(ioc), str(script)], cwd=top, env=env, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=30)
            outcomes[label] = {"exit_code": result.returncode, "out": result.stdout[-4000:],
                               "reached": "REACHED_AFTER_COMMAND" in result.stdout}
        write_json(self.work / "iocsh-outcomes.json", outcomes)
        self.assertFalse(outcomes["failure"]["reached"], "A failed command stops a script under on error break")
        self.assertIn("devSnmpLoadV3Profile: profile p: profile file path must be absolute", outcomes["failure"]["out"])
        self.assertTrue(outcomes["success"]["reached"], "A successful command does not set the shell error")
        for outcome in outcomes.values():
            for secret in (AUTH, PRIV, SENTINEL):
                self.assertNotIn(secret, outcome["out"])

    def test_security_failures(self):
        agent, proxy = self.agent()
        target = f"udp:{self.proxied(proxy)}"
        wrong = {
            "User": self.profile_file("user", "authPriv", "nosuchuser"),
            "Auth": self.profile_file("auth", "authPriv", USERS["authPriv"], auth_pass=SENTINEL),
            "Priv": self.profile_file("priv", "authPriv", USERS["authPriv"], priv_pass=SENTINEL),
            "Context": self.profile_file("context", "authPriv", USERS["authPriv"], context="nosuchcontext"),
        }
        lines = []
        for label, path in wrong.items():
            lines += [f'devSnmpLoadV3Profile("{label}", "{path}")',
                      f'devSnmpDefineEndpoint("{label}", "{target}", "{label}")',
                      f'devSnmpSetEndpointParam("{label}", "retries", "0")',
                      self.endpoint_records(label, f"{label}:")]
        runtime = self.runtime(lines)
        outcomes = {}
        for label in wrong:
            runtime.put(f"{label}:Name.PROC")
            runtime.wait_for(lambda: runtime.get(f"{label}:AuditName") == "1", f"{label} single completion")
            time.sleep(0.5)
            outcomes[label] = runtime.get_many([f"{label}:AuditName", f"{label}:Name.SEVR", f"{label}:Name.UDF"])
        write_json(self.work / "security-failures.json", outcomes)
        for label, values in outcomes.items():
            self.assertEqual(values[f"{label}:AuditName"], "1", f"{label}: exactly one completion")
            self.assertEqual(values[f"{label}:Name.SEVR"], "3", f"{label}: no false success")
            self.assertEqual(values[f"{label}:Name.UDF"], "1", f"{label}: no fresh value")
        oracle = agent.client("3", "authPriv", NAME)
        self.assertEqual(oracle.returncode, 0, "The native oracle reads with the correct secrets")
        runtime.close()
        corrected = self.profile_file("corrected", "authPriv", USERS["authPriv"])
        restarted = self.runtime([f'devSnmpLoadV3Profile("fixed", "{corrected}")',
                                  f'devSnmpDefineEndpoint("fixed", "{target}", "fixed")',
                                  self.endpoint_records("fixed", "Fixed:")])
        self.assertEqual(self.read(restarted, "Fixed:"), (VALUE, "0"), "Corrected startup succeeds")
        self.assert_no_secret(runtime)
        self.assert_no_secret(restarted)

    def test_engine_identity(self):
        agent, proxy = self.agent()
        host = self.proxied(proxy)
        target = f"udp:{host}"
        profile = self.profile_file("engine", "authPriv", USERS["authPriv"])
        legacy_file = self.write("legacy-v3.conf", (Path(agent.ioc_config("authPriv")).read_text() +
                                                    f"defSecurityEngineID {AGENT_ENGINE.upper()}\n"))
        runtime = self.runtime([
            f'devSnmpLoadV3Profile("p", "{profile}")',
            f'devSnmpDefineEndpoint("auto", "{target}", "p")',
            f'devSnmpDefineEndpoint("explicit", "{target}", "p")',
            f'devSnmpSetEndpointParam("explicit", "securityEngineID", "0X{AGENT_ENGINE.upper()}")',
            f'devSnmpSetEndpointParam("explicit", "contextEngineID", "{AGENT_ENGINE}")',
            f'devSnmpDefineEndpoint("wrong", "{target}", "p")',
            f'devSnmpSetEndpointParam("wrong", "securityEngineID", "0x{WRONG_ENGINE}")',
            f'devSnmpSetEndpointParam("wrong", "retries", "0")',
            f'devSnmpSetSnmpVersion("{host}", "SNMP_VERSION_3")',
            f'devSnmpSetSnmpV3ConfigFile("{host}", "{agent.ioc_config("authPriv")}")',
            f'devSnmpSetSnmpV3Param("{host}", "defSecurityEngineID", "0x{AGENT_ENGINE}")',
            f'devSnmpSetSnmpVersion("localhost:{proxy.port}", "SNMP_VERSION_3")',
            f'devSnmpSetSnmpV3ConfigFile("localhost:{proxy.port}", "{legacy_file}")',
            self.endpoint_records("auto", "Auto:"),
            self.endpoint_records("explicit", "Explicit:"),
            self.endpoint_records("wrong", "Wrong:"),
            f'dbLoadRecords("{ROOT}/tests/snmpv3.db", "P=SNMPTEST:,R=Setter:,HOST={host}")',
            f'dbLoadRecords("{ROOT}/tests/snmpv3.db", "P=SNMPTEST:,R=File:,HOST=localhost:{proxy.port}")'])
        results = {prefix: self.read(runtime, prefix) for prefix in ("Auto:", "Explicit:", "Setter:", "File:")}
        runtime.put("Wrong:Name.PROC")
        runtime.wait_for(lambda: runtime.get("Wrong:AuditName") == "1", "wrong engine completion")
        results["Wrong:"] = (runtime.get("Wrong:Name"), runtime.get("Wrong:Name.SEVR"))
        write_json(self.work / "engine-results.json", results)
        for prefix in ("Auto:", "Explicit:", "Setter:", "File:"):
            self.assertEqual(results[prefix], (VALUE, "0"), prefix)
        self.assertEqual(results["Wrong:"][1], "3", "A wrong security engine ID never rebinds silently")
        self.assertIn(WRONG_ENGINE, {r["engine_id"] for r in proxy.records if r["event"] == "request"},
                      "The configured wrong engine ID was sent as configured")
        self.assertNotIn("devSnmp ERROR", self.log(runtime))
        self.assert_no_secret(runtime)

    def test_engine_boundaries(self):
        results = {}
        for label, engine in (("five", "8000000501"), ("thirtytwo", "80" + "a5" * 31)):
            agent, proxy = self.agent()
            agent.restart(engine, 1)
            profile = self.profile_file(label, "authPriv", USERS["authPriv"])
            runtime = self.runtime([f'devSnmpLoadV3Profile("p", "{profile}")',
                                    f'devSnmpDefineEndpoint("e", "udp:{self.proxied(proxy)}", "p")',
                                    f'devSnmpSetEndpointParam("e", "securityEngineID", "{engine}")',
                                    self.endpoint_records("e", "B:")])
            result = self.read(runtime, "B:")
            requests = [r for r in proxy.records if r["event"] == "request" and r["version"] == 3]
            results[label] = {"engine_bytes": len(engine) // 2, "result": result,
                              "wire_engines": sorted({r["engine_id"] for r in requests}),
                              "errors": "devSnmp ERROR" in self.log(runtime)}
            runtime.close()
            self.assert_no_secret(runtime)
            agent.close()
        write_json(self.work / "engine-boundaries.json", results)
        for label, engine in (("five", "8000000501"), ("thirtytwo", "80" + "a5" * 31)):
            self.assertEqual(results[label]["result"], (VALUE, "0"), label)
            self.assertEqual(results[label]["wire_engines"], [engine],
                             f"{label}: every request carried the configured ID; no discovery request was sent")
            self.assertFalse(results[label]["errors"], f"{label}: the configured ID was accepted")
