import shutil
import unittest
from pathlib import Path

from hourproof import zk


class ZKMathTests(unittest.TestCase):
    def test_max_bps_matches_circuit_semantics(self):
        load = [100] * 168
        cert = [100 if i % 2 == 0 else 50 for i in range(168)]
        self.assertEqual(zk.max_bps(load, cert), 7500)
        self.assertEqual(zk.max_bps(load, [10_000] * 84 + [0] * 84), 5000)

    def test_input_validation(self):
        with self.assertRaises(ValueError):
            zk._check([1] * 10)
        with self.assertRaises(ValueError):
            zk._check([2**32] * 168)
        with self.assertRaises(ValueError):
            zk._check([1] * 168, [1] * 168, [1] * 167)

    def test_residual_matches_circuit_semantics(self):
        load = [100] * 168
        cert = [100 if i % 2 == 0 else 50 for i in range(168)]
        inten = [120] * 168
        self.assertEqual(zk.residual_g(load, cert, inten), 84 * 50 * 120)  # surplus never counts
        self.assertEqual(zk.min_cap_kg(load, cert, inten), 504)
        inten[1] = 121  # +50 g: the cap rounds UP to the next whole kg
        self.assertEqual(zk.min_cap_kg(load, cert, inten), 505)
        self.assertEqual(zk.residual_g(load, [1000] * 168, inten), 0)


class GeneratedVerifierNamingTests(unittest.TestCase):
    SRC = """pragma solidity >=0.8.21;
uint256 constant N = 65536;
library HonkVerificationKey { function f() internal pure returns (Honk.VerificationKey memory) {} }
interface IVerifier { function verify(bytes calldata, bytes32[] calldata) external view returns (bool); }
library Honk { struct VerificationKey { uint256 x; } }
library RelationsLib { function g() external pure {} }
abstract contract BaseZKHonkVerifier is IVerifier { function h() public { RelationsLib.g(); } }
contract HonkVerifier is BaseZKHonkVerifier { }
"""

    def test_every_declared_name_is_prefixed(self):
        out = zk.rename_generated(self.SRC, "Emissions")
        for n in ("HonkVerificationKey", "IVerifier", "Honk", "RelationsLib", "BaseZKHonkVerifier", "HonkVerifier"):
            self.assertIn(f"Emissions{n}", out)
        self.assertIn("EmissionsHonk.VerificationKey", out)
        self.assertIn("EmissionsRelationsLib.g()", out)
        self.assertIn("contract EmissionsHonkVerifier is EmissionsBaseZKHonkVerifier", out)
        self.assertNotIn("EmissionsEmissions", out)
        self.assertIn("uint256 constant N = 65536;", out)  # file-level items are untouched

    def test_no_prefix_is_identity(self):
        self.assertEqual(zk.rename_generated(self.SRC, ""), self.SRC)

    def test_generated_files_do_not_share_names(self):
        import re
        if not (zk.GENERATED.exists() and zk.EMISSIONS_GENERATED.exists()):
            self.skipTest("verifiers not generated yet (python -m hourproof zk build)")
        decl = r"^\s*(?:abstract\s+)?(?:contract|library|interface)\s+(\w+)"
        a = set(re.findall(decl, zk.GENERATED.read_text(), re.M))
        b = set(re.findall(decl, zk.EMISSIONS_GENERATED.read_text(), re.M))
        self.assertIn("HonkVerifier", a)
        self.assertIn("EmissionsHonkVerifier", b)
        self.assertFalse(a & b, f"shared names: {a & b}")


@unittest.skipUnless(shutil.which("nargo"), "nargo not installed")
class ZKCircuitTests(unittest.TestCase):
    def test_commitment_is_deterministic_and_salted(self):
        load = [50_000 + i for i in range(168)]
        a = zk.commit_load(load, 42)
        self.assertEqual(a, zk.commit_load(load, 42))
        self.assertNotEqual(a, zk.commit_load(load, 43))
        self.assertEqual(len(a), 66)

    def test_overclaim_is_refused_before_proving(self):
        load = [100_000] * 168
        cert = [90_000] * 168
        with self.assertRaises(zk.ProverRefused):
            zk.prove(load, 7, zk.max_bps(load, cert) + 1, cert, Path("/tmp/hp_never"))

    def test_emissions_cap_below_truth_is_refused_before_proving(self):
        load = [100_000] * 168
        cert = [90_000] * 168
        inten = [150] * 168
        cap = zk.min_cap_kg(load, cert, inten)
        with self.assertRaises(zk.ProverRefused):
            zk.prove_emissions(load, 7, 0, cap - 1, cert, inten, Path("/tmp/hp_never"))
        with self.assertRaises(zk.ProverRefused):
            zk.prove_emissions(load, 7, zk.max_bps(load, cert) + 1, cap, cert, inten, Path("/tmp/hp_never"))


if __name__ == "__main__":
    unittest.main()
