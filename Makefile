PY ?= .venv/bin/python

.PHONY: setup build test fetch screenshots all
setup:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
build:        ## regenerate both editions (PDF, workbook, deck) offline from saved snapshots
	$(PY) -m mpr build
test:
	$(PY) -m pytest -q
fetch:        ## re-download public snapshots (network); then run `make build test`
	$(PY) -m mpr fetch
screenshots:  ## re-render real screenshots of every output (needs LibreOffice: soffice)
	$(PY) tools/screenshots.py
all: build test screenshots
