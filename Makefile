.PHONY: auth-test install seed smoke reconcile run

VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install:
	python3 -m venv $(VENV) || true
	$(PIP) install -r requirements.txt

seed: install
	$(PYTHON) -m auth_harness seed

smoke: install
	$(PYTHON) -m auth_harness smoke

reconcile: install
	$(PYTHON) -m auth_harness reconcile $(ARGS)

run: install
	$(PYTHON) -m auth_harness run $(ARGS)

auth-test: smoke
