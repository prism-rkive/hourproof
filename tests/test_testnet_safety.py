import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hourproof import config, verify
from hourproof.config import ANVIL_KEYS, testnet_key

GOOD = "0x" + "1f" * 32  # a syntactically valid TEST-ONLY key, never funded


class KeyValidationTests(unittest.TestCase):
    def _refused(self, value: str) -> str:
        with self.assertRaises(SystemExit) as e:
            testnet_key(value)
        msg = str(e.exception)
        if len(value) > 12:
            self.assertNotIn(value.removeprefix("0x")[:12], msg)  # the value is never echoed
        return msg

    def test_accepts_and_normalises(self):
        self.assertEqual(testnet_key(GOOD.upper().replace("0X", "0x")), GOOD)
        self.assertEqual(testnet_key(GOOD[2:]), GOOD)

    def test_refuses_missing_placeholder_malformed(self):
        self.assertIn("not set", self._refused(""))
        self.assertIn("placeholder", self._refused("0xyour_throwaway_testnet_key"))
        self.assertIn("64 hex", self._refused("0x" + "ab" * 31))
        self.assertIn("64 hex", self._refused("0x" + "zz" * 32))
        self.assertIn("not a valid", self._refused("0x" + "00" * 32))
        self.assertIn("not a valid", self._refused("0x" + "ff" * 32))

    def test_refuses_every_public_anvil_key(self):
        for k in ANVIL_KEYS:
            self.assertIn("PUBLIC", self._refused(k))

    def test_network_uses_validated_key_and_base_sepolia_id(self):
        with mock.patch.dict("os.environ", {"PRIVATE_KEY": ANVIL_KEYS[0]}):
            with self.assertRaises(SystemExit):
                config.base_sepolia_network()
        self.assertEqual(config.BASE_SEPOLIA_CHAIN_ID, 84532)


class CalldataTests(unittest.TestCase):
    def test_decodes_submit_calldata(self):
        proof = bytes(range(70))
        words = [7, 7500, 3 * 32]
        enc = b"".join(w.to_bytes(32, "big") for w in words) + len(proof).to_bytes(32, "big") + proof + b"\0" * 26
        args, got = verify._decode_submit("0xdeadbeef" + enc.hex(), 2)
        self.assertEqual(args, [7, 7500])
        self.assertEqual(got, proof)
        words = [3, 4476, 1_842_741, 4 * 32]
        enc = b"".join(w.to_bytes(32, "big") for w in words) + len(proof).to_bytes(32, "big") + proof + b"\0" * 26
        args, got = verify._decode_submit("0x12345678" + enc.hex(), 3)
        self.assertEqual(args, [3, 4476, 1_842_741])
        self.assertEqual(got, proof)


