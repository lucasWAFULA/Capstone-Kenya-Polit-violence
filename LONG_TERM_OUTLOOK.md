# Annual research outlook for 2026–2030

The Forecasts & trends page now defaults to a **2026–2030 annual count outlook**. This is a
third, separate research task: it projects the number of recorded high-severity political
violence events in each county and nationally. It does not stretch the existing seven-day
classifier into a five-year probability model or generate current review alerts.

## Data cutoff and annual target

The verified daily panel ends on **15 November 2025**. Only complete calendar years
**2000–2024** enter this annual experiment. Partial 2025 is excluded rather than annualized;
no events are invented for the missing months or for 2026. Each target counts recorded
political violence events with at least three fatalities and an eligible violent event type,
matching the daily panel's `high_political_violence_events` definition.

Observed outcome counts are historical targets. Future event fatalities are not predictors.
The model extrapolates annual history; it has no assumed future actor, economic, election
or policy inputs. All 47 counties retain explicit zero-record years. Those zeros describe
the source snapshot, not verified absence of violence.

The last fitted year is 2024, so 2025 is an unobserved bridge and the displayed 2026–2030
years are **leads 2–6**. The experiment therefore backtests six-year horizons, rather than
claiming a five-step test covers a six-step extrapolation.

## Candidate methods and evaluation

- **Recent five-year mean:** the preceding five complete annual counts averaged per county.
- **Damped log trend:** a linear slope over up to ten `log(1 + count)` observations, with
  level anchored to the latest three transformed observations. The absolute slope cap is
  0.1 and damping is 0.8. These settings were fixed before holdout evaluation.

Rolling origins **2009–2012** evaluate the subsequent six years, ending no later than 2018.
The pooled county-year validation MAE selects the method. The held-out test fits through
2018 and evaluates **2019–2024** (282 county-years and six national annual totals). This test
does not determine selection or tune the uncertainty band. The selected method is then
refitted on complete 2000–2024 history to produce the outlook.

| Validation result | County-year MAE |
| --- | ---: |
| Recent five-year mean | 1.2057 |
| Damped log trend (selected) | 1.0567 |

| Untouched 2019–2024 result | Value |
| --- | ---: |
| Pooled county MAE | 0.9696 events/year |
| Pooled county RMSE | 1.8795 |
| Recent-mean baseline county MAE | 0.8837 |
| Recent-mean baseline county RMSE | 1.7357 |
| National total MAE | 12.7750 events/year |
| National total RMSE | 13.1428 |
| County empirical-band coverage | 86.17% |
| National empirical-band coverage | 100% of six observations |

County metrics pool all counties and must not be interpreted as each selected county's
individual accuracy. National point estimates sum the county estimates, while national
error bands use aggregate forecast errors, not sums of county bounds.

The validation-selected trend performs **worse than the baseline on the held-out county
MAE and RMSE**. Selection is not retrospectively changed using this test. No improvement
over a simple baseline is claimed; this limits the case for using these projections in decisions.

## Error bands and interpretation

The display uses **empirical 80% validation-error bands**, not calibrated probabilistic
prediction intervals. Per-horizon county errors are scaled by `sqrt(expected + 1)` before
pooling; national widths use errors in aggregate totals. A cumulative maximum of widths
prevents their horizon factors from shrinking. Lower limits are clipped at zero.

The overlapping validation windows are dependent, the holdout is small, and all evaluation
uses a retrospective snapshot. Band coverage is descriptive, not a guaranteed future
coverage level. Structural shifts, changing reporting, under-reporting and missing
point-in-time record versions can invalidate the projections. These are expected counts,
so fractional estimates are valid; they are not verified incidents or probabilities.

The five-year view does not change the severity classifier or the existing seven-day
research model. Use the **Seven-day research replay** tab for those separately dated
probabilities. The alerts endpoint continues to suppress current signals for historical inputs.

## Reproduce and inspect

The committed annual input contains aggregate counts only and allows reproduction without
raw incident records or ACLED credentials:

```powershell
python scripts/build_long_term_outlook.py --annual-input artifacts/outlook/annual_history.json
python -m pytest tests/test_outlook.py -q
```

To regenerate from the verified private daily panel instead:

```powershell
python scripts/build_long_term_outlook.py --source-root 'PATH_TO_DATA_WORKSPACE'
```

The script checks the complete daily calendar before aggregating. It writes
`artifacts/outlook/annual_history.json` and `artifacts/outlook/outlook.json`. The latter
contains method settings, selection scores, held-out metrics, annual history, county/national
projections and a SHA-256 digest of the canonical annual input. `GET /v1/outlook` exposes
this aggregate artifact. The React view supports national/county selection and CSV export.

Methodological references: Hyndman and Athanasopoulos,
[multi-step rolling-origin evaluation](https://otexts.com/fpp3/tscv.html),
[forecast uncertainty](https://otexts.com/fpp3/prediction-intervals.html) and
[damped trends](https://otexts.com/fpp3/holt.html). The project implementation is a simple
count extrapolation, not a fitted ETS model or a validated causal account of political violence.
