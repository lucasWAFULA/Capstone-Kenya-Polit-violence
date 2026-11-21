# Seven-day county forecasting research

For the new **2026–2030 annual outlook**, see [LONG_TERM_OUTLOOK.md](LONG_TERM_OUTLOOK.md).
It has separate data aggregation, targets, multi-year evaluation and uncertainty bands.
The seven-day results below do not validate that long-term model and have not been relabelled
as future five-year probabilities. Both views are available in the React Forecasts section.

This extension forecasts a different target from the existing event severity classifier:
whether at least one political violence incident with three or more fatalities is recorded
in a county during the seven days beginning at a Monday forecast origin.

The historical export ends on 7 September 2025. These are retrospective research results,
not current forecasts or validated operational alerts. No live dashboard figures are fabricated.

## Data and experimental design

- 47 counties; 62,980 county-weeks from January 2000 through September 2025.
- Repeated actor rows collapse to one incident ID when forecasting fields agree.
- Complete daily calendars retain zero-record days and county-weeks.
- Predictors use incident dates strictly before the origin minus an assumed reporting delay.
- Only complete seven-day target windows enter evaluation.
- Rolling 2019, 2020, and 2021 validation compares a prevalence baseline, Logistic Regression,
  Random Forest, and XGBoost. Mean average precision selects the estimator.
- Final estimator fits before 2022; 2022 calibrates probabilities; 2023 tunes the alert
  threshold for positive-class F1. Target windows plus the delay are purged at boundaries.
- The untouched 2024+ test contains 4,136 county-weeks and 77 positive outcomes (1.86%).

## Primary experiment: assumed seven-day reporting delay

Rolling validation selected Random Forest. Its threshold, chosen on 2023 data, is 0.08.

| Held-out measure | Result |
| --- | ---: |
| Precision | 10.89% |
| Recall | 35.06% |
| Macro F1 | 0.5660 |
| Average precision | 0.0808 |
| Prevalence baseline average precision | 0.0186 |
| ROC-AUC | 0.8259 |
| Brier score | 0.01766 |
| Prevalence baseline Brier score | 0.01829 |
| False positive rate among negative county-weeks | 5.44% |
| False discovery rate among issued alerts | 89.11% |

The ranking exceeds the simple baseline, but most issued alerts are false positives and
most positive county-weeks are missed. These results do not support operational deployment.
The threshold is a research tuning choice, not a validated decision policy.

## Reporting-delay sensitivity

Each prespecified scenario repeats the same selection and tuning procedure. Consequently,
differences reflect both the assumed information delay and changes in the selected estimator.
The seven-day scenario remains the primary experiment; test results are not used to switch it.

| Assumed delay | Selected model | Precision | Recall | Average precision | Brier score |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 days | XGBoost | 10.27% | 58.44% | 0.1229 | 0.01732 |
| 7 days | Random Forest | 10.89% | 35.06% | 0.0808 | 0.01766 |
| 14 days | Logistic Regression | 12.27% | 44.16% | 0.1486 | 0.01699 |

Historical first-seen dates and record versions are unavailable. A fixed delay does not
remove reporting/revision bias, and zero records do not establish absence of violence.
County estimates can be unstable because positive outcomes are sparse; inspect positive
counts in `county_test_metrics.csv`. Temporal and geographical dependence also limits
inference from point estimates; no statistical superiority claim is made.

## Reproduce and inspect

Use `Forecasting.ipynb` or the new section 16 in local `Capstone2.ipynb`.
The standalone notebook has no original event-level outputs and is suitable for GitHub.
Supply your authorised local ACLED export; raw data are excluded from GitHub.

```powershell
python scripts/train_forecasting.py --coverage-end 2025-09-07
python scripts/train_forecasting.py --coverage-end 2025-09-07 --reporting-delay-days 0 --output artifacts/forecasting-delay0
python scripts/train_forecasting.py --coverage-end 2025-09-07 --reporting-delay-days 14 --output artifacts/forecasting-delay14
```

`artifacts/forecasting` contains the separate saved model, metadata, rolling evaluation,
county/year metrics, and test reliability bins. The large generated panel and per-origin
predictions stay local. The saved estimator is the pre-2022 research estimator with its
2022 calibrator; it is not refitted through 2025 and is not loaded by the severity API.

The next application phase now includes authenticated ingestion, first-seen/versioned
snapshots, freshness checks, a county map, and an in-app research review queue. It still
requires account configuration and prospective evaluation before operational use.
See `LIVE_OPERATIONS.md`. ACLED documents authenticated API access in its
[getting-started guide](https://acleddata.com/api-documentation/getting-started).
