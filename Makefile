PYTHON ?= python3
PORT ?= 8000
HISTORY_DIR ?= .history-local
FORECAST_DIR ?= .forecast-local
DATA_DIR ?= weather-data

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

# Manual data maintenance; only data-update opts into provider IO.
.PHONY: data-update data-status data-export
data-update data-status data-export:
	$(PYTHON) -m web.data_commands $(patsubst data-%,%,$@) --forecast-dir "$(FORECAST_DIR)" --history-dir "$(HISTORY_DIR)" --bundle-dir "$(DATA_DIR)"

# Historical inventory is read-only; ARGS=--seed writes locally, ARGS=--download opts into LIVE IO.
# history-export is offline and history-only: copies valid local months missing from Git into weather-data/history.
.PHONY: history-status history-backfill history-export
history-status history-backfill history-export:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m web.history_commands $(patsubst history-%,%,$@) --history-dir "$(HISTORY_DIR)" --bundle-dir "$(DATA_DIR)" $(ARGS)

# Explicit forecast-only IO; OUTPUT must be a new independent directory.
.PHONY: forecast-update forecast-export
forecast-update forecast-export:
	$(PYTHON) -m web.data_commands $@ --bundle-dir "$(DATA_DIR)" --forecast-dir "$(FORECAST_DIR)" --output "$(OUTPUT)"

# Manual history data PR: new branch from origin/main, LIVE bounded ERA5 backfill, history-only export,
# push and `gh pr create`; never merges. ARGS=--no-download skips live IO; limits via ARGS (see web/README.md).
.PHONY: history-pr
history-pr:
	$(PYTHON) -m web.history_pr --history-dir "$(HISTORY_DIR)" --bundle-dir "$(DATA_DIR)" $(ARGS)
