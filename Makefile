# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores
.DEFAULT_GOAL := help
.PHONY: help setup doctor run lint test coverage check install-hooks

help:
	@printf '%s\n' 'Serifa development commands:' \
	  '  make setup          Prepare the development environment' \
	  '  make doctor         Check Python and system libraries' \
	  '  make run            Open Serifa' \
	  '  make lint           Run Ruff' \
	  '  make test           Run the test suite' \
	  '  make coverage       Run tests with coverage' \
	  '  make check          Run lint, then tests' \
	  '  make install-hooks  Enable the pre-push checks'

setup:
	bin/setup

doctor:
	bin/python --check

run:
	bin/serifa

lint:
	bin/lint

test:
	bin/test

coverage:
	bin/test --coverage

check:
	bin/lint
	bin/test

install-hooks:
	bin/install-hooks
