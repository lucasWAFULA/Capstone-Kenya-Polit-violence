# K-PVIEWS final project report

**Kenya Political Violence & Event Severity Intelligence Platform**  
DSA8401 capstone project · Repository report · 21 November 2026  
Repository: https://github.com/lucasWAFULA/Capstone-Kenya-Polit-violence  
Demonstration: https://kenya-event-severity-clabrcsgmq-bq.a.run.app

## Problem framing

Political violence records require careful interpretation across place, time and event type.
A useful research system must make the evidence accessible while keeping recorded outcomes,
event classification and forecasts separate. K-PVIEWS addresses that need with a reproducible
data pipeline, two distinct modelling tasks, a FastAPI serving layer and a React analytical
workspace for Kenya's 47 counties.

The primary task classifies a described recorded event into severity bands. A separate research
experiment estimates whether a county will record at least one high-severity political violence
event over seven days. Neither output establishes what actually happened or replaces human
judgment. The application is an academic demonstration, not an operational public-safety system.

## Data and provenance

The data source is ACLED, accessed through authorized exports and authenticated API extraction.
The frozen severity-training manifest records **28,058 engineered rows**, with events through
**7 September 2025**. This training dataset must not be conflated with the later descriptive
API panel: its summary records **19,505 source incidents**, **495,004 county-day rows** and
**10,532 dates across 47 counties**, covering **15 January 1997 to 15 November 2025**.
The latter contains **479,108 zero-record county-days** and **282 right-censored target rows**.
These counts describe different data products; the later panel did not automatically retrain
either deployed model.

Extraction preserves raw response pages, page hashes, access restrictions and a versioned
manifest. Processing standardizes fields and checks identifiers, dates, county coverage and
count conservation before advancing latest-run pointers. The daily panel completes the calendar
so absence of a record is represented explicitly. It does not turn missing reports into proof
of no violence. Original publication/revision histories are not reconstructed from incident
dates or ACLED's last-upload timestamp.

Raw exports, credentials, private processed masters and SQLite state are excluded from Git.
The public application packages approved county totals and bounded 365-day national/county
series with source-run provenance. Authorized data access is needed to rerun extraction;
the committed artifacts are sufficient to run the demonstration without that access.

## Event severity methods and justification

Severity is defined as **Low: 0 fatalities; Moderate: 1–2; High: 3+**. Fatalities are used to
construct the target, never as a current-event request predictor. Inputs include event
attributes, administrative geography, actor/interaction codes, calendar variables and six
historical context values. Historical counts exclude the event date; the earlier high-severity
county count uses a 90-day window. Earlier outcomes must be available at the relevant cutoff.

The preprocessing pipeline imputes missing values and encodes categorical inputs consistently
between training and serving. Logistic Regression is the governed primary model; XGBoost is
the nonlinear challenger. Logistic Regression provides a comparatively simple baseline and
has stronger recorded macro F1 and High recall on the chronological test than the challenger.
XGBoost can capture nonlinear relationships, but higher aggregate accuracy or ROC AUC alone
does not justify promotion when High-severity recall is materially lower.

Training uses events before 2022, validation uses 2022–2023, and testing uses 2024 onward.
Chronological ordering reflects temporal deployment more closely than a random split.
The production script then refits both governed models on all input records and saves a
versioned registry with feature names, class order and SHA-256 checksums. The holdout scores
below belong to the earlier chronological experiment, **not an independent evaluation of
the final all-data refit**.

## Event severity results

Source: [artifacts/production/model_metrics.csv](artifacts/production/model_metrics.csv).

| Model | Test accuracy | Macro F1 | High recall | One-vs-rest ROC AUC |
| --- | ---: | ---: | ---: | ---: |
| Logistic Regression | 74.77% | 0.5745 | 37.50% | 0.8636 |
| XGBoost | 75.42% | 0.5443 | 17.13% | 0.8656 |

The challenger has slightly higher accuracy and ROC AUC, while the primary performs better
on balanced class performance and High recall. Even the primary misses many High cases;
its class probabilities support review rather than an automated decision. Every request
returns only the primary prediction while recording a structured shadow comparison for the
challenger. Promotion requires a separately governed evaluation rather than an AUC-only rule.

## County forecasting methods and results

This experiment uses **62,980 county-weeks**, retains zero-record observations and collapses
compatible repeated actor rows to incident IDs. The binary target is at least one political
violence event with three or more fatalities in a complete seven-day outcome window.
Features use dates before the origin minus an assumed reporting delay. Horizon and delay
purging reduce overlap across experimental boundaries; incomplete outcome windows are censored.

Rolling validation in 2019–2021 compares a prevalence baseline, Logistic Regression,
Random Forest and XGBoost using average precision. This metric is appropriate for the rare
positive outcome because it evaluates positive-class ranking rather than relying on accuracy.
Random Forest is selected. It fits before 2022, uses 2022 sigmoid calibration, and selects a
threshold on 2023 positive-class F1. The principal experiment assumes a seven-day reporting
delay and uses threshold **0.08**. The untouched 2024+ test contains **4,136 county-weeks**,
including **77 positives (1.86%)**. The research model is not refitted on all data for live use.

