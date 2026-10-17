import unittest

try:
    import dilithium_py  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "dilithium-py not installed")
class PQTests(unittest.TestCase):
    def test_sign_verify_and_blob(self):
        from dilithium_py.ml_dsa import ML_DSA_44
        from hourproof import pq
        pk, sk = ML_DSA_44.keygen()
        msg = b"HOURPROOF/v1/issue test"
        sig = pq.sign(sk.hex(), msg)
        self.assertTrue(pq.verify(pk.hex(), msg, sig))
        self.assertFalse(pq.verify(pk.hex(), msg + b"!", sig))
        self.assertEqual(len(pq.prepare_blob(pk.hex())) // 2, 20545)
        self.assertTrue(pq.helper_runtime().startswith(("0x", "6")) or len(pq.helper_runtime()) > 1000)


if __name__ == "__main__":
    unittest.main()
