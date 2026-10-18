PYTHON ?= python3
PORT ?= 8000
HISTORY_DIR ?= .history-local
FORECAST_DIR ?= .forecast-local

.PHONY: dev check-dev test demo

dev: check-dev
	$(PYTHON) -m web.server --history-dir "$(HISTORY_DIR)" --forecast-dir "$(FORECAST_DIR)" --port "$(PORT)"

check-dev:
	$(PYTHON) -m web.check_dev --history-dir "$(HISTORY_DIR)" --forecast-dir "$(FORECAST_DIR)"

test:
	$(PYTHON) -m unittest discover -s tests/web -v

# Fixture advice/search/featured only; /api/city can still call GeoNames (see web/README.md).
demo:
	$(PYTHON) -m web.server --fixtures --port "$(PORT)"
