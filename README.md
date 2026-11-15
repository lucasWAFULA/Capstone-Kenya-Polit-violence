# Kenya Political Violence Early-Warning Research System

Repository: https://github.com/lucasWAFULA/Capstone-Kenya-Polit-violence

The national dashboard at `/` displays a 47-county map, seven-day research probabilities,
forecast history, data freshness, and an in-app review queue. It starts with a clearly dated
historical replay from actual held-out predictions, with current alerts suppressed.
Authenticated ACLED ingestion can update research forecasts without retraining the model.

The separate `/event-assessment` page classifies a described event as Low, Moderate, or High.
The two pages use different models and targets. ACLED records reflect reported incidents;
results support human assessment and forecasting is not operationally validated.
See [LIVE_OPERATIONS.md](LIVE_OPERATIONS.md) for credentials, weekly ingestion, and local startup.
For the historical dataset milestone, use [HISTORICAL_INGESTION.md](HISTORICAL_INGESTION.md):
`python scripts/fetch_acled_data.py` preserves raw API snapshots and produces CSV/Parquet
master datasets and a quality report, without training or generating forecasts.
Then run `python scripts/build_county_daily.py` to create the complete 47-county daily
calendar, historical features, and censored seven-day labels. See [DAILY_DATASET.md](DAILY_DATASET.md).
The dashboard displays daily coverage, zero-record counts, quality checks, and activity charts.

The deployment package excludes raw ACLED data and notebook outputs. The original notebook
bundle is preserved in `artifacts/severity_model_bundle.joblib` for research reference.
The service uses the separately refitted registry in `artifacts/production`.
Reported holdout metrics describe the chronological experiment, not an independent evaluation
of the final all-data refit. Historical features on the event-assessment page are entered manually.

This project serves the notebook's governed model decision:

- **Primary:** Logistic Regression; its result is returned to callers.
- **Challenger:** XGBoost; it scores every request in shadow mode and is never used to alter the response.
- **Target:** `Low` (0 fatalities), `Moderate` (1–2), or `High` (3+).

The training command repeats the chronological evaluation (`<2022` train, 2022–2023 validation,
2024+ test), records both candidates' metrics, then refits both models on all data available through
2025 for deployment. Artifacts have a versioned manifest and SHA-256 checksums.

## Build the model registry

From this directory, with a Python 3.13 environment:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "$PWD/src"
python scripts/train_production_models.py --version 1.0.0
```

This writes `artifacts/production/manifest.json`, both model files, and `model_metrics.csv`.
The service refuses to start when the feature contract, class order, or artifact checksum differs.

## Run locally

Use Python 3.13 (the model's pinned XGBoost version requires Python 3.12 or newer).
Create and activate an environment before installing the requirements:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

```powershell
$env:PYTHONPATH = "$PWD/src"
uvicorn severity_service.app:app --host 127.0.0.1 --port 8000
```

OpenAPI documentation is at `http://localhost:8000/docs`. Health probes are
`/health/live` and `/health/ready`.
Open `http://localhost:8000/` for the national overview, or `/event-assessment` for the event form. `/health` and `/predict` are
aliases for `/health/ready` and `/v1/predict`. Responses use `severity` and `probabilities`.

Example request:

```json
POST /v1/predict
{
  "event_date": "2026-09-20",
  "disorder_type": "Political violence",
  "event_type": "Battles",
  "sub_event_type": "Armed clash",
  "admin1": "Nairobi",
  "admin2": "Nairobi",
  "inter1": 1,
  "interaction": 12,
  "civilian_targeting": null,
  "county_events_previous_30_days": 8,
  "county_events_previous_90_days": 20,
  "violent_events_previous_30_days": 4,
  "previous_high_severity_events_in_county": 1,
  "days_since_previous_event_in_county": 2,
  "actor_previous_event_count": 15
}
```

History values are required because they must come from events strictly before `event_date`. The
calling feature pipeline should compute them from the production event store. Defaulting an unknown
history to zero would create training/serving skew, so the API deliberately rejects omitted values.
`previous_high_severity_events_in_county` uses the previous 90 days.
Actor codes are integers; missing civilian targeting is JSON `null`.

## Container

Build only after generating the artifacts:

```powershell
docker build -t kenya-severity-api:1.0.0 .
docker run --rm -p 8080:8080 kenya-severity-api:1.0.0
```

## Deploy to Google Cloud Run

