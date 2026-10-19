PYTHON ?= python3
PORT ?= 8000
HISTORY_DIR ?= .history-local
FORECAST_DIR ?= .forecast-local

.PHONY: dev check-dev test demo

# Local convenience only: cached same-day sources cause no provider downloads.
# Missing/failed preparation never substitutes fixtures or prevents basic server startup.
dev:
	@if [ -f "$(FORECAST_DIR)/cities.json" ]; then \
		echo "Checking today's featured-city forecast (fetch missing data if needed)..."; \
		$(PYTHON) -m web.prefetch_forecasts --cities-file "$(FORECAST_DIR)/cities.json" --store-dir "$(FORECAST_DIR)" \
			|| echo "WARNING: featured-city forecast unavailable; server will start without complete featured advice."; \
	else \
		echo "WARNING: $(FORECAST_DIR)/cities.json missing; skipping featured forecast preparation."; \
	fi
	$(PYTHON) -m web.server --history-dir "$(HISTORY_DIR)" --forecast-dir "$(FORECAST_DIR)" --port "$(PORT)"

check-dev:
	$(PYTHON) -m web.check_dev --history-dir "$(HISTORY_DIR)" --forecast-dir "$(FORECAST_DIR)"

test:
	$(PYTHON) -m unittest discover -s tests/web -v

# Fixture advice/search/featured only; /api/city can still call GeoNames (see web/README.md).
demo:
	$(PYTHON) -m web.server --fixtures --port "$(PORT)"
