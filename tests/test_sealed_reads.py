"""Regression tests for read-after-write on RPCs whose receipts run ahead of the sealed `latest` block (Base
Flashblocks). The failed Base Sepolia run (20261016T223327Z) signed issuer nonce 2 after the nonce-3 batch's receipt
had arrived, because the read of the nonce still saw the previous sealed block. Chain tests use a throwaway anvil
with its PUBLIC dev keys behind a small proxy that reproduces that lag."""
import contextlib
import json
import shutil
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import requests

from hourproof import chain as chain_mod
from hourproof import pq
from hourproof.chain import Chain, ChainRevert, b32, start_anvil
from hourproof.config import ANVIL_KEYS, ROLES, Network

HAVE_FOUNDRY = all(shutil.which(t) for t in ("anvil", "cast", "forge"))
try:
    import dilithium_py  # noqa: F401
    HAVE_MLDSA = True
except ImportError:
    HAVE_MLDSA = False


# ------------------------------------------------------------------ unit: _settle against scripted RPC answers
class ScriptedChain(Chain):
    """_settle's three RPC reads answered from scripts (one item per call; the last item repeats)."""

    def __init__(self, latest, hashes, receipts=()):
        super().__init__(Network("local", "http://unused", 31337, "", {}))
        self.latest, self.hashes, self.receipts = list(latest), list(hashes), list(receipts)
        self.calls = {"latest": 0, "hash": 0, "receipt": 0}

    @staticmethod
    def _next(script):
        return script.pop(0) if len(script) > 1 else script[0]

    def _latest_block(self):
        self.calls["latest"] += 1
        return self._next(self.latest)

    def _block_hash(self, number):
        self.calls["hash"] += 1
        return self._next(self.hashes)

    def _receipt(self, txhash):
        self.calls["receipt"] += 1
        return self._next(self.receipts)


def rc(block: int, bhash: str, status: str = "0x1") -> dict:
    return {"blockNumber": hex(block), "blockHash": bhash, "status": status, "transactionHash": "0xabc"}


@mock.patch.object(chain_mod.time, "sleep", lambda s: None)
class SettleUnitTests(unittest.TestCase):
    def test_waits_while_latest_lags_behind_the_receipt(self):
        ch = ScriptedChain(latest=[99, 99, 99, 100], hashes=["0xb100"])
        out = ch._settle("0xabc", rc(100, "0xB100"), "t")
        self.assertEqual(out["blockNumber"], hex(100))
        self.assertEqual(ch.calls["latest"], 4)  # returned only once latest reached the receipt's block
        self.assertEqual(ch._read_block, 100)   # later reads are pinned to it

    def test_does_not_pin_before_the_block_is_sealed(self):
        ch = ScriptedChain(latest=[99], hashes=["0xb100"])
        with mock.patch.object(Chain, "SEAL_TIMEOUT", 0):
            with self.assertRaises(RuntimeError) as e:
                ch._settle("0xabc", rc(100, "0xb100"), "never sealed")
        self.assertIn("not in a sealed canonical block", str(e.exception))
        self.assertEqual(ch._read_block, 0)

    def test_reorg_moves_the_transaction_to_a_later_block(self):
        # block 100 got sealed without our tx (hash differs); the receipt now says block 101
        ch = ScriptedChain(latest=[100, 100, 101], hashes=["0xother", "0xb101"], receipts=[rc(101, "0xb101")])
        out = ch._settle("0xabc", rc(100, "0xb100"), "t")
        self.assertEqual(out["blockNumber"], hex(101))
        self.assertEqual(ch._read_block, 101)

    def test_receipt_that_disappears_fails_closed(self):
        ch = ScriptedChain(latest=[100], hashes=["0xother"], receipts=[None])
        with mock.patch.object(Chain, "SEAL_TIMEOUT", 0):
            with self.assertRaises(RuntimeError):
                ch._settle("0xabc", rc(100, "0xb100"), "dropped")
        self.assertEqual(ch._read_block, 0)

    def test_failed_status_is_still_reported_by_send(self):
        # _settle never turns a reverted transaction into a success: status is checked by _send after it
        ch = ScriptedChain(latest=[100], hashes=["0xb100"])
        self.assertEqual(ch._settle("0xabc", rc(100, "0xb100", "0x0"), "t")["status"], "0x0")

    def test_pin_is_monotonic(self):
        ch = ScriptedChain(latest=[200], hashes=["0xb150"])
        ch._read_block = 180
        ch._settle("0xabc", rc(150, "0xb150"), "t")
        self.assertEqual(ch._read_block, 180)


