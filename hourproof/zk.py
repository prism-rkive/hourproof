"""Noir + Barretenberg (UltraHonk) wrappers for the coverage and residual-emissions proofs.

  commit_load(load_kwh, salt)          -> commitment (run by the data hub; load_commit circuit)
  prove(load_kwh, salt, bps, cert_kwh) -> proof + public inputs (run by the buyer; coverage circuit)
  prove_emissions(load_kwh, salt, bps, cap_kg, cert_kwh, intensity_g)
                                        -> proof + public inputs (run by the buyer; emissions circuit)
  build_verifier()                      -> contracts/src/generated/HonkVerifier.sol (coverage) and
                                           contracts/src/generated/EmissionsHonkVerifier.sol (emissions)
Load never leaves the prover; only the commitment, the threshold, the cap, the certificate vector and the
(public) hourly grid intensity are public. Both circuits output the SAME commitment (hp_lib::commit_load), so
one data-hub attestation serves both proofs.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from .chain import run, tool
from .config import CIRCUITS, CONTRACTS, DATA, HOURS

TARGET = CIRCUITS / "target"
GENERATED = CONTRACTS / "src" / "generated" / "HonkVerifier.sol"
EMISSIONS_GENERATED = CONTRACTS / "src" / "generated" / "EmissionsHonkVerifier.sol"
ZK_META = DATA / "zk_meta.json"
EIP170_LIMIT = 24_576  # bytes of runtime code per contract
EMISSIONS_PREFIX = "Emissions"

# vk directory, generated verifier file, prefix for every contract/library/interface name in it, public inputs
CIRCUIT_SPECS = {
    "coverage": {"vk_dir": TARGET, "generated": GENERATED, "prefix": "", "public_inputs": HOURS + 2},
    "emissions": {"vk_dir": TARGET / "emissions_vk", "generated": EMISSIONS_GENERATED, "prefix": EMISSIONS_PREFIX,
                  "public_inputs": 2 * HOURS + 3},
}


class ProverRefused(RuntimeError):
    """The witness does not satisfy the circuit (e.g. the claimed coverage is higher than the truth)."""


def _toml(values: dict) -> str:
    out = []
    for k, v in values.items():
        if isinstance(v, list):
            out.append(f"{k} = [{', '.join(str(int(x)) for x in v)}]")
        elif isinstance(v, str):
            out.append(f'{k} = "{v}"')
        else:
            out.append(f"{k} = {int(v)}")
    return "\n".join(out) + "\n"


def _check(load: list[int], cert: list[int] | None = None, intensity: list[int] | None = None) -> None:
    vectors = [load] + [v for v in (cert, intensity) if v is not None]
    if any(len(v) != HOURS for v in vectors):
        raise ValueError(f"need exactly {HOURS} hourly values")
    for x in (x for v in vectors for x in v):
        if not 0 <= int(x) < 2**32:
            raise ValueError("hourly values must fit u32 (kWh, g/kWh)")


def compile_circuits() -> None:
    out = run([tool("nargo"), "compile", "--workspace"], cwd=CIRCUITS, timeout=900)
    if out.returncode:
        raise RuntimeError(f"nargo compile failed:\n{out.stdout}{out.stderr}")


def max_bps(load_kwh: list[int], cert_kwh: list[int]) -> int:
    """Exactly the circuit's integer arithmetic: the highest threshold the truth supports."""
    matched = sum(min(int(l), int(c)) for l, c in zip(load_kwh, cert_kwh))
    total = sum(int(l) for l in load_kwh)
    return matched * 10000 // total


def residual_g(load_kwh: list[int], cert_kwh: list[int], intensity_g: list[int]) -> int:
    """sum_h (load_h - min(load_h, cert_h)) * intensity_h in grams, exactly as the emissions circuit."""
    return sum((int(l) - min(int(l), int(c))) * int(i) for l, c, i in zip(load_kwh, cert_kwh, intensity_g))


