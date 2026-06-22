.PHONY: auth-test install seed smoke reconcile run preflight test

VENV ?= .venv
PYTHON := $(VENV)/bin/python

install:
	@if [ ! -x "$(PYTHON)" ] || ! $(PYTHON) -m pip --version >/dev/null 2>&1; then \
		rm -rf $(VENV); \
		python3 -m venv $(VENV); \
		$(PYTHON) -m ensurepip --upgrade; \
	fi
	$(PYTHON) -m pip install -r requirements.txt

seed: install
	$(PYTHON) -m auth_harness seed

smoke: install
	$(PYTHON) -m auth_harness smoke

reconcile: install
	$(PYTHON) -m auth_harness reconcile $(ARGS)

run: install
	$(PYTHON) -m auth_harness run $(ARGS)

preflight: install
	$(PYTHON) -m auth_harness preflight

test: install
	$(PYTHON) -m unittest discover -s tests -v

auth-test: smoke