Source: [artifacts/forecasting/summary.json](artifacts/forecasting/summary.json).

| Held-out measure | Result |
| --- | ---: |
| Precision | 10.89% |
| Recall | 35.06% |
| Macro F1 | 0.5660 |
| Average precision | 0.0808 |
| Prevalence baseline average precision | 0.0186 |
| ROC AUC | 0.8259 |
| Brier score | 0.01766 |
| Baseline Brier score | 0.01829 |
| False positive rate | 5.44% |
| False discovery rate | 89.11% |

Ranking exceeds the prevalence baseline, but most issued flags are false positives and
most positive county-weeks are missed. The results do not establish an operational alert
policy. Sensitivity experiments with 0- and 14-day delays are recorded separately; see
[FORECASTING_RESULTS.md](FORECASTING_RESULTS.md). A fixed reporting-delay assumption cannot
recover original first-seen times, remove retrospective revision bias or prove real-time validity.

## Serving architecture and analytical interface

FastAPI validates individual and batch event requests, applies calendar transformations,
loads the checksummed registry and returns the primary class, probabilities, model version
and request ID. Extra fields, including fatalities, are rejected. The six historical context
values remain explicitly caller-supplied; server-side historical feature lookup is not yet
implemented and is not claimed as a completed serving capability.

The React + TypeScript workspace provides seven sections: executive overview, severity
prediction, forecasting and trends, geographic intelligence, alerts and review, data explorer,
and governance. It supports a local 47-county map, interactive county/window selection,
verified historical charts, individual and JSON batch predictions, CSV/JSON exports, mobile
navigation and light/dark themes. Unavailable data receive explicit states rather than
fabricated values. Reviewer notes and case assignment are not persisted in this version.

The Dockerfile builds React in a Node 24 stage and packages its assets with the Python service.
Cloud Build builds the image, pushes it to Artifact Registry and deploys Cloud Run in
`africa-south1`. Model files and aggregate snapshots are embedded in the image; the original
Cloud Storage model/snapshot-loading sketch is future work. GitHub Actions tests and builds
the project; automatic repository-triggered cloud release is not assumed.

The public academic demonstration uses the existing `kenya-event-severity` service in project
`k-pviews-2026`. Public access applies to both UI and API. ACLED ingestion requires separate
credentials, and current research forecasts require eligible fresh data. Historical replay
cannot generate current review alerts. The packaged replay spans 1–7 September 2025 and
must not be presented as current 2026 intelligence.

## Reproducibility and verification

[README.md](README.md) gives fresh-clone setup, data processing, training, Docker Compose,
cloud deployment and testing commands. Dependency files, the frontend lockfile, model manifest
and metric artifacts are committed. Exact experiment reproduction additionally requires the
original frozen data export; a later API response may have different coverage or revisions.

On 21 November 2026, the production React build completed, **44 backend tests passed**, and
browser checks passed against the deployed service. Checks exercised all seven sections,
47 county polygons, real individual/batch predictions, historical-alert suppression, daily
charts, mobile layout/navigation and dark mode, with no captured JavaScript exceptions.
Public website loading and model readiness were also verified after public access was enabled.
Software tests do not establish real-world model validity, operational readiness or course compliance.

## Limitations and next work

Data availability, under-reporting, uneven coverage, account restrictions and retrospective
revisions limit inference. Historical lags alone do not prove point-in-time eligibility.
The 1997–2025 descriptive panel and the model training export have different coverage and
granularity. The final severity refit has no separate independent holdout, High recall remains
limited, and rare-outcome county forecasting has a high false discovery rate.

Next work should implement versioned server-side historical lookup with availability cutoffs,
durable shared cloud storage for ingestion, stronger calibration and drift review, and prospective
evaluation. Public demonstration access has no application-level roles or rate limiting.
Any institutional use would need those controls, explicit human review and a validated decision
policy. No claim is made that the product is ready for operational security decisions.

## Sources and AI disclosure

Project evidence: [production manifest](artifacts/production/manifest.json),
[severity metrics](artifacts/production/model_metrics.csv),
[forecast summary](artifacts/forecasting/summary.json),
[daily summary](artifacts/data_quality/daily_summary.json),
[historical pipeline](HISTORICAL_INGESTION.md), [daily dataset](DAILY_DATASET.md),
[forecast results](FORECASTING_RESULTS.md) and the corresponding source code/tests.
Data-provider access and provenance are documented in the historical pipeline guide;
county geometry provenance is recorded in [BOUNDARIES.md](src/severity_service/static/BOUNDARIES.md).

AI assistance materially contributed to code and documentation, including this report;
see [AI_USE.md](AI_USE.md). The submitting student must review the report and disclosure
against the actual course rubric and AI policy. This report does not supply a signed student
attestation or certify policy compliance.
