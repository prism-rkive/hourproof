"""Regression tests for transient network failures (the second Base Sepolia attempt ended on a Wi-Fi drop:
"... client error (Connect): dns error: ... Temporary failure in name resolution"). Retries are bounded, use backoff,
and never create a second transaction: signing retries never broadcast, and every broadcast re-sends the SAME bytes.
Chain tests use a throwaway anvil with its PUBLIC dev keys; the outage is simulated around the `cast` calls."""
import shutil
import subprocess
import unittest
from unittest import mock

from hourproof import chain as chain_mod
from hourproof.chain import RETRY_DELAYS, Chain, ChainRevert, _transient, run, start_anvil, tool
from hourproof.config import Network, local_network

DNS_FAIL = ("Error: MPP HTTP request to https://sepolia.base.org/ failed: HTTP request failed: error sending request: "
            "error sending request: client error (Connect): dns error: error resolving DNS: failed to lookup address "
            "information: Temporary failure in name resolution")  # verbatim from run 20261017T132115Z
HAVE_FOUNDRY = all(shutil.which(t) for t in ("anvil", "cast"))


def failed(args, text=DNS_FAIL):
    return subprocess.CompletedProcess(args, 1, "", text)


class SleepRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, s):
        self.calls.append(s)


class PatternTests(unittest.TestCase):
    def test_the_observed_dns_failure_is_transient(self):
        self.assertTrue(_transient(DNS_FAIL))
        for t in ("network is unreachable", "No route to host", "connection refused", "error sending request: eof"):
            self.assertTrue(_transient(t), t)

    def test_contract_reverts_are_not_transient(self):
        for t in ('Error: Failed to estimate gas: server returned an error response: error code 3: execution '
                  'reverted, data: "0xc3b0d8cd": ProofRejected',
                  'execution reverted, data: "0xb0b82dc9…": BadIssuerSignature(0x6973…)',
                  "insufficient funds for gas * price + value"):
            self.assertFalse(_transient(t), t)

    def test_backoff_is_bounded(self):
        self.assertEqual(RETRY_DELAYS, (3, 6, 12, 24, 30, 30))
        self.assertLessEqual(sum(RETRY_DELAYS), 120)


class ReadRetryTests(unittest.TestCase):
    def setUp(self):
        self.ch = Chain(Network("local", "http://unused", 31337, "", {}))

    def test_read_recovers_after_an_outage(self):
        seq = [failed([]), failed([]), subprocess.CompletedProcess([], 0, "84532\n", "")]
        sleep = SleepRecorder()
        with mock.patch.object(chain_mod, "run", side_effect=lambda *a, **k: seq.pop(0)), \
                mock.patch.object(chain_mod.time, "sleep", sleep):
            out = self.ch._read(["cast", "chain-id"])
        self.assertEqual(out.stdout.strip(), "84532")
        self.assertEqual(sleep.calls, [3, 6])

    def test_read_gives_up_after_the_bounded_schedule(self):
        sleep, calls = SleepRecorder(), []
        with mock.patch.object(chain_mod, "run", side_effect=lambda a, **k: calls.append(a) or failed(a)), \
                mock.patch.object(chain_mod.time, "sleep", sleep):
            out = self.ch._read(["cast", "chain-id"])
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(len(calls), len(RETRY_DELAYS) + 1)
        self.assertEqual(tuple(sleep.calls), RETRY_DELAYS)


class SettleToleratesOutageTests(unittest.TestCase):
    def test_sealing_wait_survives_unreachable_rpc(self):
        ch = Chain(Network("local", "http://unused", 31337, "", {}))
        answers = [RuntimeError("cast block-number failed: dns error"), RuntimeError("dns error"), 100]

        def latest():
            a = answers.pop(0) if len(answers) > 1 else answers[0]
            if isinstance(a, Exception):
                raise a
            return a

        with mock.patch.object(ch, "_latest_block", latest), mock.patch.object(ch, "_block_hash", lambda n: "0xb"), \
                mock.patch.object(chain_mod.time, "sleep", lambda s: None):
            rc = ch._settle("0xabc", {"blockNumber": hex(100), "blockHash": "0xB"}, "t")
        self.assertEqual(rc["blockNumber"], hex(100))
        self.assertEqual(ch._read_block, 100)


