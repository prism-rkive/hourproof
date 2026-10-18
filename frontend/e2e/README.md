# Browser tests (Playwright)

```bash
npx playwright test                         # against the local production build (vite preview + the snapshot API)
HP_BASE_URL=https://hourproof-phi.vercel.app HP_SHOTS=e2e/screenshots/production npx playwright test   # a deployed site
```

- `pages.spec.ts`: every page and the 404 page at 375 and 1440 px in both themes, as full-page screenshots in
  `e2e/screenshots/`. It fails on any console error (React reports hydration mismatches there) or sideways scroll.
- `shell.spec.ts`, `overview.spec.ts`: navigation, theme, skip link, run status, deep links, the week toggle and
  heatmap keyboard, the glossary and nav hints, no requests to other sites, and the `#limits` anchor.

## Wait until the page is interactive

Pages are prerendered, so their controls are visible before React attaches to them, and a click in that window is
lost. This happens on any server-rendered site, typically for well under a second. Once the first render has
committed, the shell sets `<html data-hydrated="true">`. Every test waits for that marker before clicking, typing
or toggling (see the `ready()` helpers), never on retries.

This was the one flaky test: in 1 of 10 full runs, the week toggle was clicked about 1.7 s after navigation and
before hydration, so the caption never changed. Delaying the page's code by 2 s reproduces it every time without
the wait and never with it.

After the fix, the suite ran 10 times in a row with `--retries=0 --trace=retain-on-failure`: 10 of 10 runs passed
(49 tests each, 490 executions), and no traces were kept.
