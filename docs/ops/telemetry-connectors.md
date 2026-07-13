# Telemetry connectors over `GET /metrics`

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-10 (MST) |
| **Audience** | software / ops |
| **Related** | [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md) (read API), [requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) (wishlist #17), [planning/tasks.md](../planning/tasks.md) (T-036/T-027/T-079), config bundle: [`deploy/telemetry/`](../../deploy/telemetry/) |

## Overview

How to point an APM (Datadog, Prometheus, or any OTLP backend) at bayleaf's
shipped `GET /metrics` endpoint. This is **config + docs only** — no bayleaf
code and no new dependency. Everything here rides the pull model: your collector
scrapes `/metrics`; bayleaf never dials out and never ships a credential.

## The pull model (why this is scrape-safe)

1. **Fact.** `/metrics` is a read-only Prometheus text-exposition endpoint served
   by the read-API (`api/main.py`, `GET /metrics`, `text/plain; version=0.0.4`),
   aggregated over the served runs. The default host:port is `http://<host>:8010/metrics`
   (`uv run uvicorn api.main:app --port 8010`).
2. **Fact.** Collectors GET that endpoint on their own schedule. bayleaf makes
   no outbound network call and holds no APM credentials — the credentials live in
   the collector/agent config, never in bayleaf.
3. **Decision.** We connect APMs by scraping, not by embedding a vendor SDK, so the
   app core and its dependency set are untouched (CLAUDE.md dependency guardrail 1).

## Exposed series — the whole surface

The endpoint emits exactly four series (`_render_prometheus` in `api/main.py`):

| Series | Type | Labels | Meaning |
|---|---|---|---|
| `bayleaf_runs_total` | counter | — | Analysis runs discoverable by the API |
| `bayleaf_samples_total` | counter | — | Decision cards (samples) across served runs |
| `bayleaf_cards_total` | counter | `verdict` ∈ {`proceed`,`hold`,`rerun`,`escalate`} | Decision cards by final verdict |
| `bayleaf_gate_flagged_samples_total` | counter | `gate` ∈ {`preflight`,`qc`,`variant`} | Samples with a non-proceed verdict at each gate |

## No PHI leaves the app — verified

**Fact (verified 2026-07-08 against `_render_prometheus`, `api/main.py`).** Every
line the endpoint emits is either an aggregate integer count (`runs`, `samples`)
or a count carrying a single label whose value comes from a **closed enum**:
`verdict` (`_VERDICT_ORDER`) or `gate` (`_GATE_ORDER`). There are **no** sample
ids, run ids, file paths, subject/patient identifiers, metric values, or free-text
fields in the exposition. Scraping `/metrics` therefore cannot exfiltrate sample-
or subject-level data — that is the point of choosing a pull model. If a future
change adds a series, re-verify this claim before shipping (Doc-update map: an
`api/` capability change owes this doc).

> Guardrail: bayleaf is a research/demo tool, not a clinical system. These are
> aggregate operational counts, not calibrated or clinical metrics.

## Connect Datadog

Use the Datadog Agent's OpenMetrics V2 check — no bayleaf change.

1. Copy [`deploy/telemetry/datadog-openmetrics.conf.yaml`](../../deploy/telemetry/datadog-openmetrics.conf.yaml)
   to `conf.d/openmetrics.d/conf.yaml` in the Agent config dir (or merge its
   `instances:` entry into an existing file).
2. Set `openmetrics_endpoint` to your API URL (`http://host.docker.internal:8010/metrics`
   for a containerized Agent on Docker Desktop; the API host:port otherwise).
3. Restart the Agent. Series arrive namespaced `bayleaf.*`; under OpenMetrics V2
   a `_total` counter lands as `bayleaf.<name>.count`
   (e.g. `bayleaf.cards.count`, keeping the `verdict`/`gate` tag dimensions).

## Connect Prometheus

1. Merge the job from [`deploy/telemetry/prometheus.yml`](../../deploy/telemetry/prometheus.yml)
   into your Prometheus config's `scrape_configs`.
2. Pick the target: `localhost:8010` for a natively-run Prometheus on the API host,
   or `host.docker.internal:8010` for a containerized Prometheus (the shipped file
   defaults to the container form and comments the native one).
3. Reload Prometheus; confirm the `bayleaf` target is **UP** on the Targets page.

## Connect OTLP-based APMs (New Relic / Honeycomb / Grafana Cloud)

For backends that ingest OTLP, run an OpenTelemetry Collector as the bridge — it
scrapes `/metrics` and forwards over OTLP, so still no in-app exporter.

1. Use [`deploy/telemetry/otel-collector-config.yaml`](../../deploy/telemetry/otel-collector-config.yaml)
   (Prometheus receiver → `batch` → OTLP exporter).
2. Provide the backend endpoint and key via env — `OTLP_ENDPOINT` and
   `OTLP_API_KEY` — never hardcoded (CLAUDE.md Security 1).
3. Run e.g. `otelcol-contrib --config deploy/telemetry/otel-collector-config.yaml`.
   The `debug` exporter prints scraped series to the Collector log for a local check.

## Optional local demo (docker-compose)

For a live "connect your APM" moment, [`deploy/telemetry/docker-compose.yml`](../../deploy/telemetry/docker-compose.yml)
stands up Prometheus + Grafana that scrape the locally-running API:

```bash
uv run uvicorn api.main:app --port 8010          # API with /metrics
docker compose -f deploy/telemetry/docker-compose.yml up
# Prometheus → http://localhost:9090   Grafana → http://localhost:3000
```

**Fact (added 2026-07-10, T-079).** Grafana no longer boots empty: a provisioned
**"bayleaf — QC decision gate"** dashboard ([`deploy/telemetry/grafana-dashboard.json`](../../deploy/telemetry/grafana-dashboard.json)
+ [`grafana-dashboards.yml`](../../deploy/telemetry/grafana-dashboards.yml) provider) renders
the same four series above (runs/samples stat tiles, cards-by-verdict donut + trend, flagged-by-gate
bar) — no new series, config only. A stable `bayleaf-prometheus` datasource `uid`
([`grafana-datasource.yml`](../../deploy/telemetry/grafana-datasource.yml)) lets it bind
deterministically.

**Decision — demo sizzle only.** This stack is *not* on the offline API/UI
demo path and is not required to run or demo bayleaf; the anonymous-admin Grafana
and default password are for a throwaway localhost demo, not for exposure.

## Deferred (own task, out of this slice)

**TODO / scope note.** An **in-app push exporter** (Datadog `ddtrace`/DogStatsD, or
`opentelemetry-*` + OTLP) behind a `BAYLEAF_*_LIVE` opt-in, following the
`notify/` adapter pattern, is deliberately **out of scope** here. That path is
where a heavy runtime dependency, outbound network surface, and vendor credentials
would enter — so it stays a separate, opt-in-gated follow-up. This connector slice
keeps everything pull-based and dependency-free.

---

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