@unittest.skipUnless(HAVE_FOUNDRY, "needs anvil + cast")
class SendOutageTests(unittest.TestCase):
    PORT = 8651

    @classmethod
    def setUpClass(cls):
        cls.anvil = start_anvil(cls.PORT)

    @classmethod
    def tearDownClass(cls):
        cls.anvil.terminate()

    def setUp(self):
        self.ch = Chain(local_network(self.PORT))
        names = sorted(n for n in dir(self) if n.startswith("test_"))
        self.dest = "0x%040x" % (0xd1d10000 + names.index(self._testMethodName))

    def nonce(self):
        return int(run([tool("cast"), "nonce", self.ch.addr("admin"), "--rpc-url", self.ch.net.rpc]).stdout.strip())

    def balance(self):
        return int(run([tool("cast"), "balance", self.dest, "--rpc-url", self.ch.net.rpc]).stdout.strip())

    def outage(self, sub: str, n_failures: int, log: list):
        """`run` where the first n_failures calls of `cast <sub>` hit the DNS failure (never reaching anvil)."""
        real, seen = chain_mod.run, {"n": 0}

        def flaky(args, *a, **kw):
            if len(args) > 1 and args[1] == sub:
                log.append(args[-1])
                seen["n"] += 1
                if seen["n"] <= n_failures:
                    return failed(args)
            return real(args, *a, **kw)
        return flaky

    def test_dns_failure_while_signing_recovers_with_backoff(self):
        n0, log, sleep = self.nonce(), [], SleepRecorder()
        with mock.patch.object(chain_mod, "run", self.outage("mktx", 2, log)), \
                mock.patch.object(chain_mod.time, "sleep", sleep):
            self.ch._send([self.dest, "--value", "7"], "admin", "transfer during outage")
        self.assertEqual(len(log), 3)
        self.assertEqual(sleep.calls[:2], [3, 6])
        self.assertEqual((self.nonce(), self.balance()), (n0 + 1, 7))  # exactly one transaction

    def test_exhausted_signing_retries_fail_closed_and_broadcast_nothing(self):
        n0, log, sleep = self.nonce(), [], SleepRecorder()
        with mock.patch.object(chain_mod, "run", self.outage("mktx", 99, log)), \
                mock.patch.object(chain_mod.time, "sleep", sleep):
            with self.assertRaises(RuntimeError) as e:
                self.ch._send([self.dest, "--value", "7"], "admin", "never signed")
        self.assertIn(f"after {len(RETRY_DELAYS) + 1} attempt(s); nothing was broadcast", str(e.exception))
        self.assertEqual(tuple(sleep.calls), RETRY_DELAYS)
        self.assertEqual((self.nonce(), self.balance()), (n0, 0))

    def test_outage_through_every_broadcast_retry_recovers_by_republishing_the_same_bytes(self):
        n0, log = self.nonce(), []
        with mock.patch.object(chain_mod, "run", self.outage("publish", len(RETRY_DELAYS) + 1, log)), \
                mock.patch.object(chain_mod.time, "sleep", lambda s: None), mock.patch.object(Chain, "PUBLISH_REPEAT", 0):
            rc = self.ch._send([self.dest, "--value", "5"], "admin", "broadcast after outage")
        self.assertEqual(rc["status"], "0x1")
        self.assertGreater(len(log), len(RETRY_DELAYS) + 1)  # recovered on a re-publish from the receipt wait
        self.assertEqual(len(set(log)), 1)  # every attempt carried the identical signed bytes
        self.assertEqual((self.nonce(), self.balance()), (n0 + 1, 5))

    def test_total_outage_fails_closed_without_a_second_signature(self):
        n0, log = self.nonce(), []
        real = chain_mod.run

        def down(args, *a, **kw):  # the node can still be reached for signing, then everything is down
            if len(args) > 1 and args[1] in ("publish", "receipt"):
                log.append((args[1], args[-1]))
                return failed(args)
            return real(args, *a, **kw)

        with mock.patch.object(chain_mod, "run", down), mock.patch.object(chain_mod.time, "sleep", lambda s: None), \
                mock.patch.object(Chain, "RECEIPT_TIMEOUT", 0.5), mock.patch.object(Chain, "PUBLISH_REPEAT", 0):
            with self.assertRaises(RuntimeError) as e:
                self.ch._send([self.dest, "--value", "9"], "admin", "lost to the outage")
        self.assertIn("do NOT resend", str(e.exception))
        self.assertEqual(len({raw for kind, raw in log if kind == "publish"}), 1)  # one signed transaction only
        self.assertEqual((self.nonce(), self.balance()), (n0, 0))

    def test_definite_rejection_is_not_retried(self):
        log, sleep = [], SleepRecorder()
        real = chain_mod.run

        def reject(args, *a, **kw):
            if len(args) > 1 and args[1] == "publish":
                log.append(args[-1])
                return failed(args, "server returned an error response: error code -32003: insufficient funds for "
                                    "gas * price + value")
            return real(args, *a, **kw)

        with mock.patch.object(chain_mod, "run", reject), mock.patch.object(chain_mod.time, "sleep", sleep):
            with self.assertRaises(RuntimeError) as e:
                self.ch._send([self.dest, "--value", "1"], "admin", "rejected")
        self.assertIn("rejected", str(e.exception))
        self.assertEqual(len(log), 1)
        self.assertEqual(sleep.calls, [])

    def test_contract_revert_during_an_outage_window_is_still_decoded_not_retried(self):
        sel = run([tool("cast"), "sig", "ProofRejected()"]).stdout.strip()
        n0, sleep = self.nonce(), SleepRecorder()
        with mock.patch.object(chain_mod.time, "sleep", sleep):
            with self.assertRaises(ChainRevert) as e:
                self.ch._send(["--create", "0x63" + sel[2:] + "60e01b60005260046000fd"], "admin", "revert")
        self.assertEqual(e.exception.error, "ProofRejected")
        self.assertEqual(sleep.calls, [])
        self.assertEqual(self.nonce(), n0)


if __name__ == "__main__":
    unittest.main()
