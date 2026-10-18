# HourProof — common tasks. Run `make help`.
SHELL := /bin/bash
VENV  := .venv
PY    := $(VENV)/bin/python
export PATH := $(CURDIR)/$(VENV)/bin:$(HOME)/.hourproof/bin:$(HOME)/.foundry/bin:$(PATH)

.PHONY: help setup tools venv doctor data backtest zk fixture test test-py test-sol test-noir demo demo-base serve e2e live-commit live-score clean wallet-new preflight-base verify-base verify-evidence site web test-web

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

setup: tools venv ## install toolchain + python env, build contracts and circuits
	cd contracts && forge build
	cd circuits && nargo compile --workspace

tools:           ## pinned forge/cast/anvil/nargo/bb into ~/.hourproof/bin
	./scripts/install_tools.sh

venv:            ## python virtual environment
	test -d $(VENV) || python3 -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements.txt

doctor:          ## check everything is installed
	$(PY) -m hourproof doctor

data:            ## download real 2025 Energinet data (first time ~30-50 min, cached afterwards)
	$(PY) -m hourproof data fetch

backtest:        ## train + walk-forward-test the AI agent on real data
	$(PY) -m hourproof agent backtest

zk:              ## generate the Solidity verifier from the circuit (downloads the CRS once)
	$(PY) -m hourproof zk build

fixture:         ## real proof over a real week, for the Solidity integration test
	$(PY) -m hourproof zk fixture

test: test-py test-noir test-sol ## all tests

test-py:
	$(PY) -m unittest discover -s tests -t . -v

test-noir:
	cd circuits && nargo test --workspace

test-sol:
	cd contracts && forge test

demo:            ## full scenario with attacks on a local replay chain (real data, real proof)
	$(PY) -m hourproof demo --network local

wallet-new:      ## create a THROWAWAY testnet key in .env (prints only the address)
	$(PY) -m hourproof wallet new

preflight-base:  ## read-only Base Sepolia check: chain id 84532, balances, funding needed (sends nothing)
	$(PY) -m hourproof wallet check

demo-base:       ## the same on Base Sepolia (needs PRIVATE_KEY in .env; run preflight-base first)
	$(PY) -m hourproof demo --network base-sepolia

verify-base:     ## re-check the latest Base Sepolia run against the chain (receipts, code, proofs)
	$(PY) -m hourproof verify

site:            ## static dashboard snapshot for Vercel: deploy/snapshot/*.json + site/ (needs Node 22: make web first)
	$(PY) -m hourproof site export
	bash scripts/build_site.sh

web:             ## install and build the dashboard (frontend/, Node 22 + npm 11.20); make serve then uses it
	cd frontend && npx --yes npm@11.20.0 ci && npm run build

test-web:        ## dashboard checks: format, types, lint, unit tests, browser tests (needs make web)
	cd frontend && npm run format:check && npm run typecheck && npm run lint && npm test && npx playwright test

verify-evidence: ## re-check the committed evidence bundle on Base Sepolia (read-only, no key needed)
	$(PY) -m hourproof verify --state evidence/base-sepolia-20261017T141639Z/state.json
	python3 scripts/check_public_run.py evidence/base-sepolia-20261017T141639Z/state.json

serve:           ## dashboard on http://127.0.0.1:8000
	$(PY) -m hourproof serve

e2e:             ## everything, in order, with a checklist
	$(PY) -m hourproof e2e

live-commit:     ## commit tomorrow's agent forecast on Base Sepolia (run after 18:00 Danish time)
	$(PY) -m hourproof live commit --network base-sepolia

live-score:      ## score and reveal past live commitments
	$(PY) -m hourproof live score --network base-sepolia

clean:           ## build outputs (keeps downloaded data and keys)
	rm -rf contracts/out contracts/cache circuits/target