The checked-in GCP configuration uses Cloud Run, Cloud Build, and Artifact Registry in
`africa-south1` (Johannesburg). The service is private by default and runs under a dedicated
runtime service account with no project roles.

Prerequisites:

1. Select or create a billing-enabled GCP project.
2. Install the Google Cloud CLI and run `gcloud auth login`.
3. Make sure your account can enable APIs, create service accounts and repositories, and change IAM.

Bootstrap the project once:

```powershell
.\deploy\gcp\bootstrap.ps1 -ProjectId 'your-gcp-project-id'
```

Build, publish, and deploy:

```powershell
.\deploy\gcp\deploy.ps1 -ProjectId 'your-gcp-project-id'
```

The deployment uses an immutable Cloud Build ID image tag, checks model artifacts during startup,
allocates 1 CPU/1 GiB, permits up to 20 concurrent requests per instance, and scales from zero to
five instances. Startup and liveness probes call the model-aware health endpoints.

For a private service, grant `roles/run.invoker` only to the user, group, or service account that
will call the API. You can test through a local authenticated proxy:

```powershell
gcloud run services proxy kenya-event-severity --project='your-gcp-project-id' --region='africa-south1'
```

Public access is available only as an explicit option:

```powershell
.\deploy\gcp\deploy.ps1 -ProjectId 'your-gcp-project-id' -AllowUnauthenticated
```

Do not use that option for sensitive production traffic until application-level authentication,
rate limiting, and abuse controls are in place. After deployment, use
`deploy/gcp/smoke-test.ps1` against the service URL (or the local proxy URL).

Cloud Run writes the API's structured shadow-comparison records to Cloud Logging. Create log-based
metrics or export these records to BigQuery before using them for challenger promotion decisions.

## Monitoring and promotion

Every request emits a JSON `shadow_prediction` log containing model agreement and both models'
High-severity probability. Join labels later by `request_id` and report, by calendar month:

- primary/challenger macro F1 and High recall;
- prediction mix and model agreement rate;
- probability calibration by class;
- missing/unknown category rates and feature-distribution drift;
- p50/p95 latency and 4xx/5xx rates.

Do not promote the challenger from AUC alone. Require a pre-declared evaluation window, no material
drop in High recall, a statistically credible macro-F1 improvement, calibration review, and a new
approved artifact version. Rollback consists of redeploying the prior immutable artifact directory.

## Test

```powershell
$env:PYTHONPATH = "$PWD/src"
pytest -q
```

GitHub Actions tests the API against direct inference from the real registry and builds the
Docker image. Automatic cloud deployment is deferred until a manual Cloud Run deployment
is verified, following the guide.

Setup reference: [Google's FastAPI quickstart](https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-fastapi-service).

## County-level seven-day forecasting research

`Capstone2.ipynb` now includes section 16 for a separate early-warning experiment.
It preserves the event severity classifier. Its separate bundle supplies the national dashboard.
The target is at least one high-severity political violence event in each county's
next seven days. All 47 counties have weekly Monday observations, including zero-record
weeks. Features use complete calendar-day windows strictly before the assumed reporting cutoff.
Repeated actor rows are collapsed to one event ID when forecasting fields agree; conflicting
event IDs are rejected. This prevents actor-level duplication from inflating incident counts.

Run independently of the notebook:

```powershell
python scripts/train_forecasting.py --coverage-end 2025-09-07
```

Use the actual final fully observed date of your export. The default seven-day reporting
delay is an assumption. `timestamp` is not treated as first-seen history. Without historic
record versions and availability dates this is a retrospective experiment, not a proven
real-time backtest. Repeat with `--reporting-delay-days 0` and `14` into separate `--output`
folders to assess sensitivity. No-record rows do not prove that no violence occurred.

Model selection compares a prevalence baseline, Logistic Regression, Random Forest, and
XGBoost on rolling 2019–2021 validation. The selected model fits before 2022, calibrates
on 2022, tunes its threshold on 2023, and is tested on 2024 onward. Label windows plus
the reporting delay are purged at boundaries. The all-data refit is deliberately deferred.
Exports under `artifacts/forecasting` contain the separate model bundle, summary, rolling
metrics, county/year test metrics, reliability bins, and local-only panel/predictions.

Current-data ingestion, the county map, and in-app research alerts are implemented. API access
requires an authenticated account; ingestion retains first-seen timestamps and record versions.
Historical 2025 records are explicitly labelled and cannot generate current alerts.
