.PHONY: demo test list demo-all catalog demo-orchestrator \
        install install-spatial-domains install-full install-dev \
        bot-telegram bot-feishu

## ── Virtual-environment + installation targets ──────────────────────────────

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

## ── Bot targets ─────────────────────────────────────────────────────────────

bot-telegram:
	python bot/telegram_bot.py

bot-feishu:
	python bot/feishu_bot.py
