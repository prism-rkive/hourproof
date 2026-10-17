"""Thin, dependency-free chain client built on Foundry's `cast` (same toolchain as the contracts).

Every write returns a Tx record (hash, gas, block, explorer link). Reverts raise ChainRevert with the
custom error decoded from the project's own ABIs, so the demo can assert *which* safeguard fired.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import CONTRACTS, Network


class ToolMissing(RuntimeError):
    pass


def tool(name: str) -> str:
    p = shutil.which(name) or str(Path.home() / ".foundry" / "bin" / name)
    if not Path(p).exists():
        raise ToolMissing(f"`{name}` not found. Install the toolchain: ./scripts/install_tools.sh")
    return p


class ChainTimeout(RuntimeError):
    """A tool call timed out. The message names only the tool and its subcommand: the full argument list can hold a
    private key (`cast send --private-key ...`), and Python's own TimeoutExpired message would print all of it."""


def run(args: list[str], cwd: Path | None = None, timeout: int = 600, env: dict | None = None,
        input: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env, input=input)
    except subprocess.TimeoutExpired:
        what = " ".join([Path(args[0]).name, *args[1:2]])
        raise ChainTimeout(f"`{what}` timed out after {timeout}s") from None  # `from None`: no argv in the traceback


def keccak_hex(data: bytes) -> str:
    """keccak256 via `cast keccak`, with the data on stdin (never on the command line: it may be key material)."""
    out = run([tool("cast"), "keccak"], input="0x" + data.hex())
    if out.returncode:
        raise RuntimeError(f"cast keccak failed: {out.stderr.strip()[:200]}")
    return out.stdout.strip()


def derive_key(master: str, role: str) -> str:
    """Deterministic role key from a master key (testnet convenience; never for real funds)."""
    return keccak_hex(bytes.fromhex(master.removeprefix("0x")) + role.encode())


REDACTED = "<redacted>"


def redact(text: str, secrets) -> str:
    """Remove every secret (with or without 0x, any letter case) from text that will be saved, printed or shown."""
    for s in secrets:
        h = str(s).lower().removeprefix("0x")
        if len(h) >= 16:
            text = re.sub(rf"(?i)(0x)?{re.escape(h)}", REDACTED, text)
    return text


def b32(text: str) -> str:
    raw = text.encode()
    if len(raw) > 32:
        raise ValueError(f"{text!r} longer than 32 bytes")
    return "0x" + raw.hex().ljust(64, "0")


TRANSIENT = ("nonce", "timeout", "timed out", "replacement", "connection", "429", "rate limit", "underpriced",
             "too many requests", "502", "503", "504", "temporarily",
             # a read pinned to our last sealed block, served by a node that has not sealed it yet: retry, never stale
             "header not found", "unknown block", "block not found", "beyond the current head",
             # the network itself (e.g. Wi-Fi drop): "client error (Connect): dns error: ... Temporary failure in name
             # resolution" ended the second Base Sepolia attempt because none of the patterns above matched it
             "dns error", "name resolution", "failed to lookup", "error sending request", "connect",
             "network is unreachable", "no route to host", "broken pipe", "eof")
# Bounded exponential backoff for every retried call: 7 attempts, ~105 s in total (rides out a short outage).
RETRY_DELAYS = (3, 6, 12, 24, 30, 30)


def _transient(text: str) -> bool:
    return any(s in text.lower() for s in TRANSIENT)


class ChainRevert(RuntimeError):
    def __init__(self, error: str, data: str, message: str):
        super().__init__(f"{error}: {message[:300]}")
        self.error, self.data, self.message = error, data, message


@dataclass
class Tx:
    label: str
    hash: str
    gas: int
    block: int
    url: str = ""
    to: str = ""
    role: str = ""  # who sent it (gas accounting per role wallet)


