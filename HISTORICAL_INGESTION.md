# Kenya historical API extraction

Official endpoints verified against ACLED documentation:

- OAuth: `https://acleddata.com/oauth/token`
- Events: `https://acleddata.com/api/acled/read`

Sources: [authentication](https://acleddata.com/api-documentation/getting-started),
[cursor pagination](https://acleddata.com/api-documentation/elements-acleds-api),
[event fields and access metadata](https://acleddata.com/api-documentation/acled-endpoint).

## Run

Keep your credentials in the ignored local `.env`. Install the historical-ingestion
dependencies in the same Python environment used by the application:

```powershell
python -m pip install -r requirements-ingestion.txt
python scripts/check_acled_api.py
python scripts/fetch_acled_data.py
python scripts/inspect_acled_data.py
```

In this workspace the existing interpreter is `.\.venv313\Scripts\python.exe`.
The provided checker prints connection metadata and field names, never OAuth tokens.
Your original `test_acled.py` is left untouched and excluded from upload.

## Stored files

Each extraction receives a unique run ID; older raw snapshots remain intact:

```text
data/
  latest.json
  raw/<run-id>/
    page-0001.json ...
    manifest.json
    kenya_acled_raw.csv
    kenya_acled_raw.parquet
  processed/<run-id>/
    kenya_acled_master.csv
    kenya_acled_master.parquet
    quality_report.json
```

The raw page files retain the original response fields and access metadata before cleaning.
The manifest records page SHA-256 hashes. CSV and Parquet preserve all returned event columns;
the separate processed master standardises dates, county aliases, missing strings, fatalities,
and the original Low/Moderate/High severity definition. Numeric actor codes are requested with
`inter_num=1` for consistency with the research export.

The importer uses dyadic events, follows every cursor, checks a consistent `total_count`,
rejects duplicate/conflicting event IDs, and detects stalled cursors. A partial or invalid
run preserves its raw pages for review but cannot replace `latest.json`. That pointer is
updated atomically only after raw/master files and the quality report are complete.

The report includes record counts, dates, shape, missingness, county coverage, event types,
severity counts, and event-ID/core-field differences from the original notebook dataset.
`timestamp` is ACLED's last-upload field, not historical first publication. The master also
records when this installation observed the snapshot; it does not invent historic availability.

## Historical extraction versus current forecasting

The archival importer downloads **all records available to the configured account**, records
any access restrictions, and does not train models or generate forecasts. This is separate
from `scripts/update_forecasts.py`, which applies the stricter freshness/access requirements
for current research forecasts. A successful historical extraction does not enable live alerts.

The connection verified on 15 November 2026 reported a 12-month recency restriction and a
15 November 2025 access cutoff. Recent records are therefore unavailable to this account.
The API response also omitted `last_update`; archival extraction does not require that optional
field or infer release freshness from the newest incident date. Current forecasts remain
blocked unless their access and freshness requirements can actually be established.

Raw data, processed masters, credentials, and account-specific quality reports are excluded
from GitHub and Docker/Cloud Build contexts. Only code and documentation are uploaded.
Repeated full extraction is intentional for this first milestone; incremental updates and
deleted-event reconciliation are subsequent work.
