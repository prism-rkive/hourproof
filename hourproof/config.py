"""Paths, constants and environment configuration (one place, no magic elsewhere)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
CIRCUITS = ROOT / "circuits"
DATA = Path(os.environ.get("HOURPROOF_DATA", ROOT / "data"))
CACHE = DATA / "eds_cache"
KEYS = DATA / "keys"
RUNS = DATA / "runs"
for _d in (DATA, CACHE, KEYS, RUNS):
    _d.mkdir(parents=True, exist_ok=True)

HOURS = 168  # one claim window = one week of hours; fixed by the circuit
DATASET_CSV = DATA / "hourly.csv"
DATASET_META = DATA / "hourly_meta.json"
BACKTEST_JSON = DATA / "agent_backtest.json"
PLANS_DIR = DATA / "agent_plans"
AGENT_CONFIG_JSON = DATA / "agent_config.json"            # frozen agent configuration (chosen on validation)
AGENT_EXPERIMENTS_JSON = DATA / "agent_experiments.json"  # every validation candidate, for audit
DEMO_STATE = DATA / "demo_state.json"
LIVE_JSON = DATA / "live_commits.json"
# carbon-aware mode: its own hourly file (the kill test's 8,760 hours and settlement wind; hourly.csv stays
# untouched because the frozen agent's TEST run depends on it)
CARBON_CSV = DATA / "carbon_hourly.csv"
CARBON_META = DATA / "carbon_hourly_meta.json"
CARBON_BACKTEST_JSON = DATA / "carbon_backtest.json"
CARBON_PLANS_DIR = DATA / "carbon_plans"

ZONE = "DK"                 # DK1 + DK2 together
ASSET = "DK-wind-declared"  # national declared wind production (Energinet)
AGENT_ID = "hourproof-agent-v1"


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

# Anvil's well-known development keys (public, for the LOCAL chain only).
ANVIL_KEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
    "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
    "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
]
ROLES = ["admin", "oracle", "issuer_ops", "buyer", "ghost", "datahub", "investor", "agent"]


@dataclass
class Network:
    name: str
    rpc: str
    chain_id: int
    explorer: str = ""
    keys: dict[str, str] = field(default_factory=dict)

    def tx_url(self, h: str) -> str:
        return f"{self.explorer}/tx/{h}" if self.explorer else ""

    def addr_url(self, a: str) -> str:
        return f"{self.explorer}/address/{a}" if self.explorer else ""


def local_network(port: int = 8545) -> Network:
    return Network("local", f"http://127.0.0.1:{port}", 31337, "", dict(zip(ROLES, ANVIL_KEYS)))


BASE_SEPOLIA_CHAIN_ID = 84532


def testnet_key(value: str) -> str:
    """Validate PRIVATE_KEY without ever echoing it: 32 bytes of hex, not the .env.example placeholder, and not one of
    anvil's PUBLIC development keys (anyone can drain those on a public chain)."""
    v = value.strip()
    if not v:
        raise SystemExit("PRIVATE_KEY is not set. Create a throwaway wallet with `python -m hourproof wallet new` "
                         "(writes .env, shows only the address), or see .env.example")
    if "your" in v.lower():
        raise SystemExit("PRIVATE_KEY in .env is still the .env.example placeholder. Run `python -m hourproof wallet new`")
    h = v.removeprefix("0x").removeprefix("0X")
    if len(h) != 64 or any(c not in "0123456789abcdefABCDEF" for c in h):
        raise SystemExit("PRIVATE_KEY must be 32 bytes as 64 hex characters (optional 0x prefix). The value is not shown.")
    key = "0x" + h.lower()
    if key in ANVIL_KEYS:
        raise SystemExit("PRIVATE_KEY is one of anvil's PUBLIC development keys; never use it on a public chain. "
                         "Run `python -m hourproof wallet new`")
    if int(h, 16) == 0 or int(h, 16) >= 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141:
        raise SystemExit("PRIVATE_KEY is not a valid secp256k1 private key. The value is not shown.")
    return key


def base_sepolia_network() -> Network:
    rpc = os.environ.get("BASE_SEPOLIA_RPC", "https://sepolia.base.org")
    master = testnet_key(os.environ.get("PRIVATE_KEY", ""))
    # role keys are derived from the master key, funded from it at deploy time
    from .chain import derive_key  # local import: avoids a cycle
    keys = {"admin": master} | {r: derive_key(master, r) for r in ROLES if r != "admin"}
    return Network("base-sepolia", rpc, BASE_SEPOLIA_CHAIN_ID, "https://sepolia.basescan.org", keys)
