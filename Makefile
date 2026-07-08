# Developer entry points — tiers mirror ADR-0011 and .pre-commit-config.yaml.
# The fast tiers (lint/type/test) also run automatically via the git hooks;
# these targets are for running them on demand.
.PHONY: sync check lint type test audit rebuild-db

sync: ## Install deps + dev toolchain (editable)
	uv sync --all-extras

check: lint type test ## Fast gate: lint + type + test (pre-commit / pre-push parity)

lint:
	uv run ruff check
	uv run ruff format --check

type:
	uv run mypy

test:
	uv run pytest

audit: ## Batch/milestone tier: dependency vulnerability scan
	uv run pip-audit

# Replay a JSONL event ledger into a fresh SQLite projection (ADR-0002). The DB is
# disposable and rebuilt from the authoritative log. Override LEDGER=/DB= as needed.
LEDGER ?= run.events.jsonl
DB ?= pipeguard.sqlite
rebuild-db: ## Rebuild the SQLite projection from a JSONL ledger (LEDGER=... DB=...)
	uv run python -m pipeguard.persistence.rebuild $(LEDGER) $(DB)

# The other half of the batch tier — full evaluation vs GIAB / synthetic truth —
# is deferred to Phase 2 (needs the eval harness; see tasks.md T-009).
