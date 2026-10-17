"""Regression tests for the public-chain hardening: no key in errors or saved state, no duplicate transactions on
retry, and an honest status on Ctrl-C. Chain tests run on a throwaway local anvil with its PUBLIC dev keys."""
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import traceback
import unittest
from pathlib import Path
from unittest import mock

from hourproof import chain as chain_mod
from hourproof import demo
from hourproof.chain import Chain, ChainRevert, ChainTimeout, derive_key, keccak_hex, redact, run, start_anvil, tool
from hourproof.config import ANVIL_KEYS, local_network

KEY = ANVIL_KEYS[0]   # public anvil key 0: stands in for a secret in these tests
KEY2 = ANVIL_KEYS[1]
HAVE_FOUNDRY = all(shutil.which(t) for t in ("anvil", "cast"))


class TimeoutAndRedactionTests(unittest.TestCase):
    def test_timeout_message_and_traceback_never_contain_the_arguments(self):
        with self.assertRaises(ChainTimeout) as e:
            run(["sh", "-c", "sleep 5", "cast", "--private-key", KEY], timeout=0.3)
        tb = "".join(traceback.format_exception(e.exception))
        self.assertNotIn(KEY[2:], str(e.exception))
        self.assertNotIn(KEY[2:], tb)  # `from None`: the original TimeoutExpired (with argv) is not chained in
        self.assertIn("timed out", str(e.exception))

    def test_redact_removes_keys_in_every_spelling(self):
        text = f"a {KEY} b {KEY[2:].upper()} c 0X{KEY[2:]} d {KEY2[2:]}"
        out = redact(text, [KEY, KEY2])
        for k in (KEY, KEY2):
            self.assertNotIn(k[2:].lower(), out.lower())
        self.assertEqual(out.count(chain_mod.REDACTED), 4)
        self.assertEqual(redact("nothing secret here", [KEY]), "nothing secret here")


@unittest.skipUnless(HAVE_FOUNDRY, "needs foundry's cast")
class KeyDerivationTests(unittest.TestCase):
    def test_derived_keys_are_unchanged_by_moving_the_input_to_stdin(self):
        data = bytes.fromhex(KEY[2:]) + b"buyer"
        old = subprocess.run([tool("cast"), "keccak", "0x" + data.hex()], capture_output=True, text=True).stdout.strip()
        self.assertEqual(derive_key(KEY, "buyer"), old)  # the previous implementation passed it as an argument
        self.assertEqual(keccak_hex(b"\xde\xad\xbe\xef"),
                         "0xd4fd4e189132273036449fc9e11198c739161b4c0116a9a2dccdfa1c492006f1")

    def test_derivation_puts_no_key_material_on_the_command_line(self):
        seen = []
        real = chain_mod.run

        def spy(args, *a, **kw):
            seen.append(list(args))
            return real(args, *a, **kw)

        with mock.patch.object(chain_mod, "run", spy):
            derive_key(KEY, "oracle")
        self.assertTrue(seen)
        self.assertFalse(any(KEY[2:] in " ".join(map(str, args)).lower() for args in seen))


