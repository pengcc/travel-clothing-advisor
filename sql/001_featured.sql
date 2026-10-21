-- Apply only to an explicitly authorized dedicated database. Never run at import.
-- The owner provisions separate worker and SELECT-only reader roles afterwards.
CREATE TABLE runtime_control (
 id boolean PRIMARY KEY DEFAULT true CHECK(id),
 enabled boolean NOT NULL DEFAULT false,
 epoch bigint NOT NULL CHECK(epoch>0),
 code_version text NOT NULL, config_digest text NOT NULL,
 provider_group text NOT NULL,
 aggregate_day_limit integer NOT NULL CHECK(aggregate_day_limit BETWEEN 1 AND 42),
 aggregate_month_limit integer NOT NULL CHECK(aggregate_month_limit>0),
 aggregate_minute_limit integer NOT NULL CHECK(aggregate_minute_limit>0),
 heartbeat timestamptz,
 ordinary_enabled boolean NOT NULL DEFAULT false CHECK(NOT ordinary_enabled),
 history_enabled boolean NOT NULL DEFAULT false CHECK(NOT history_enabled)
);
CREATE TABLE budget_usage (
 provider_group text NOT NULL, period text NOT NULL, used integer NOT NULL CHECK(used>=0),
 PRIMARY KEY(provider_group,period)
);
CREATE TABLE jobs (
 domain text NOT NULL, day date NOT NULL, city_id text NOT NULL,
 generation bigint NOT NULL DEFAULT 0, epoch bigint NOT NULL,
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
 lease_until timestamptz, retry_at timestamptz,
 version text, PRIMARY KEY(domain,day,city_id)
);
CREATE TABLE attempts (
 domain text NOT NULL, day date NOT NULL, city_id text NOT NULL,
 generation bigint NOT NULL, provider_group text NOT NULL, charged_at timestamptz NOT NULL,
 PRIMARY KEY(domain,day,city_id,generation)
);
CREATE TABLE publications (
 domain text NOT NULL, day date NOT NULL, epoch bigint NOT NULL,
 version text NOT NULL, committed_at timestamptz NOT NULL,
 PRIMARY KEY(domain,day)
);
-- No activation record is seeded. Missing control/ledger fails closed.
-- GRANT SELECT on runtime_control,publications to the dedicated site role only.
-- Worker needs SELECT/INSERT/UPDATE/DELETE on these five tables, no DDL or role rights.