def min_cap_kg(load_kwh: list[int], cert_kwh: list[int], intensity_g: list[int]) -> int:
    """The lowest cap (whole kg) the truth supports: the residual rounded UP to the next kg."""
    return -(-residual_g(load_kwh, cert_kwh, intensity_g) // 1000)


def commit_load(load_kwh: list[int], salt: int) -> str:
    _check(load_kwh)
    if not (TARGET / "load_commit.json").exists():
        compile_circuits()
    (CIRCUITS / "load_commit" / "Prover.toml").write_text(_toml({"load": load_kwh, "salt": str(salt)}))
    out = run([tool("nargo"), "execute", "--package", "load_commit"], cwd=CIRCUITS, timeout=600)
    m = re.search(r"Circuit output: (0x[0-9a-fA-F]+)", out.stdout + out.stderr)
    if out.returncode or not m:
        raise RuntimeError(f"load_commit failed:\n{out.stdout}{out.stderr}")
    return "0x" + m.group(1)[2:].rjust(64, "0")


def ensure_vk(circuit: str = "coverage") -> Path:
    spec = CIRCUIT_SPECS[circuit]
    if not (TARGET / f"{circuit}.json").exists():
        compile_circuits()
    vk = spec["vk_dir"] / "vk"
    if not vk.exists() or vk.stat().st_mtime < (TARGET / f"{circuit}.json").stat().st_mtime:
        spec["vk_dir"].mkdir(parents=True, exist_ok=True)
        out = run([tool("bb"), "write_vk", "-b", str(TARGET / f"{circuit}.json"), "-o", str(spec["vk_dir"]), "-t", "evm"],
                  timeout=1800)
        if out.returncode:
            raise RuntimeError(f"bb write_vk failed (first run downloads the CRS; needs internet):\n{out.stdout}{out.stderr}")
    return vk


def _prove(circuit: str, inputs: dict, outdir: Path, refusal: str) -> dict:
    if not (TARGET / f"{circuit}.json").exists():
        compile_circuits()
    (CIRCUITS / circuit / "Prover.toml").write_text(_toml(inputs))
    out = run([tool("nargo"), "execute", "--package", circuit], cwd=CIRCUITS, timeout=900)
    if out.returncode:
        if "Cannot satisfy constraint" in out.stdout + out.stderr or "Failed constraint" in out.stdout + out.stderr:
            raise ProverRefused(refusal)
        raise RuntimeError(f"nargo execute failed:\n{out.stdout}{out.stderr}")
    vk = ensure_vk(circuit)  # after witness generation: a false claim is refused before any proving work
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    out = run([tool("bb"), "prove", "-b", str(TARGET / f"{circuit}.json"), "-w", str(TARGET / f"{circuit}.gz"),
               "-k", str(vk), "-o", str(outdir), "-t", "evm"], timeout=1800)
    if out.returncode:
        raise RuntimeError(f"bb prove failed:\n{out.stdout}{out.stderr}")
    secs = time.time() - t0
    proof = (outdir / "proof").read_bytes()
    pubs = (outdir / "public_inputs").read_bytes()
    public_inputs = ["0x" + pubs[i:i + 32].hex() for i in range(0, len(pubs), 32)]
    if len(public_inputs) != CIRCUIT_SPECS[circuit]["public_inputs"]:
        raise RuntimeError(f"unexpected public input count {len(public_inputs)}")
    v = run([tool("bb"), "verify", "-k", str(vk), "-p", str(outdir / "proof"), "-i", str(outdir / "public_inputs"),
             "-t", "evm"], timeout=600)
    return {"proof": "0x" + proof.hex(), "public_inputs": public_inputs, "prove_seconds": round(secs, 2),
            "native_verify": v.returncode == 0, "proof_bytes": len(proof)}


def prove(load_kwh: list[int], salt: int, threshold_bps: int, cert_kwh: list[int], outdir: Path) -> dict:
    _check(load_kwh, cert_kwh)
    return _prove("coverage", {"load": load_kwh, "salt": str(salt), "threshold_bps": threshold_bps, "cert": cert_kwh},
                  outdir, f"coverage >= {threshold_bps / 100:.2f}% is false for this data; no proof can exist")


def prove_emissions(load_kwh: list[int], salt: int, threshold_bps: int, cap_kg: int, cert_kwh: list[int],
                    intensity_g: list[int], outdir: Path) -> dict:
    """Coverage >= threshold AND residual (unmatched) emissions <= cap_kg; public inputs in circuit order:
    [threshold_bps, cap_kg, cert_kwh[168], intensity_g_per_kwh[168], load_commitment]."""
    _check(load_kwh, cert_kwh, intensity_g)
    if not 0 <= int(cap_kg) < 2**64:
        raise ValueError("cap_kg must fit u64")
    return _prove("emissions", {"load": load_kwh, "salt": str(salt), "threshold_bps": threshold_bps, "cap_kg": cap_kg,
                                "cert": cert_kwh, "intensity": intensity_g}, outdir,
                  f"coverage >= {threshold_bps / 100:.2f}% and residual <= {cap_kg:,} kg is false for this data; "
                  "no proof can exist")


def rename_generated(src: str, prefix: str) -> str:
    """bb names every verifier HonkVerifier and reuses its library names (RelationsLib, ...). Prefix every
    contract, library and interface declared in the file so two verifiers can live in one Foundry project
    and `Chain.artifact(name)` / library linking find exactly one artifact per name."""
    if not prefix:
        return src
    names = re.findall(r"^\s*(?:abstract\s+)?(?:contract|library|interface)\s+(\w+)", src, re.M)
    for n in sorted(set(names), key=len, reverse=True):
        src = re.sub(rf"(?<![\w$]){n}(?![\w$])", prefix + n, src)
    return src


def _write_verifier(circuit: str) -> str:
    spec = CIRCUIT_SPECS[circuit]
    vk = ensure_vk(circuit)
    out_file: Path = spec["generated"]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out = run([tool("bb"), "write_solidity_verifier", "-k", str(vk), "-o", str(out_file), "-t", "evm"], timeout=600)
    if out.returncode:
        raise RuntimeError(f"bb write_solidity_verifier ({circuit}) failed:\n{out.stdout}{out.stderr}")
    out_file.write_text(rename_generated(out_file.read_text(), spec["prefix"]))
    names = re.findall(r"^contract\s+(\w+)", out_file.read_text(), re.M)
    want = spec["prefix"] + "HonkVerifier"
    return want if want in names else names[-1]


def build_verifier() -> dict:
    """Generate both Solidity verifiers into contracts/src/generated/."""
    meta = {"verifier_contract": _write_verifier("coverage"),
            "emissions_verifier_contract": _write_verifier("emissions"),
            "nargo": run([tool("nargo"), "--version"]).stdout.splitlines()[0],
            "bb": run([tool("bb"), "--version"]).stdout.strip(),
            "generated": str(GENERATED.relative_to(CONTRACTS)),
            "emissions_generated": str(EMISSIONS_GENERATED.relative_to(CONTRACTS))}
    ZK_META.write_text(json.dumps(meta, indent=2))
    return meta


def runtime_sizes() -> dict[str, int]:
    """Runtime bytecode size of every contract/library in the generated verifiers (after `forge build`)."""
    sizes = {}
    for gen in (GENERATED, EMISSIONS_GENERATED):
        for f in sorted((CONTRACTS / "out" / gen.name).glob("*.json")):
            obj = json.loads(f.read_text()).get("deployedBytecode", {}).get("object", "").removeprefix("0x")
            if obj:
                sizes[f"{gen.name}:{f.stem}"] = len(obj) // 2
    return sizes


def check_eip170() -> dict[str, int]:
    """EIP-170: every runtime must be <= 24,576 bytes, or it cannot be deployed. Records the sizes in zk_meta."""
    sizes = runtime_sizes()
    if not any(k.startswith(EMISSIONS_GENERATED.name) for k in sizes):
        raise RuntimeError("emissions verifier artifacts not found: run `forge build` in contracts/")
    if ZK_META.exists():
        meta = json.loads(ZK_META.read_text())
        meta["runtime_bytes"] = sizes
        ZK_META.write_text(json.dumps(meta, indent=2))
    over = {k: v for k, v in sizes.items() if v > EIP170_LIMIT}
    if over:
        raise RuntimeError(f"EIP-170: runtime bytecode above {EIP170_LIMIT:,} bytes: {over}")
    return sizes


def verifier_ready() -> bool:
    return GENERATED.exists() and ZK_META.exists()


def emissions_verifier_ready() -> bool:
    return EMISSIONS_GENERATED.exists() and ZK_META.exists() and "emissions_verifier_contract" in json.loads(ZK_META.read_text())


def bb_installed() -> bool:
    return shutil.which("bb") is not None or (Path.home() / ".bb" / "bb").exists()
