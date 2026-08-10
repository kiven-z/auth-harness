.PHONY: auth-test install seed cleanup smoke p0 integration reconcile run preflight test impact dept-scope dept-scope-list data-scope perms-scan perms-check perms-gen perms-apply

VENV ?= .venv
PYTHON := $(VENV)/bin/python

install:
	@if [ ! -x "$(PYTHON)" ] || ! $(PYTHON) -m pip --version >/dev/null 2>&1; then \
		rm -rf $(VENV); \
		python3 -m venv $(VENV); \
		$(PYTHON) -m ensurepip --upgrade; \
	fi
	@$(PYTHON) -m pip install -r requirements.txt || { \
		rm -rf $(VENV); \
		python3 -m venv $(VENV); \
		$(PYTHON) -m ensurepip --upgrade; \
		$(PYTHON) -m pip install -r requirements.txt; \
	}

seed: install
	$(PYTHON) -m auth_harness seed

cleanup: install
	$(PYTHON) -m auth_harness cleanup

smoke: install
	$(PYTHON) -m auth_harness smoke

p0: install
	$(PYTHON) -m auth_harness seed
	$(PYTHON) -m auth_harness p0

integration: install
	$(PYTHON) -m auth_harness seed
	$(PYTHON) -m auth_harness preflight
	$(PYTHON) -m auth_harness integration

impact: install
	$(PYTHON) -m auth_harness seed
	$(PYTHON) -m auth_harness impact

reconcile: install
	$(PYTHON) -m auth_harness reconcile $(ARGS)

run: install
	$(PYTHON) -m auth_harness run $(ARGS)

preflight: install
	$(PYTHON) -m auth_harness preflight

dept-scope: install
	$(PYTHON) -m auth_harness dept-scope $(ARGS)

dept-scope-list: install
	$(PYTHON) -m auth_harness dept-scope-list $(ARGS)

data-scope: install
	$(PYTHON) -m auth_harness data-scope $(ARGS)

test: install
	$(PYTHON) -m unittest discover -s tests -v

perms-scan: install
	$(PYTHON) -m auth_harness perms scan $(ARGS)

perms-check: install
	$(PYTHON) -m auth_harness perms check $(ARGS)

perms-gen: install
	$(PYTHON) -m auth_harness perms gen $(ARGS)

perms-apply: install
	$(PYTHON) -m auth_harness perms apply $(ARGS)

auth-test: p0