class FundingPlanTests(unittest.TestCase):
    """The public-chain funding plan: derived from a measured run, priced at the fee cap, fail closed."""
    GAS = {"admin": 41_383_350, "buyer": 26_376_889, "issuer_ops": 24_035_585, "oracle": 20_768_628,
           "agent": 1_193_211, "investor": 264_027, "datahub": 49_397, "ghost": 0}
    FEE = 11_000_000  # 0.011 gwei = 2 x 0.005 base + 0.001 priority, as on Base Sepolia on 17 Oct 2026

    class FakeChain:
        def __init__(self, fee_wei, balances_wei):
            self.fee, self.balances = fee_wei, balances_wei

        def fee_cap_wei(self):
            return self.fee

        def balance_wei(self, role):
            return self.balances.get(role, 0)

        def addr(self, role):
            return f"0x{role}"

    def plan(self, balances):
        from hourproof.demo import funding_plan
        return funding_plan(self.FakeChain(self.FEE, balances), self.GAS, "test-run")

    def test_targets_are_margin_times_measured_gas_at_the_fee_cap(self):
        from hourproof.demo import GAS_MARGIN, RESERVE_GAS, TRANSFER_GAS
        p = self.plan({})
        for r, v in p["roles"].items():
            self.assertEqual(v["target_wei"], GAS_MARGIN * max(self.GAS[r], RESERVE_GAS.get(r, 0)) * self.FEE)
        self.assertEqual(p["admin_target_wei"], GAS_MARGIN * (self.GAS["admin"] + TRANSFER_GAS * 7) * self.FEE)
        self.assertEqual(p["admin_needs_wei"], sum(v["to_send_wei"] for v in p["roles"].values()) + p["admin_target_wei"])

    def test_ready_exactly_at_the_requirement_not_one_wei_below(self):
        need = self.plan({})["admin_needs_wei"]
        self.assertTrue(self.plan({"admin": need})["ready"])
        p = self.plan({"admin": need - 1})
        self.assertFalse(p["ready"])
        self.assertEqual(p["shortfall_wei"], 1)

    def test_partly_funded_role_is_topped_up_to_its_full_target(self):
        target = self.plan({})["roles"]["buyer"]["target_wei"]
        p = self.plan({"buyer": target * 6 // 10})  # the old rule (skip above half) would have sent nothing
        self.assertEqual(p["roles"]["buyer"]["to_send_wei"], target - target * 6 // 10)
        self.assertEqual(self.plan({"buyer": target})["roles"]["buyer"]["to_send_wei"], 0)

    def test_ghost_keeps_a_reserve_for_gas_estimation(self):
        from hourproof.demo import GAS_MARGIN, RESERVE_GAS
        self.assertEqual(self.plan({})["roles"]["ghost"]["target_wei"], GAS_MARGIN * RESERVE_GAS["ghost"] * self.FEE)

    def test_post_funding_check_fails_closed(self):
        from hourproof.demo import assert_funded
        full = {r: v["target_wei"] for r, v in self.plan({})["roles"].items()}
        admin_own = self.plan(full)["admin_target_wei"]
        assert_funded(self.plan(full | {"admin": admin_own}))  # everything at target: passes
        with self.assertRaises(RuntimeError):
            assert_funded(self.plan(full | {"admin": admin_own - 1}))
        with self.assertRaises(RuntimeError):
            assert_funded(self.plan(full | {"admin": admin_own, "oracle": full["oracle"] - 1}))

    def test_higher_fee_raises_the_requirement(self):
        from hourproof.demo import funding_plan
        low = funding_plan(self.FakeChain(self.FEE, {}), self.GAS, "t")["admin_needs_wei"]
        high = funding_plan(self.FakeChain(10 * self.FEE, {}), self.GAS, "t")["admin_needs_wei"]
        self.assertEqual(high, 10 * low)

    def test_fee_cap_bounds_what_cast_charges_and_fails_closed(self):
        from types import SimpleNamespace
        from hourproof.chain import Chain
        from hourproof.config import local_network

        class C(Chain):
            def __init__(self, base, tip, price, fail=False):
                super().__init__(local_network())
                self.vals = {"baseFeePerGas": str(base), "eth_maxPriorityFeePerGas": f'"{hex(tip)}"'}
                self.price, self.fail = price, fail

            def _read(self, args, timeout=60):
                key = next(k for k in self.vals if k in args)
                return SimpleNamespace(returncode=1 if self.fail else 0, stdout=self.vals[key], stderr="rpc down")

            def gas_price_wei(self):
                return self.price

        # cast send uses maxFeePerGas = 2 x base + priority (measured: 2 x 1 gwei + 1 wei on anvil)
        self.assertEqual(C(5_000_000, 1_000_000, 6_000_000).fee_cap_wei(), 11_000_000)
        self.assertEqual(C(1, 1, 50).fee_cap_wei(), 50)  # never below the node's gas price
        with self.assertRaises(RuntimeError):
            C(5, 1, 6, fail=True).fee_cap_wei()
        with self.assertRaises(RuntimeError):
            C(0, 0, 0).fee_cap_wei()

    def test_fund_refuses_non_positive_amounts(self):
        from hourproof.chain import Chain
        from hourproof.config import local_network
        ch = Chain(local_network())
        for wei in (0, -1):
            with self.assertRaises(ValueError):
                ch.fund("buyer", wei)


class MeasuredPlanTests(unittest.TestCase):
    """The plan is derived only from a successful REAL local run of the same mode and week."""

    def _write(self, d: Path, run_id: str, **kw):
        st = {"run_id": run_id, "network": "local", "zk_mode": "real", "mode": "carbon", "status": "done",
              "window": {"window_start_unix": 100},
              "steps": [{"txs": [{"role": "admin", "gas": 10}, {"role": "buyer", "gas": 7}, {"role": "buyer", "gas": 3}]}]}
        st.update(kw)
        (d / run_id).mkdir()
        (d / run_id / "state.json").write_text(json.dumps(st))

    def test_newest_matching_run_wins_and_others_are_ignored(self):
        from hourproof.demo import planned_gas_by_role
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._write(d, "20260101T000000Z")
            self._write(d, "20260102T000000Z", zk_mode="mock")
            self._write(d, "20260103T000000Z", status="failed")
            self._write(d, "20260104T000000Z", mode="procurement")
            self._write(d, "20260105T000000Z", window={"window_start_unix": 999})
            self._write(d, "20260106T000000Z", steps=[{"txs": [{"gas": 5}]}])  # no per-role records
            gas, src = planned_gas_by_role("carbon", 100, runs=d)
            self.assertEqual(src, "20260101T000000Z")
            self.assertEqual((gas["admin"], gas["buyer"], gas["ghost"]), (10, 10, 0))

    def test_no_measured_run_fails_closed(self):
        from hourproof.demo import planned_gas_by_role
        with tempfile.TemporaryDirectory() as d:
            self._write(Path(d), "20260101T000000Z", zk_mode="mock")
            with self.assertRaises(SystemExit):
                planned_gas_by_role("carbon", 100, runs=Path(d))


class AttackCheckTests(unittest.TestCase):
    """An underfunded wallet can only make an attack check FAIL: its error is not a contract revert."""

    def test_insufficient_funds_is_never_decoded_as_a_contract_error(self):
        from hourproof.chain import Chain
        from hourproof.config import local_network
        ch = Chain(local_network())
        for text in ("server returned an error response: error code -32003: insufficient funds for gas * price + value: "
                     "balance 0, tx cost 59400000000000, overshot 59400000000000",
                     "error code -32000: gas required exceeds allowance (0)"):
            self.assertIsNone(ch._decode_revert(text))


@unittest.skipUnless(shutil.which("cast"), "needs foundry's cast")
class WalletNewTests(unittest.TestCase):
    def test_writes_key_to_env_and_prints_only_the_address(self):
        from hourproof import __main__ as cli
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / ".env.example").write_text("BASE_SEPOLIA_RPC=https://sepolia.base.org\nPRIVATE_KEY=0xyour_throwaway_testnet_key\n")
            buf = io.StringIO()
            with mock.patch.object(cli, "ROOT", d), contextlib.redirect_stdout(buf):
                cli.wallet_new()
            env = (d / ".env").read_text()
            key = next(line.split("=", 1)[1] for line in env.splitlines() if line.startswith("PRIVATE_KEY="))
            self.assertEqual(testnet_key(key), key)
            self.assertIn("BASE_SEPOLIA_RPC=https://sepolia.base.org", env)
            out = buf.getvalue()
            self.assertNotIn(key[2:], out)
            self.assertIn("Address to fund", out)
            with mock.patch.object(cli, "ROOT", d), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as e:
                    cli.wallet_new()  # never overwrites a valid key
            self.assertIn("not overwriting", str(e.exception))
            self.assertEqual((d / ".env").read_text(), env)


if __name__ == "__main__":
    unittest.main()
