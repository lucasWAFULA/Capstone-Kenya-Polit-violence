# Recent reporting: access, ingestion, and dashboard evidence

The application now separates three different facts:

1. **API connected:** authentication and an event query succeeded.
2. **Recent reporting accessible:** unrestricted Kenya queries return actual event records
   in the requested last-14-day interval.
3. **Recent reporting ingested:** a successful recent sync produced the exact dataset
   backing the map. The access check and sync must be at most 24 hours old.

None of these establishes complete incident reporting or validates a forecasting model.
ACLED publishes event data weekly; this is not an instantaneous incident stream.

## Current verified limitation

The API check on 15 November 2026 authenticated successfully, but the account reported a
12-month recency delay, access through 15 November 2025, and zero available Kenya records
for 2–15 November 2026. Polling more frequently cannot remove this restriction.
Request access to **current Kenya event-level data** through your myACLED account or
ACLED account administrator. Do not change the historical dataset's dates or claim it is live.

Official references: [myACLED access FAQ](https://acleddata.com/myacled-faqs),
[data types and delayed Research access](https://acleddata.com/faq-codebook-tools),
[ACLED event-data publication](https://acleddata.com/faq/what-are-acled-data).

## Check access

```powershell
.\.venv313\Scripts\python.exe scripts/check_reporting_access.py
```

The check requests access metadata and a one-record query for the last 14 days. It never
prints OAuth credentials/tokens. A blocked/unconfirmed check exits nonzero and records
its status locally in ignored `runtime/reporting_status.json`.

The React Data explorer displays reporting-access status and available provenance; the
context banner distinguishes historical activity from recent ingestion. Detailed connectivity,
last-check, recent-record and sync evidence remains available in the reporting endpoint.
`GET /v1/reporting/status` serves this non-sensitive evidence. Browser refreshes read the
saved result; they do not repeatedly authenticate against ACLED.

## After current-data access is enabled

Run a reporting-only update:

```powershell
.\.venv313\Scripts\python.exe scripts/update_reporting.py
```

The updater verifies recent access, extracts all available Kenya history with cursor
pagination, preserves raw snapshots, validates the master, rebuilds the daily county
dataset, and refreshes the map aggregates. It rejects restricted or unexpectedly old
extractions before publishing a new daily panel. It does **not** train or run forecast models.

For automatic daily checks and refreshes, keep this separate process running:

```powershell
.\.venv313\Scripts\python.exe scripts/reporting_worker.py --interval-hours 24
```

The dashboard refreshes its saved status/map every 60 seconds. A “Recently ingested
reporting” label requires verified current access, a successful sync within 24 hours,
a matching dataset ID, and ingested incident dates within the last 14 days. A recent login,
an old export downloaded today, or a mismatched snapshot cannot earn that label.
The latest incident date remains distinct from release freshness or reporting completeness.

## Docker option

```powershell
docker compose --profile reporting up --build -d
```

The reporting worker uses `Dockerfile.reporting` and the configured local `.env`.
It shares persistent data/runtime volumes with the dashboard. This profile does not start
the separate forecasting worker. Keep credentials in `.env`, which is excluded from Git
and Docker build contexts. Cloud resources are not deployed by this change.

## Forecasting remains separate

`scripts/update_forecasts.py` still applies its stricter model/source freshness checks.
The real API response currently omits optional `last_update`, so the reporting path does
not depend on that optional field or invent a source-publication time from an incident date.
Enabling reporting access does not by itself enable validated early-warning alerts.
