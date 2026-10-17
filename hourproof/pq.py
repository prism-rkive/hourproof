"""Post-quantum issuer keys: FIPS 204 ML-DSA-44 (dilithium-py), verified on-chain by the vendored
Fireblocks verifier. Keys live in data/keys/ (git-ignored). Testnet/demo keys only."""
from __future__ import annotations

import json
import subprocess
import sys

from .config import CONTRACTS, KEYS

VENDOR = CONTRACTS / "lib" / "evm-ml-dsa-verifier"


def _mldsa():
    try:
        from dilithium_py.ml_dsa import ML_DSA_44
    except ImportError as e:  # pragma: no cover
        raise SystemExit("dilithium-py missing: pip install -r requirements.txt") from e
    return ML_DSA_44


def issuer_key(name: str) -> dict:
    """Load (or create once) an ML-DSA-44 issuer key pair, plus its prepared on-chain blob."""
    f = KEYS / f"issuer_{name}.json"
    if f.exists():
        return json.loads(f.read_text())
    pk, sk = _mldsa().keygen()
    rec = {"name": name, "scheme": "ML-DSA-44 (FIPS 204)", "pk": pk.hex(), "sk": sk.hex(), "blob": prepare_blob(pk.hex())}
    f.write_text(json.dumps(rec))
    return rec


def prepare_blob(pk_hex: str) -> str:
    out = subprocess.run([sys.executable, "-I", str(VENDOR / "prepare" / "prepare.py"), pk_hex],
                         capture_output=True, text=True, check=True)
    blob = out.stdout.strip()
    if len(blob) != 41090:
        raise RuntimeError("unexpected ML-DSA public-key blob size")
    return blob


def sign(sk_hex: str, message: bytes) -> str:
    sig = _mldsa().sign(bytes.fromhex(sk_hex), message)
    assert len(sig) == 2420
    return "0x" + sig.hex()


def verify(pk_hex: str, message: bytes, sig_hex: str) -> bool:
    return _mldsa().verify(bytes.fromhex(pk_hex), message, bytes.fromhex(sig_hex.removeprefix("0x")))


def helper_runtime() -> str:
    return (VENDOR / "helpers" / "f1600_170.hex").read_text().strip()
