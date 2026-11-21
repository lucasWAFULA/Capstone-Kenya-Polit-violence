# Local dashboard and live-data setup

## Open the updated dashboard

The published React demonstration is public at
https://kenya-event-severity-clabrcsgmq-bq.a.run.app. Provider credentials are required only
for ACLED ingestion, not for opening this website. Public hosting does not establish fresh
source coverage. See README.md for the current interface, architecture and fresh-clone setup.

Build React once before starting a production-style local preview:

```powershell
npm ci --prefix frontend
npm run build --prefix frontend
```

Stop your old server with Ctrl+C, then run from the project directory:

```powershell
.\scripts\run_local.ps1
```

Open http://127.0.0.1:8000. If Windows blocks that port, use
`.\scripts\run_local.ps1 -Port 8765` and open the matching address.
The helper selects the existing `.venv313` or `.venv` and loads `.env` if present.

The React sidebar separates Overview, Severity prediction, Forecasts & trends, Geographic
intelligence, Alerts & review, Data explorer and Model governance. `/event-assessment`
opens the event classifier. `/docs` describes forecast and severity APIs. The Overview starts
with 90 observed days. County/window selections link supported charts and tables; the
Geographic intelligence page provides alternate count layers. Forecasts & trends displays
the separately dated research estimates. Data explorer shows coverage and quality metadata,
county search, daily activity and exportable aggregate tables. Build the daily panel
after extraction with `python scripts/build_county_daily.py`; see `DAILY_DATASET.md`.
Its dataset coverage is separate from the older forecast replay's input coverage.

With no fresh ingested forecasts, the dashboard shows **Historical replay, 1–7 September
2025**. These are saved, actual held-out model estimates, not current 2026 forecasts.
Current alerts are suppressed. The historical export's end date is not its download time.

## Connect ACLED locally

For recent reported activity without running the research forecast model, follow
`REPORTING_READINESS.md` and use `scripts/update_reporting.py`. The dashboard now
shows API connectivity, access delay, last check, and last successful reporting sync.

Create `.env` using `.env.example` as a template, then enter your own myACLED username
and password in your editor, or supply an unexpired OAuth access token. Do not commit
the file or paste passwords into chat. The project ignores it. Environment variables
already set in the terminal take precedence over `.env` values.

```text
ACLED_USERNAME=your-account-email
ACLED_PASSWORD=your-account-password
```

The account needs API access to the full Kenya event history and recent releases.
The client uses the official OAuth endpoint and cursor pagination for dyadic events.
It rejects reported query restrictions, missing pagination totals/cursors, total-count
changes, incomplete responses, unmapped counties, and source update age over eight days.
Credentials and response bodies are never printed by the HTTP client.

Run one update:

```powershell
.\.venv313\Scripts\python.exe scripts/update_forecasts.py
```

The query includes events through yesterday in Africa/Nairobi. `coverage_end` means the
requested query cutoff, not proof that every incident through that day has been reported.
The model still applies its seven-day reporting-delay assumption. You can explicitly
set a known query cutoff with `--coverage-end YYYY-MM-DD`; stale coverage cannot be
silently extended with zero-event days to make a current forecast.

A successful run saves a versioned snapshot and generates a seven-day forecast beginning
tomorrow at midnight in Nairobi. Use **Refresh data** in React to request the new state.
No model retraining occurs. Cloud ingestion needs persistent shared storage and scheduling;
running a local updater does not change an already-deployed image's packaged data.

## Run weekly updates

For a local demonstration, keep this worker running in a second terminal:

```powershell
.\.venv313\Scripts\python.exe scripts/ingestion_worker.py
```

It runs immediately and every 168 hours thereafter. Stop it with Ctrl+C.
Each run downloads a complete snapshot so changed and removed records are reflected.
It uses the account's access restrictions rather than assuming unrestricted coverage.
OAuth password-based authentication renews access for each run; manually supplied access
tokens must be refreshed before expiry. Select an interval aligned to your ACLED release
schedule; a failed run leaves previous results visible but suppresses current alerts.

## Storage and alerts

`runtime/events.sqlite3` stores snapshots, projected event versions, first-seen times,
job outcomes, and forecasts. It is excluded from Git and container builds. First-seen times
mean first observed by this installation, not original ACLED publication dates. Versions
store fields needed for forecasting; no event notes are exposed by the dashboard API.
The map geometry is served locally and does not need a third-party map token or CDN.

Alerts are **in-app research review signals**, not public warnings, email, or SMS. The
primary threshold is 8%, selected using 2023 F1. The map's 20%-wide probability colour
bands are presentation bands and are separate from that threshold. Current signals are
suppressed if the forecast expires, source/snapshot age exceeds eight days, or a newer
update job fails. Review signals can be displayed for tomorrow's scheduled forecast.

The model is the existing pre-2022 Random Forest with a 2022 calibrator. It achieved about
11% precision and 35% recall in the held-out experiment; about 89% of its alerts were
false discoveries. New input data do not establish prospective validity or fix those limits.

## Docker

```powershell
docker compose up --build dashboard
```

With a configured `.env`, start the weekly worker as well:

```powershell
docker compose --profile live up --build -d
```

Both containers share a persistent named volume for SQLite. This is a single-host setup.
The earlier Cloud Run scripts still serve the historical dashboard, but do not provide
durable shared live storage or schedule this worker. A cloud rollout needs a supplied GCP
project and shared durable storage/job infrastructure; this change does not deploy cloud resources.

## Verification

Tests cover OAuth/cursor paging, partial and restricted data rejection, version retention,
first-seen preservation, research/serving feature parity, real-model inference, freshness,
expiry, failed-update suppression, and the dashboard API/map. Live ACLED connectivity must
be verified with your own authorised account; mocked API tests cannot establish entitlement.

References: [ACLED authentication](https://acleddata.com/api-documentation/getting-started),
[current pagination](https://acleddata.com/api-documentation/elements-acleds-api),
[geoBoundaries metadata](https://www.geoboundaries.org/api/current/gbOpen/KEN/ADM1/).