# ------------------------------------------------------------------ integration: a Flashblocks-like RPC
class LaggingRpc:
    """JSON-RPC proxy in front of anvil. For LAG seconds after each new block, the SEALED head it reports (and every
    `latest`-based read) is the previous block, while receipts and pending state are already current, as on an RPC
    serving pre-confirmations. Explicit reads of a block above the sealed head get "header not found"."""
    LAG = 1.2
    TAGGED = {"eth_call": 1, "eth_getBalance": 1, "eth_getCode": 1, "eth_getStorageAt": 2}

    def __init__(self, upstream: str, port: int):
        self.upstream, self.port, self.first_seen, self.lock = upstream, port, {}, threading.Lock()
        proxy = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                out = [proxy.handle(r) for r in body] if isinstance(body, list) else proxy.handle(body)
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def up(self, req: dict) -> dict:
        return requests.post(self.upstream, json=req, timeout=30).json()

    def sealed(self) -> int:
        head = int(self.up({"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []})["result"], 16)
        with self.lock:
            t = self.first_seen.setdefault(head, time.time())
        return head - 1 if time.time() - t < self.LAG and head > 0 else head

    def handle(self, req: dict) -> dict:
        m, p = req.get("method"), list(req.get("params") or [])
        if m == "eth_blockNumber":
            return {"jsonrpc": "2.0", "id": req.get("id"), "result": hex(self.sealed())}
        if m == "eth_getBlockByNumber" and p and p[0] not in ("pending", "earliest", "safe", "finalized"):
            s = self.sealed()
            if p[0] == "latest":
                p[0] = hex(s)
            elif int(p[0], 16) > s:
                return {"jsonrpc": "2.0", "id": req.get("id"), "result": None}
        if m in self.TAGGED:
            i, s = self.TAGGED[m], self.sealed()
            tag = p[i] if len(p) > i else "latest"
            if isinstance(tag, dict):
                tag = tag.get("blockNumber", "latest")
            if tag == "latest":
                p = p[:i] + [hex(s)] + p[i + 1:]
            elif isinstance(tag, str) and tag.startswith("0x") and int(tag, 16) > s:
                return {"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32000, "message": "header not found"}}
        return self.up({**req, "params": p})

    def close(self):
        self.server.shutdown()


def disabled_settle(self, txhash, rc, label):
    """The behaviour before the fix: trust the receipt, read `latest` (no wait, no pin)."""
    return rc


@unittest.skipUnless(HAVE_FOUNDRY, "needs anvil + cast + forge build output")
class LaggingRpcIntegrationTests(unittest.TestCase):
    ANVIL, PROXY = 8641, 8642

    @classmethod
    def setUpClass(cls):
        cls.anvil = start_anvil(cls.ANVIL)
        cls.proxy = LaggingRpc(f"http://127.0.0.1:{cls.ANVIL}", cls.PROXY)

    @classmethod
    def tearDownClass(cls):
        cls.proxy.close()
        cls.anvil.terminate()

    def chain(self) -> Chain:
        return Chain(Network("local", f"http://127.0.0.1:{self.PROXY}", 31337, "", dict(zip(ROLES, ANVIL_KEYS))))

    def commit_then_read(self, ch: Chain, day: int) -> int:
        log = ch.deploy("AgentCommitLog", role="agent")
        time.sleep(LaggingRpc.LAG + 0.3)  # start from a settled head, then race exactly one write against one read
        ch.send(log, "commit(bytes32,uint64,bytes32)", [b32("agent"), day, b32("plan")], role="agent")
        out = ch.call(log, "entries(address,bytes32,uint64)(bytes32,uint64,bool,bool)",
                      [ch.addr("agent"), b32("agent"), day])
        return int(out.splitlines()[1].split()[0])  # committedAt: 0 = the read did not see the write

    def test_simulator_reproduces_the_stale_read_without_the_fix(self):
        with mock.patch.object(Chain, "_settle", disabled_settle):
            self.assertEqual(self.commit_then_read(self.chain(), 1_800_000_000), 0)

    def test_fix_reads_its_own_write(self):
        self.assertNotEqual(self.commit_then_read(self.chain(), 1_800_086_400), 0)

    @unittest.skipUnless(HAVE_MLDSA, "needs dilithium-py")
    def test_signed_issuance_after_a_batch_reproduces_and_fixes_the_base_failure(self):
        """The observed failure end to end: issue a signed batch, read batchMessage (which embeds the issuer's
        nonce), sign it, issue again. Without the fix the second signature covers the stale nonce and the contract
        refuses it with BadIssuerSignature; with the fix both batches are accepted. Nothing is hard-coded: the
        message comes from the contract each time."""
        self.assertEqual(self.two_batches(fixed=False), "BadIssuerSignature")
        self.assertEqual(self.two_batches(fixed=True), 2)

    def two_batches(self, fixed: bool):
        ch = self.chain()
        with mock.patch.object(Chain, "_settle", disabled_settle) if not fixed else contextlib.nullcontext():
            zone, asset, hour = b32("DK"), b32("DK-wind-declared"), 1_736_121_600
            oracle = ch.deploy("ProductionOracle")
            ledger = ch.deploy("SliceLedger")
            helper = ch.deploy_runtime(pq.helper_runtime(), label="deploy ML-DSA Keccak helper")
            verifier = ch.deploy("MLDSA44Verifier", [helper])
            key = pq.issuer_key("A")
            blob = ch.deploy_runtime(key["blob"], label="deploy issuer A ML-DSA public key")
            reg = ch.deploy("CertRegistry", ["Registry A", ledger, oracle, verifier])
            ch.send(oracle, "setPoster(address,bool)", [ch.addr("oracle"), "true"])
            ch.send(ledger, "setRegistry(address,bool)", [reg, "true"])
            ch.send(reg, "registerIssuer(bytes32,address)", [b32("issuer-A"), blob])
            ch.send(oracle, "post(bytes32,bytes32,uint64[],uint32[])", [zone, asset, f"[{hour}]", "[100]"], role="oracle")
            time.sleep(LaggingRpc.LAG + 0.3)  # settled head, as before each issuance in the demo
            sig_t = "(bytes32,bytes32,uint64,uint32,uint32,address)[]"
            try:
                for first in (0, 10):  # two batches of 10 MWh of the same hour: batch 2 is signed after batch 1
                    batch = f"[({zone},{asset},{hour},{first},10,{ch.addr('buyer')})]"
                    msg = ch.call(reg, f"batchMessage(bytes32,{sig_t})(bytes)", [b32("issuer-A"), batch])
                    sig = pq.sign(key["sk"], bytes.fromhex(msg.removeprefix("0x")))
                    ch.send(reg, f"issueBatch(bytes32,{sig_t},bytes)", [b32("issuer-A"), batch, sig], role="issuer_ops")
            except ChainRevert as e:
                return e.error
            return int(ch.call(reg, "issuers(bytes32)(address,bool,uint64)", [b32("issuer-A")]).splitlines()[2])


if __name__ == "__main__":
    unittest.main()
