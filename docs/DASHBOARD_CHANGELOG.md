# Dashboard redesign (October 2026)

The dashboard moved from one page of plain HTML/JS (`web/`) to a multi-page app (`frontend/`). This was a
presentation change only: no data, number, calculation, contract, script or proof changed. Every figure is read
from the same API.

## Data and export
- `/api/overview` gains `annual_match`, computed from `data/hourly.csv` and the backtest's portfolio share (it is
  100 %; the old page had it typed in). `/api/carbon` gains `frozen_config` (`flex_share`, `flex_cap`).
- The snapshot stores the note count (1,000) with its source, `totalSupply()` of the note contract read once at
  export time. The hosted site never calls the chain.
- The verified run's console output is committed as `evidence/.../console.txt` (secret-scanned, SHA-256 in the
  evidence README) and served at `/api/demo/log`.

## Pages
- **Overview:** the annual vs hourly match, key results with their period labelled, the week heatmap (fixed portfolio or
  with the agent), what the chain sees vs what the buyer sees, and how it works.
- **Proof run:** every step with a plain-language line, all 80 transactions, the independent checks, and the recorded log.
- **Security:** each attack with what refused it, the run's own note, and an honest transaction status.
- **Agent:** strategies, forecast skill, and the plans' commit and reveal transactions.
- **Carbon:** emissions by strategy, robustness, the on-chain proof, forecast vs actual, and the intensity week.
- **Note:** outcome, term sheet, how the coupon and the target are set, and the settlement.
- **Method:** "What this does not claim" (word for word, under `#limits`), data, parameters, cryptography,
  contracts, glossary.

## Behaviour kept
- The run status ("Last run … passed") and the run buttons work as before: they start and poll on a local server
  and are disabled on the hosted snapshot.
- Every transaction link, now with none hidden behind "+N more".

## Engineering
- Pages are prerendered at build time from the snapshot and hydrated in the browser. Charts load near the
  viewport, and below-the-fold layout is deferred.
- Node 22 and npm 11.20 are pinned (`engines`, `packageManager`, `engine-strict`); Vercel installs with
  `npx npm@11.20.0 ci`.
- Tests:
  - Python: the export fields, the log, the build output and the local server's page routing.
  - Vitest: every displayed figure against the snapshot, and a period label on every figure.
  - Playwright: every page in both themes at 375 and 1440 px, and no console or hydration errors.
- Before `web/` was removed, a parity test compared it with the new site on the same snapshot, locally and against
  production: every figure the old page showed, and all 80 transaction links, are on the new site. The original
  "What this does not claim" block is kept as a test fixture.
