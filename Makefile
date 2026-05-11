.PHONY: setup-env setup-env-name \
        demo test list demo-all catalog demo-orchestrator demo-bulkrna \
        install install-spatial-domains install-full install-dev \
        install-oc oc-link \
        bot-telegram bot-feishu bot-multi bot-list \
        memory-server

## ── Conda environment (recommended, full functionality) ──────────────
## Single-command install of R 4.3, ~30 R packages, ~15 bioconda CLIs,
## OmicsClaw (editable), and all Python optional extras.
## Requires mamba (recommended) or conda — install Miniforge:
##   https://github.com/conda-forge/miniforge

setup-env:
	bash 0_setup_env.sh

# Use a custom env name: `make setup-env-name NAME=foo`
NAME ?= OmicsClaw
setup-env-name:
	bash 0_setup_env.sh "$(NAME)"

## ── Legacy lightweight venv path (Python-only skills) ────────────────────────
## NOTE: this path does NOT install R, samtools, STAR, fastqc, etc.
## For full functionality use:  make setup-env  (or: bash 0_setup_env.sh)

venv:
	python3 -m venv .venv
	@echo "Activate with: source .venv/bin/activate"

install:
	pip install -e .

install-spatial-domains:
	pip install -e ".[spatial-domains]"

install-full:
	pip install -e ".[full]"

install-dev:
	pip install -e ".[dev]"

# Install the package and register the `oc` short alias
# After this, both `omicsclaw` and `oc` commands are available system-wide.
install-oc:
	pip install -e .
	@echo ""
	@echo "✓ 'oc' command installed. Try: oc list"
	@echo "  oc interactive   → start interactive CLI"
	@echo "  oc tui           → start full-screen TUI"

# Quick symlink alternative (no pip needed, works for current user only)
# Creates ~/.local/bin/oc → project's omicsclaw.py
oc-link:
	@mkdir -p "$(HOME)/.local/bin"
	@printf '#!/usr/bin/env sh\nexec python "$(CURDIR)/omicsclaw.py" "$$@"\n' > "$(HOME)/.local/bin/oc"
	@chmod +x "$(HOME)/.local/bin/oc"
	@echo "✓ Symlink created: ~/.local/bin/oc → $(CURDIR)/omicsclaw.py"
	@echo "  Make sure ~/.local/bin is in your PATH."

# Convenience: create venv + core install in one step
setup: venv
	.venv/bin/pip install -e .

# Create venv + full install in one step
setup-full: venv
	.venv/bin/pip install -e ".[full]"

## ── Demo & test targets ──────────────────────────────────────────────────────

demo:
	python omicsclaw.py run preprocess --demo --output /tmp/omicsclaw_demo

test:
	python -m pytest -v

list:
	python omicsclaw.py list

catalog:
	python scripts/generate_catalog.py

# ADR 2026-05-11 (#1): verify every routing surface (catalog.json, every
# domain INDEX.md, CLAUDE.md routing table) stays in sync with SKILL.md
# descriptions.  Exits 1 on drift.  CI MUST call without --fix so drift is
# blocking; local dev can use `make check-drift FIX=1` for one-step repair.
check-drift:
	python scripts/check_description_drift.py $(if $(FIX),--fix,) $(if $(VERBOSE),-v,)

# ADR 2026-05-11: regenerate the Skip-when negative-routing eval snapshot.
# Default domain = spatial (the POC scope).  Set DOMAIN=<other> to extend.
# Set STUB=1 to emit a schema-only snapshot without calling the LLM.
DOMAIN ?= spatial
EVAL_OUT ?= tests/eval/skip_when_cases.json
eval-snapshot:
	python scripts/extract_skip_when_cases.py \
		--domain $(DOMAIN) \
		--output $(EVAL_OUT) \
		$(if $(STUB),--stub,)
	@echo
	@echo "Snapshot written.  Review the diff before commit:"
	@echo "  git diff -- $(EVAL_OUT)"

demo-orchestrator:
	python omicsclaw.py run orchestrator --demo --output /tmp/omicsclaw_orchestrator_demo

demo-all:
	python omicsclaw.py run preprocess --demo --output /tmp/sc_preprocess
	python omicsclaw.py run domains --demo --output /tmp/sc_domains
	python omicsclaw.py run de --demo --output /tmp/sc_de
	python omicsclaw.py run genes --demo --output /tmp/sc_genes
	python omicsclaw.py run statistics --demo --output /tmp/sc_statistics
	python omicsclaw.py run annotate --demo --output /tmp/sc_annotate
	python omicsclaw.py run deconv --demo --output /tmp/sc_deconv
	python omicsclaw.py run communication --demo --output /tmp/sc_communication
	python omicsclaw.py run condition --demo --output /tmp/sc_condition
	python omicsclaw.py run velocity --demo --output /tmp/sc_velocity
	python omicsclaw.py run trajectory --demo --output /tmp/sc_trajectory
	python omicsclaw.py run enrichment --demo --output /tmp/sc_enrichment
	python omicsclaw.py run cnv --demo --output /tmp/sc_cnv
	python omicsclaw.py run integrate --demo --output /tmp/sc_integrate
	python omicsclaw.py run register --demo --output /tmp/sc_register
	python omicsclaw.py run orchestrator --demo --output /tmp/sc_orchestrator

demo-bulkrna:
	python omicsclaw.py run bulkrna-alignment --demo --output /tmp/bulkrna_alignment
	python omicsclaw.py run bulkrna-de --demo --output /tmp/bulkrna_de
	python omicsclaw.py run bulkrna-splicing --demo --output /tmp/bulkrna_splicing
	python omicsclaw.py run bulkrna-enrichment --demo --output /tmp/bulkrna_enrichment
	python omicsclaw.py run bulkrna-deconvolution --demo --output /tmp/bulkrna_deconv
	python omicsclaw.py run bulkrna-coexpression --demo --output /tmp/bulkrna_coexpr

## ── Bot targets ─────────────────────────────────────────────────────────────

bot-telegram:
	python -m bot.run --channels telegram

bot-feishu:
	python -m bot.run --channels feishu

# Multi-channel runner (runs multiple channels in one process)
# Usage: make bot-multi CHANNELS=telegram,feishu
bot-multi:
	python -m bot.run --channels $(CHANNELS)

bot-list:
	python -m bot.run --list

## ── Memory server ───────────────────────────────────────────────────────────

memory-server:
	python omicsclaw.py memory-server

