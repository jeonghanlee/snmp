"""Exercise bounded native batches after observed real host contention."""

from collections import Counter

from request_cases import ScenarioTest


CASES = ("one_limit_twenty", "twenty_limit_twenty", "twenty_one_limit_twenty",
         "one_limit_one", "twenty_limit_one", "twenty_one_limit_one",
         "shared_limit_twenty", "shared_limit_one", "communities_limit_twenty", "communities_limit_one")
CHUNK_CYCLES = 25


class BatchTest(ScenarioTest):
    def batches(self, count, limit, variant="distinct"):
        observed_sizes = []
        for offset in range(0, self.cycles(), CHUNK_CYCLES):
            with self.scenario(f"batch-{offset}", fixture="batch.db", max_oids=limit) as s:
                for cycle in range(min(CHUNK_CYCLES, self.cycles() - offset)):
                    first = len(s.peer.requests)
                    s.peer.hold = True
                    s.put("Block.PROC")
                    s.wait(lambda: len(s.peer.held) == 1, "host occupied by the blocker")
                    self.assertEqual(s.peer.requests[-1]["oids"], [99])
                    if variant == "shared":
                        records, trigger = {"R1": 1, "Shared": 1}, "SharedPair"
                    elif variant == "communities":
                        records, trigger = {"R1": 1, "Other": 1}, "Groups"
                    else:
                        records, trigger = {"R" + str(n): n for n in range(1, count + 1)}, "Many" + str(count)
                    s.put(trigger + ".PROC")
                    pending = s.runtime.get_many([field for name in records
                                                  for field in (name + ".PACT", "Audit" + name)])
                    for name in records:
                        self.assertEqual(pending[name + ".PACT"], "1")
                        self.assertEqual(pending["Audit" + name], str(cycle))
                    self.assertEqual(len(s.peer.requests), first + 1, "Host serialization was bypassed")
                    s.peer.hold = False
                    s.peer.release()
                    s.done_many(dict(Block=199, **{name: 100 + oid for name, oid in records.items()}), cycle + 1)
                    requests = s.peer.requests[first + 1:]
                    self.assertTrue(requests)
                    for request in requests:
                        oids = request["oids"]
                        self.assertLessEqual(len(oids), limit)
                        self.assertEqual(len(oids), len(set(oids)), "Duplicate wire OID")
                        observed_sizes.append(len(oids))
                    actual = Counter(oid for request in requests for oid in request["oids"])
                    expected = Counter({1: 2}) if variant == "communities" else Counter(set(records.values()))
                    self.assertEqual(actual, expected)
                    if variant == "communities":
                        self.assertEqual(sorted(request["community"] for request in requests), ["public", "separate"])
                    else:
                        self.assertTrue(all(request["community"] == "public" for request in requests))
            blockers = s.events("Block", "result")
            for name in records:
                for accepted, claimed, blocker in zip(s.events(name, "accepted"), s.events(name, "claimed"), blockers):
                    self.assertLess(accepted["time"], blocker["time"], "Missing queued-work precondition")
                    self.assertGreater(claimed["time"], blocker["time"], "Membership claimed before host release")
                for dispatched, blocker in zip(s.events(name, "dispatch"), blockers):
                    self.assertLess((dispatched["time"] - blocker["time"]) / 1e9,
                                    s.runtime.config["profile"]["limits"]["healthy_max_seconds"])
            if variant == "shared":
                for one, shared in zip(s.events("R1", "dispatch"), s.events("Shared", "dispatch")):
                    self.assertEqual(one["extra"], shared["extra"], "Pre-dispatch waiters did not share acquisition")
        if variant == "distinct" and count >= limit:
            self.assertIn(limit, observed_sizes, "The configured full-batch boundary was not exercised")

    def test_one_limit_twenty(self):
        self.batches(1, 20)

    def test_twenty_limit_twenty(self):
        self.batches(20, 20)

    def test_twenty_one_limit_twenty(self):
        self.batches(21, 20)

    def test_one_limit_one(self):
        self.batches(1, 1)

    def test_twenty_limit_one(self):
        self.batches(20, 1)

    def test_twenty_one_limit_one(self):
        self.batches(21, 1)

    def test_shared_limit_twenty(self):
        self.batches(1, 20, "shared")

    def test_shared_limit_one(self):
        self.batches(1, 1, "shared")

    def test_communities_limit_twenty(self):
        self.batches(1, 20, "communities")

    def test_communities_limit_one(self):
        self.batches(1, 1, "communities")