@dataclass
class Chain:
    net: Network
    txs: list[Tx] = field(default_factory=list)
    _addr: dict[str, str] = field(default_factory=dict)
    _libs: dict[str, str] = field(default_factory=dict)
    # Block of our last write, once SEALED (see _settle). State reads are pinned to it, so they always include our
    # own writes, even from a load-balanced RPC node that is behind. 0 = no write yet: read `latest`.
    _read_block: int = 0

    # ---------------------------------------------------------------- basics
    def addr(self, role: str) -> str:
        if role not in self._addr:
            out = run([tool("cast"), "wallet", "address", "--private-key", self.net.keys[role]])
            if out.returncode:
                raise RuntimeError(out.stderr)
            self._addr[role] = out.stdout.strip()
        return self._addr[role]

    def _read(self, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """A read-only cast call, retried on transient RPC/network errors and timeouts with RETRY_DELAYS backoff
        (safe: a read changes nothing). After the last attempt the failed result (or the timeout) is returned."""
        for attempt in range(len(RETRY_DELAYS) + 1):
            last = attempt == len(RETRY_DELAYS)
            try:
                out = run(args, timeout=timeout)
            except ChainTimeout:
                if last:
                    raise
                time.sleep(RETRY_DELAYS[attempt])
                continue
            if out.returncode == 0 or not _transient(out.stdout + out.stderr) or last:
                return out
            time.sleep(RETRY_DELAYS[attempt])
        return out

    def chain_id(self) -> int:
        out = self._read([tool("cast"), "chain-id", "--rpc-url", self.net.rpc], timeout=30)
        if out.returncode:
            raise RuntimeError(f"RPC {self.net.rpc} unreachable: {out.stderr.strip()[:200]}")
        return int(out.stdout.strip())

    def block_timestamp(self) -> int:
        out = self._read([tool("cast"), "block", "latest", "--field", "timestamp", "--rpc-url", self.net.rpc])
        if out.returncode:
            raise RuntimeError(f"cast block failed: {out.stderr.strip()[:200]}")
        return int(out.stdout.strip(), 0)

    def gas_price_wei(self) -> int:
        out = self._read([tool("cast"), "gas-price", "--rpc-url", self.net.rpc])
        if out.returncode:
            raise RuntimeError(f"cast gas-price failed: {out.stderr.strip()[:200]}")
        return int(out.stdout.strip())

    def fee_cap_wei(self) -> int:
        """Upper bound of the max fee per gas `cast send` will set: it uses 2 x base fee + a priority fee from fee
        history (measured: 2 x base + 1 wei). Bounded here by max(eth_gasPrice, 2 x latest base fee +
        eth_maxPriorityFeePerGas). Fails closed: any missing value raises instead of guessing."""
        base = self._read([tool("cast"), "block", "latest", "--field", "baseFeePerGas", "--rpc-url", self.net.rpc])
        tip = self._read([tool("cast"), "rpc", "eth_maxPriorityFeePerGas", "--rpc-url", self.net.rpc])
        if base.returncode or tip.returncode:
            raise RuntimeError(f"fee data unavailable: {(base.stderr + tip.stderr).strip()[:200]}")
        cap = max(self.gas_price_wei(), 2 * int(base.stdout.strip(), 0) + int(tip.stdout.strip().strip('"'), 0))
        if cap <= 0:
            raise RuntimeError("RPC reported a zero fee cap; refusing to plan funding on it")
        return cap

    def balance_wei(self, role_or_addr: str) -> int:
        a = self.addr(role_or_addr) if role_or_addr in self.net.keys else role_or_addr
        out = self._read([tool("cast"), "balance", a, "--rpc-url", self.net.rpc, *self._pin()])
        if out.returncode:
            raise RuntimeError(f"cast balance failed: {out.stderr.strip()[:200]}")
        return int(out.stdout.strip())

    def balance_eth(self, role_or_addr: str) -> float:
        return self.balance_wei(role_or_addr) / 1e18

    # ---------------------------------------------------------------- artifacts
    @staticmethod
    @lru_cache(maxsize=None)
    def artifact(name: str) -> dict:
        """`Name` or `File.sol:Name`. A bare name must be unique across contracts/out: bb names every generated
        verifier HonkVerifier, so silently taking the first hit could deploy the wrong circuit's verifier."""
        source, _, contract = name.rpartition(":")
        pattern = f"{source}/{contract}.json" if source else f"**/{contract}.json"
        hits = [h for h in sorted((CONTRACTS / "out").glob(pattern)) if not h.parent.name.endswith(".t.sol")]
        if not hits:
            raise RuntimeError(f"artifact {name} not found: run `forge build` in contracts/")
        if len(hits) > 1:
            raise RuntimeError(f"artifact name {name} is ambiguous ({', '.join(h.parent.name for h in hits)}); "
                               "use File.sol:Name")
        return json.loads(hits[0].read_text())

    @staticmethod
    @lru_cache(maxsize=1)
    def error_map() -> dict[str, str]:
        """selector -> error signature, from every ABI in contracts/out."""
        sigs: set[str] = set()
        for f in (CONTRACTS / "out").glob("**/*.json"):
            try:
                abi = json.loads(f.read_text()).get("abi", [])
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                continue
            for e in abi:
                if isinstance(e, dict) and e.get("type") == "error":
                    sigs.add(f"{e['name']}({','.join(_type(i) for i in e['inputs'])})")
        m = {}
        for s in sorted(sigs):
            out = run([tool("cast"), "sig", s])
            if out.returncode == 0:
                m[out.stdout.strip()[:10]] = s
        return m

    # ---------------------------------------------------------------- writes
    def _decode_revert(self, text: str) -> ChainRevert | None:
        m = re.search(r'data: \\?"(0x[0-9a-fA-F]+)', text) or re.search(r"custom error (0x[0-9a-fA-F]{8})", text)
        if m:
            data = m.group(1)
            err = self.error_map().get(data[:10], f"UnknownError_{data[:10]}")
            return ChainRevert(err.split("(")[0], data, text)
        if "revert" in text.lower():
            return ChainRevert("Reverted", "", text)
        return None

    RECEIPT_TIMEOUT = 300  # seconds a published transaction may take to be mined before the run fails closed
    ALREADY_SEEN = ("already known", "nonce too low", "known transaction", "already imported")

    def secrets(self) -> list[str]:
        """Every private key this client signs with (to scrub from anything saved, printed or shown)."""
        return list(self.net.keys.values())

    def _send(self, args: list[str], role: str, label: str, to: str = "") -> dict:
        """Sign once, publish idempotently, wait by hash; never two transactions for one intended write.

        1. `cast mktx` signs with a pinned nonce. Gas estimation runs here, so a contract revert (every refused
           attack) surfaces BEFORE anything is broadcast, decoded exactly as before.
        2. The hash is computed from the signed bytes. After an ambiguous failure only those same bytes are
           published again, and a node cannot mine them twice ("already known" / "nonce too low").
        3. The receipt is polled by that hash. Nothing is ever re-signed with a new nonce."""
        nonce = self._pending_nonce(role)
        raw = self._sign(args, role, label, nonce)
        txhash = keccak_hex(bytes.fromhex(raw.removeprefix("0x")))
        self._publish(raw, label)  # False = no answer through an outage: the wait below keeps re-publishing `raw`
        rc = self._wait_receipt(txhash, role, nonce, label, raw)
        rc = self._settle(txhash, rc, label)  # sealed + canonical before anything reads state that depends on it
        if rc.get("status") not in ("0x1", 1, "1"):
            raise ChainRevert("TxFailed", "", f"{label}: status {rc.get('status')}")
        tx = Tx(label, rc["transactionHash"], int(rc["gasUsed"], 16), int(rc["blockNumber"], 16),
                self.net.tx_url(rc["transactionHash"]), to or rc.get("contractAddress") or "", role)
        self.txs.append(tx)
        rc["_tx"] = tx
        return rc

    def _pending_nonce(self, role: str) -> int:
        out = self._read([tool("cast"), "nonce", self.addr(role), "--block", "pending", "--rpc-url", self.net.rpc])
        if out.returncode:
            raise RuntimeError(f"cast nonce failed: {out.stderr.strip()[:200]}")
        return int(out.stdout.strip())

    def _sign(self, args: list[str], role: str, label: str, nonce: int) -> str:
        """Build and sign; nothing leaves this machine except the estimation call. Safe to retry."""
        cmd = [tool("cast"), "mktx", "--rpc-url", self.net.rpc, "--private-key", self.net.keys[role], "--nonce",
               str(nonce), *args]
        text = ""
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                out = run(cmd, timeout=300)
            except ChainTimeout as e:
                text = str(e)
            else:
                text = (out.stdout or "") + (out.stderr or "")
                if out.returncode == 0:
                    raw = out.stdout.strip().splitlines()[-1].strip()
                    if not re.fullmatch(r"0x[0-9a-fA-F]+", raw):
                        raise RuntimeError(f"cast mktx returned no signed transaction ({label})")
                    return raw
                rev = self._decode_revert(text)  # a contract revert is an answer, never retried
                if rev:
                    raise rev
                if not _transient(text):
                    break
            if attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])
        raise RuntimeError(f"cast mktx failed ({label}) after {attempt + 1} attempt(s); nothing was broadcast: "
                           f"{text.strip()[:600]}")

    PUBLISH_REPEAT = 15  # seconds between re-publishing the SAME signed bytes while no receipt has appeared

    def _publish_once(self, raw: str) -> tuple[str, str]:
        """One broadcast attempt: ("accepted" | "transient" | "error", text). Idempotent: same bytes, same tx."""
        try:
            out = run([tool("cast"), "publish", "--rpc-url", self.net.rpc, "--async", raw], timeout=120)
        except ChainTimeout as e:
            return "transient", str(e)
        text = (out.stdout or "") + (out.stderr or "")
        if out.returncode == 0 or any(s in text.lower() for s in self.ALREADY_SEEN):
            return "accepted", text  # accepted now, or earlier by an attempt whose answer was lost
        return ("transient" if _transient(text) else "error"), text

    def _publish(self, raw: str, label: str) -> bool:
        """Broadcast the signed bytes with RETRY_DELAYS backoff. True = the node took them. False = no answer
        through an outage (the bytes may or may not have arrived): the caller waits for the receipt and keeps
        re-publishing the SAME bytes. A definite rejection (e.g. insufficient funds) raises: nothing to wait for."""
        for attempt in range(len(RETRY_DELAYS) + 1):
            kind, text = self._publish_once(raw)
            if kind == "accepted":
                return True
            if kind == "error":
                raise RuntimeError(f"cast publish rejected ({label}): {text.strip()[:600]}")
            if attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])
        return False

    def _wait_receipt(self, txhash: str, role: str, nonce: int, label: str, raw: str | None = None) -> dict:
        """Poll the receipt of exactly this hash, re-publishing the identical signed bytes every PUBLISH_REPEAT s
        (a lost broadcast recovers; a duplicate is impossible). Fails closed after RECEIPT_TIMEOUT, and says so
        explicitly if the nonce was consumed by a different transaction (e.g. another run using the same wallet)."""
        deadline = time.time() + self.RECEIPT_TIMEOUT
        republish_at = time.time() + self.PUBLISH_REPEAT
        while True:
            rc = self._receipt(txhash)
            if rc is not None:
                return rc
            if time.time() > deadline:
                latest = self._read([tool("cast"), "nonce", self.addr(role), "--rpc-url", self.net.rpc])
                if latest.returncode == 0 and int(latest.stdout.strip()) > nonce:
                    raise RuntimeError(f"{label}: nonce {nonce} was used by a different transaction (another run "
                                       f"using this wallet?); {txhash} was never mined")
                raise RuntimeError(f"{label}: {txhash} not mined within {self.RECEIPT_TIMEOUT}s. It may still be "
                                   "mined later: do NOT resend; reconcile the wallet nonce first")
            if raw and time.time() >= republish_at:
                self._publish_once(raw)  # same bytes; any answer is fine, the receipt decides
                republish_at = time.time() + self.PUBLISH_REPEAT
            time.sleep(0.5 if self.net.name == "local" else 2)

    SEAL_TIMEOUT = 120  # seconds a receipt's block may take to appear as the RPC's sealed `latest` before failing closed

    def _receipt(self, txhash: str) -> dict | None:
        out = self._read([tool("cast"), "receipt", "--rpc-url", self.net.rpc, "--async", "--json", txhash])
        if out.returncode == 0 and "{" in out.stdout:
            return json.loads(out.stdout[out.stdout.index("{"):])
        return None

    def _latest_block(self) -> int:
        out = self._read([tool("cast"), "block-number", "--rpc-url", self.net.rpc])
        if out.returncode:
            raise RuntimeError(f"cast block-number failed: {out.stderr.strip()[:200]}")
        return int(out.stdout.strip())

    def _block_hash(self, number: int) -> str | None:
        out = self._read([tool("cast"), "block", str(number), "--field", "hash", "--rpc-url", self.net.rpc])
        return out.stdout.strip().lower() if out.returncode == 0 and out.stdout.strip().startswith("0x") else None

    def _settle(self, txhash: str, rc: dict, label: str) -> dict:
        """Return the receipt only once its block is the RPC's SEALED `latest` (or older) and is the canonical block
        at that height. Flashblocks RPCs (Base) return receipts of pre-confirmed transactions up to ~2 s before the
        block is sealed, and a read at `latest` in that window still shows the state BEFORE the transaction (the
        failed Base Sepolia run signed issuer nonce 2 after the nonce-3 batch's receipt for exactly this reason).
        A re-org, or a pre-confirmation sealed differently, shows up as a block-hash mismatch: the receipt is then
        re-read and the wait starts over. Fails closed after SEAL_TIMEOUT. On anvil this costs two reads."""
        deadline = time.time() + self.SEAL_TIMEOUT
        latest = -1
        while True:
            n = int(rc["blockNumber"], 16)
            try:
                latest = self._latest_block()
            except RuntimeError:  # the RPC is unreachable right now (after _read's own retries): not known yet
                latest = -1
            if latest >= n:
                if self._block_hash(n) == str(rc.get("blockHash", "")).lower():
                    self._read_block = max(self._read_block, n)  # every later read sees this write
                    return rc
                again = self._receipt(txhash)  # the block at n is not the one the receipt named
                if again is not None and (again.get("blockHash"), again.get("blockNumber")) != \
                        (rc.get("blockHash"), rc.get("blockNumber")):
                    rc = again
                    continue
            if time.time() > deadline:
                raise RuntimeError(f"{label}: {txhash} not in a sealed canonical block within {self.SEAL_TIMEOUT}s "
                                   f"(receipt block {n}, latest {latest}); stopping before any dependent read")
            time.sleep(0.2 if self.net.name == "local" else 1)

    def deploy(self, name: str, args: list | None = None, role: str = "admin", label: str | None = None) -> str:
        art = self.artifact(name)
        bytecode = self._link(art, role)
        ctor =next((e for e in art["abi"] if e["type"] == "constructor"), None)
        if ctor and ctor["inputs"]:
            sig = f"constructor({','.join(_type(i) for i in ctor['inputs'])})"
            enc = run([tool("cast"), "abi-encode", sig, *[str(a) for a in args or []]])
            if enc.returncode:
                raise RuntimeError(enc.stderr)
            bytecode += enc.stdout.strip().removeprefix("0x")
        rc = self._send(["--create", bytecode], role, label or f"deploy {name}")
        return _checksum(rc["contractAddress"])

    def _link(self, art: dict, role: str) -> str:
        """Deploy the external libraries an artifact links against (once per chain) and splice in their
        addresses, as forge does in tests (the generated UltraHonk verifiers use RelationsLib/ZKTranscriptLib and
        EmissionsRelationsLib/EmissionsZKTranscriptLib). Libraries are keyed by source file AND name."""
        code = art["bytecode"]["object"].removeprefix("0x")
        for src, libs in art["bytecode"].get("linkReferences", {}).items():
            for lib, refs in libs.items():
                fq = f"{Path(src).name}:{lib}"
                if fq not in self._libs:
                    self._libs[fq] = self.deploy(fq, role=role, label=f"deploy library {lib}")
                addr = self._libs[fq].removeprefix("0x").lower()
                for r in refs:
                    s = 2 * r["start"]
                    code = code[:s] + addr + code[s + 2 * r["length"]:]
        if "__$" in code:
            raise RuntimeError("bytecode still has unlinked library placeholders")
        return "0x" + code

    def deploy_runtime(self, runtime_hex: str, role: str = "admin", label: str = "deploy data contract") -> str:
        """Deploy raw runtime bytes as contract code (ML-DSA Keccak helper / public-key blob)."""
        rt = runtime_hex.strip().removeprefix("0x")
        init = f"61{len(rt) // 2:04x}80600a3d393df3" + rt
        rc = self._send(["--create", init], role, label)
        return _checksum(rc["contractAddress"])

    def send(self, to: str, sig: str, args: list | None = None, role: str = "admin", label: str = "") -> Tx:
        rc = self._send([to, sig, *[str(a) for a in args or []]], role, label or sig.split("(")[0], to)
        return rc["_tx"]

    def _pin(self) -> list[str]:
        """Read at the block of our last sealed write (never older): `latest` can lag behind it on another node."""
        return ["--block", str(self._read_block)] if self._read_block else []

    def call(self, to: str, sig: str, args: list | None = None) -> str:
        out = self._read([tool("cast"), "call", "--rpc-url", self.net.rpc, *self._pin(), to, sig,
                          *[str(a) for a in args or []]], timeout=120)
        if out.returncode:
            text = out.stdout + out.stderr
            rev = self._decode_revert(text)
            if rev:
                raise rev
            raise RuntimeError(f"cast call failed: {text.strip()[:400]}")
        return out.stdout.strip()

    def fund(self, role: str, wei: int, from_role: str = "admin") -> Tx:
        """Send exactly `wei` (an integer: no float rounding) to a role wallet. How much is decided by the caller's
        funding plan, which is re-checked after the transfers."""
        if role == from_role or wei <= 0:
            raise ValueError(f"refusing to fund {role} with {wei} wei from {from_role}")
        rc = self._send([self.addr(role), "--value", str(int(wei))], from_role, f"fund {role}")
        return rc["_tx"]

    def rpc(self, method: str, *params) -> str:
        out = self._read([tool("cast"), "rpc", "--rpc-url", self.net.rpc, method, *[str(p) for p in params]])
        if out.returncode:
            raise RuntimeError(out.stderr)
        return out.stdout.strip()


def _type(inp: dict) -> str:
    t = inp["type"]
    if t.startswith("tuple"):
        inner = ",".join(_type(c) for c in inp["components"])
        return f"({inner}){t[5:]}"
    return t


def _checksum(a: str) -> str:
    out = run([tool("cast"), "to-check-sum-address", a])
    return out.stdout.strip() if out.returncode == 0 else a


def start_anvil(port: int = 8545, timestamp: int | None = None) -> subprocess.Popen:
    """Local replay chain. `timestamp` sets the genesis clock (used to replay a past week in its own time)."""
    args = [tool("anvil"), "--port", str(port), "--silent", "--gas-limit", "60000000"]
    if timestamp:
        args += ["--timestamp", str(timestamp)]
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(75):
        time.sleep(0.2)
        if run([tool("cast"), "chain-id", "--rpc-url", f"http://127.0.0.1:{port}"], timeout=5).returncode == 0:
            return p
    p.kill()
    raise RuntimeError(f"anvil did not start on port {port} (port in use?)")
