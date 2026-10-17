# HourProof on Base Sepolia

The carbon-aware demo (`make demo-base`) was run on **Base Sepolia (chain 84532)** three times on 16–17 Oct 2026.
The first two attempts failed; the third completed and was verified on-chain. All three are recorded in
[`evidence/`](../evidence/); nothing was re-run silently, and no attempt was hidden.

| Attempt | Outcome | Transactions | ETH spent | Record |
|---|---|---:|---:|---|
| 20261016T223327Z | **Failed** at step 6 (certificate issuance, day 4): `BadIssuerSignature` | 55 | 0.000434166 | [state](../evidence/failed-attempts/20261016T223327Z/state.json) |
| 20261017T132115Z | **Failed** in the preflight: DNS failure during a Wi-Fi outage | 2 | 0.000000252 | [state](../evidence/failed-attempts/20261017T132115Z/state.json) |
| **20261017T141639Z** | **Completed, verified** (15/15 steps, 8/8 attacks refused) | 80 | 0.000684796 | [evidence bundle](../evidence/base-sepolia-20261017T141639Z/) |

Total testnet ETH spent: 0.001119 ETH. A first attempt on 14 Oct stopped before sending anything (no wallet key was
configured); it broadcast nothing and is not part of the evidence.

## Attempt 1: a read that ran ahead of the chain

`sepolia.base.org` serves Flashblocks pre-confirmations: a transaction's receipt can arrive up to ~2 s before the block
containing it is sealed as `latest` (measured: the `pending` block was 1–2 blocks ahead of `latest` in 25 of 25 samples).
The demo waited for the day-3 batch's receipt, then read the issuer's nonce at `latest`, which was still the block before
(nonce 2 instead of 3). It signed day 4 over the stale nonce and the contract, correctly, refused it with
`BadIssuerSignature`. The safeguard worked; the client's read-after-write did not.

**Fix** (`hourproof/chain.py`, `_settle`): a write returns only once the RPC's sealed `latest` block contains it and the
block hash matches the receipt (a re-org restarts the wait; 120 s timeout fails closed); every later state read is pinned
to that block. `tests/test_sealed_reads.py` reproduces the failure with a Flashblocks-like proxy in front of anvil:
without the fix the second ML-DSA batch is refused with `BadIssuerSignature`, with it both are accepted.

The 15 contracts this attempt deployed remain on Base Sepolia, unused.

## Attempt 2: a Wi-Fi outage

While signing the third funding top-up, WSL could not resolve `sepolia.base.org` (`Temporary failure in name resolution`).
The client did not treat DNS errors as transient and stopped. Signing never broadcasts, so that transfer was never sent;
the two mined top-ups were reconciled against every wallet's nonce before anything else happened.

**Fix**: DNS and connection failures are transient; one bounded backoff (3, 6, 12, 24, 30, 30 s) for reads, signing and
broadcasting; while waiting for a receipt the client re-publishes the *identical signed bytes*, so a lost broadcast
recovers and a duplicate is impossible (never a new nonce). `tests/test_network_retries.py` covers recovery, exhausted
retries, a total outage and definite rejections, using the verbatim error.

## Attempt 3: verified

See the [evidence bundle](../evidence/base-sepolia-20261017T141639Z/README.md) for every transaction, contract and file hash.
Re-check it yourself, read-only and without any key:

```bash
make verify-evidence
```

## Safeguards added for public runs

- **No secret in any output.** Timeouts never echo command arguments; every signing key is scrubbed from saved state,
  tracebacks, printed output and the dashboard; role-key derivation never puts key material on a command line.
- **No duplicate transactions.** Sign once with a pinned nonce, publish the same bytes, wait by hash.
- **Fail-closed funding.** The preflight derives each wallet's need from the measured gas of a real local run of the same
  mode and week, at the fee cap `cast` may charge, with a 3× margin; balances are re-read after funding.
- **Read-only preflight** (`make preflight-base`): chain id must be 84532; sends nothing.

## Limitations

- The note's KPI was **missed** (proven residual 546.1 t against a target of 428.5 t set by a rule fixed in code before
  the run), so the coupon stepped up. This is the honest outcome, not an error.
- The agent's plans for the replayed past week are necessarily committed after their day on a public chain; only `live`
  mode can show commit-before-the-day, and live mode was not run.
- The hosted dashboard is a static snapshot of this run; it cannot start runs (`make serve` can).
- Testnet only. Test token, demo issuers, an oracle role, unaudited ML-DSA verifier: see [SECURITY.md](SECURITY.md).
