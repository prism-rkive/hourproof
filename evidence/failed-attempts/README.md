# Failed Base Sepolia attempts (kept on purpose)

Byte-identical copies of the run state of the two public attempts that did not complete. Signing keys were scrubbed when
the state was written; a scan for the admin key and every derived key finds none.

- `20261016T223327Z/state.json`: 55 transactions, stopped at certificate issuance day 4 with `BadIssuerSignature`
  (stale read on a Flashblocks RPC). 0.000434166 ETH.
- `20261017T132115Z/state.json`: 2 funding top-ups, stopped on a DNS failure during a Wi-Fi outage. 0.000000252 ETH.

Root causes, fixes and the regression tests that reproduce them: [docs/BASE_SEPOLIA.md](../../docs/BASE_SEPOLIA.md).
The verified run is in [`../base-sepolia-20261017T141639Z/`](../base-sepolia-20261017T141639Z/).
