"""ffi helper for Foundry tests: sign a hex message with an ML-DSA-44 secret key file.
usage: python3 test/ffi/mldsa_sign.py <sk_hex_file> <0xmessage>   -> prints 0x<signature>
"""
import sys
from pathlib import Path

from dilithium_py.ml_dsa import ML_DSA_44

sk = bytes.fromhex(Path(sys.argv[1]).read_text().strip())
msg = bytes.fromhex(sys.argv[2].removeprefix("0x"))
sys.stdout.write("0x" + ML_DSA_44.sign(sk, msg).hex())
