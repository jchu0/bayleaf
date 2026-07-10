# deploy/telemetry — APM connectors over the `/metrics` seam

Vendor-neutral, **pull-based** telemetry connectors that wire an APM to PipeGuard's
already-shipped `GET /metrics` endpoint. Config + docs only — no PipeGuard code or
dependency changes. Full guide: [docs/ops/telemetry-connectors.md](../../docs/ops/telemetry-connectors.md).

| File | Connect… | Notes |
|---|---|---|
| `prometheus.yml` | Prometheus | `scrape_configs` job for the read-API target |
| `datadog-openmetrics.conf.yaml` | Datadog Agent | `conf.d/openmetrics.d/conf.yaml` OpenMetrics V2 check |
| `otel-collector-config.yaml` | OTLP APMs (New Relic / Honeycomb / Grafana Cloud) | Collector Prometheus receiver → OTLP exporter |
| `docker-compose.yml` + `grafana-datasource.yml` | Local demo | **Optional sizzle** — Prometheus + Grafana; not on the offline demo path |
| `grafana-dashboards.yml` + `grafana-dashboard.json` | Grafana | Auto-provisioned **"PipeGuard — QC decision gate"** board over the four `/metrics` series (runs, samples, cards-by-verdict, flagged-by-gate) |

The read-API serves `/metrics` on port 8010. The exposition carries only aggregate
counts and closed-enum verdict/gate labels — no sample ids, no PHI.