@unittest.skipUnless(HAVE_FOUNDRY, "needs anvil + cast")
class IdempotentSendTests(unittest.TestCase):
    PORT = 8631

    @classmethod
    def setUpClass(cls):
        cls.anvil = start_anvil(cls.PORT)

    @classmethod
    def tearDownClass(cls):
        cls.anvil.terminate()

    def setUp(self):
        self.ch = Chain(local_network(self.PORT))
        names = sorted(n for n in dir(self) if n.startswith("test_"))
        self.dest = "0x%040x" % (0xd00d0000 + names.index(self._testMethodName))  # a fresh recipient per test

    def nonce(self, role="admin"):
        return int(run([tool("cast"), "nonce", self.ch.addr(role), "--rpc-url", self.ch.net.rpc]).stdout.strip())

    def test_lost_answer_after_broadcast_is_not_sent_twice(self):
        """The node accepts the transaction but our side sees a connection error: the retry republishes the SAME
        bytes, the receipt is found by hash, and exactly one transaction is mined."""
        n0, real, calls = self.nonce(), chain_mod.run, {"publish": 0}

        def flaky(args, *a, **kw):
            out = real(args, *a, **kw)
            if len(args) > 1 and args[1] == "publish":
                calls["publish"] += 1
                if calls["publish"] == 1:
                    return subprocess.CompletedProcess(args, 1, "", "error sending request: connection reset by peer")
            return out

        with mock.patch.object(chain_mod, "run", flaky), mock.patch.object(chain_mod.time, "sleep"):
            rc = self.ch._send([self.dest, "--value", "7"], "admin", "flaky transfer")
        self.assertEqual(calls["publish"], 2)
        self.assertEqual(self.nonce(), n0 + 1)  # exactly one transaction
        self.assertEqual(int(run([tool("cast"), "balance", self.dest, "--rpc-url", self.ch.net.rpc]).stdout.strip()), 7)
        self.assertEqual(rc["status"], "0x1")
        self.assertEqual(self.ch.txs[-1].role, "admin")

    def test_publish_timeout_is_retried_with_the_same_bytes(self):
        n0, real, sent = self.nonce(), chain_mod.run, []

        def slow_once(args, *a, **kw):
            if len(args) > 1 and args[1] == "publish":
                sent.append(args[-1])
                if len(sent) == 1:
                    real(args, *a, **kw)  # it reaches the node...
                    raise ChainTimeout("`cast publish` timed out after 120s")  # ...but our wait times out
            return real(args, *a, **kw)

        with mock.patch.object(chain_mod, "run", slow_once), mock.patch.object(chain_mod.time, "sleep"):
            self.ch._send([self.dest, "--value", "3"], "admin", "slow transfer")
        self.assertEqual(len(set(sent)), 1)  # every attempt published identical signed bytes
        self.assertEqual(self.nonce(), n0 + 1)

    def test_contract_revert_is_decoded_before_anything_is_broadcast(self):
        """Refused attacks are detected exactly as before: by the custom error, at gas estimation."""
        sel = run([tool("cast"), "sig", "ProofRejected()"]).stdout.strip()
        n0 = self.nonce()
        with self.assertRaises(ChainRevert) as e:
            self.ch._send(["--create", "0x63" + sel[2:] + "60e01b60005260046000fd"], "admin", "reverting create")
        self.assertEqual(e.exception.error, "ProofRejected")
        self.assertEqual(self.nonce(), n0)  # nothing was broadcast

    def test_nonce_taken_by_another_transaction_fails_closed(self):
        """If something else uses our pinned nonce, the run fails instead of waiting forever or resending."""
        n0 = self.nonce()
        real = chain_mod.run

        def race(args, *a, **kw):
            if len(args) > 1 and args[1] == "publish":
                real([tool("cast"), "send", "--rpc-url", self.ch.net.rpc, "--private-key", KEY, "--nonce", str(n0),
                      self.dest, "--value", "1"])  # another sender consumes the nonce first
            return real(args, *a, **kw)

        with mock.patch.object(chain_mod, "run", race), mock.patch.object(Chain, "RECEIPT_TIMEOUT", 2):
            with self.assertRaises(RuntimeError) as e:
                self.ch._send([self.dest, "--value", "5"], "admin", "raced transfer")
        self.assertIn("used by a different transaction", str(e.exception))
        self.assertEqual(self.nonce(), n0 + 1)  # only the other transaction


class RunStateTests(unittest.TestCase):
    """What a demo run saves, prints and shows when it fails or is interrupted."""

    def _run(self, d: Path, boom):
        with mock.patch.object(demo, "RUNS", d), mock.patch.object(demo, "DEMO_STATE", d / "demo_state.json"):
            r = demo.Run(network="local", zk_mode="mock")
            r.chain = Chain(local_network())
            r.chain.net.keys = {"admin": KEY, "buyer": KEY2}
            r._execute = boom
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    r.execute()
            finally:
                saved = (d / "demo_state.json").read_text() + (r.dir / "state.json").read_text()
            return r, saved, out.getvalue()

    def test_a_failure_carrying_a_key_is_scrubbed_everywhere(self):
        def boom():
            raise RuntimeError(f"cast failed with --private-key {KEY} and {KEY2[2:].upper()}")

        with tempfile.TemporaryDirectory() as d:
            r, saved, printed = self._run(Path(d), boom)
        self.assertEqual(r.state["status"], "failed")
        for k in (KEY, KEY2):
            for text in (saved, printed, r.state["error"], r.state["traceback"]):
                self.assertNotIn(k[2:].lower(), text.lower())
        self.assertIn(chain_mod.REDACTED, r.state["error"])

    def test_a_failing_step_detail_is_scrubbed(self):
        def boom():
            with r_holder["r"].step("x", "a step"):
                raise RuntimeError(f"step failed near {KEY}")

        r_holder = {}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(demo, "RUNS", Path(d)), \
                mock.patch.object(demo, "DEMO_STATE", Path(d) / "demo_state.json"):
            r = demo.Run(network="local", zk_mode="mock")
            r.chain = Chain(local_network())
            r.chain.net.keys = {"admin": KEY}
            r_holder["r"] = r
            r._execute = boom
            with contextlib.redirect_stdout(io.StringIO()) as out:
                r.execute()
            saved = (Path(d) / "demo_state.json").read_text()
        self.assertNotIn(KEY[2:], saved)
        self.assertNotIn(KEY[2:], out.getvalue())
        self.assertIn(chain_mod.REDACTED, r.state["steps"][0]["detail"])

    def test_ctrl_c_is_recorded_as_aborted_and_still_stops(self):
        def interrupted():
            raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(KeyboardInterrupt):
                self._run(Path(d), interrupted)
            saved = json.loads((Path(d) / "demo_state.json").read_text())
        self.assertEqual(saved["status"], "aborted")
        self.assertIn("finished_utc", saved)


if __name__ == "__main__":
    unittest.main()
