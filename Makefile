PYTHON ?= python3
NPM ?= npm
UVX ?= uvx
RUFF ?= $(UVX) --from ruff==0.15.13 ruff
CLANG_FORMAT ?= $(UVX) --from clang-format==23.1.5 clang-format
JNI_SOURCES = android/app/src/main/cpp/*.cpp android/app/src/main/cpp/*.c android/app/src/main/cpp/*.h
PYTHON_SOURCES = backend/vipi backend/tests ios/*.py scripts/*.py

.PHONY: check check-source check-python check-website check-js check-shell check-jni-format check-android-format check-swift-format
.PHONY: format-python format-website format-js format-jni format-android format-swift test-relay

check: check-source check-python check-website check-js check-shell check-jni-format

check-source:
	git diff --check
	git diff --cached --check
	$(PYTHON) scripts/check-client-reading-data.py
	$(PYTHON) scripts/test-client-source-selection.py

check-python:
	$(RUFF) format --check $(PYTHON_SOURCES)
	$(RUFF) check --select E9,F63,F7,F82 $(PYTHON_SOURCES)

check-website:
	$(NPM) run check:website
	$(PYTHON) scripts/check-homepage-assets.py

check-js:
	$(NPM) run check:tools
	@set -eu; for script in scripts/*.mjs; do node --check "$$script"; done

check-shell:
	@set -eu; for script in scripts/*.sh; do \
		case "$$(head -n 1 "$$script")" in \
			*'env bash') bash -n "$$script" ;; \
			'#!/bin/zsh') zsh -n "$$script" ;; \
			*) printf 'Unknown shell for %s\n' "$$script" >&2; exit 1 ;; \
		esac; \
	done

check-jni-format:
	$(CLANG_FORMAT) --dry-run --Werror $(JNI_SOURCES)

check-android-format:
	scripts/build-android.sh checkKotlinFormat

check-swift-format:
	git ls-files -z -- 'ios/*.swift' | xargs -0 xcrun swift-format lint --strict --configuration ios/.swift-format

format-python:
	$(RUFF) format $(PYTHON_SOURCES)

format-website:
	$(NPM) run format:website
	$(PYTHON) scripts/check-homepage-assets.py --write

format-js:
	$(NPM) run format:tools

format-jni:
	$(CLANG_FORMAT) -i $(JNI_SOURCES)

format-android:
	scripts/build-android.sh formatKotlin

format-swift:
	git ls-files -z -- 'ios/*.swift' | xargs -0 xcrun swift-format format --in-place --configuration ios/.swift-format

test-relay:
	@test -n "$(RUN_DIRECTORY)" || { printf 'Set RUN_DIRECTORY to a new local path.\n' >&2; exit 1; }
	$(PYTHON) scripts/test-postgres.py --run-directory "$(RUN_DIRECTORY)" $(if $(PG_BIN),--pg-bin "$(PG_BIN)")
