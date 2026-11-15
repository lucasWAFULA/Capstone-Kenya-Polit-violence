# Complete daily county dataset

The API master has been expanded into one row per Kenyan county per calendar day.
The current build contains **495,004 rows × 23 columns**: **10,532 dates × 47 counties**,
from **15 January 1997 through 15 November 2025**. It retains all **19,505 source incidents**
and includes **479,108 zero-record county-days**. No model was fitted or forecast refreshed.

## Rebuild and inspect

After a successful historical extraction, run:

```powershell
.\.venv313\Scripts\python.exe scripts/build_county_daily.py
```

Each build saves CSV, Parquet, a quality report, and bounded aggregate dashboard series in
`data/daily/<build-id>/`. `data/daily/latest.json` points to the last completed build.
Previous builds remain intact. The source extraction ID links the panel to its verified master.
The dashboard detects when a newer extraction exists and a panel rebuild is needed.

To open the latest panel in a notebook:

```python
import json
from pathlib import Path
import pandas as pd

pointer = json.loads(Path("data/daily/latest.json").read_text())
daily = pd.read_parquet(Path(pointer["directory"]) / "county_daily.parquet")
display(daily.head())
assert daily.groupby("date")["county"].nunique().eq(47).all()
assert not daily.duplicated(["county", "date"]).any()
```

## Field meanings

| Fields | Interpretation |
| --- | --- |
| `date`, `county` | Unique observation key, using the model's consistent 47 county names |
| `events`, `fatalities` | All recorded incidents and total fatalities on that date |
| `context_events` | Recorded incidents excluding Strategic developments |
| `violent_events` | Battles, Violence against civilians, or Explosions/Remote violence |
| `high_severity_events` | Recorded incidents with 3+ fatalities, across all event types |
| `high_political_violence_events` | Violent-type incidents with 3+ fatalities whose disorder type contains Political violence |
| `is_zero_record_day` | No recorded incident for this county/date in the source snapshot |
| `events_previous_7_days`, `events_previous_30_days`, `events_previous_90_days` | Strictly prior calendar-day context counts; observation day excluded |
| `high_political_previous_30_days`, `violent_previous_90_days` | Strictly prior historical outcome/activity counts |
| `history_90d_complete` | At least 90 earlier calendar days fall inside the panel coverage |
| `no_previous_context_event`, `days_since_previous_context_event` | No earlier context incident observed in this snapshot, or days since the latest one |
| `high_political_events_next_7_days`, `target_high_next_7_days` | Event count and binary outcome over `[date, date + 7 days)` |
| `target_window_complete` | Entire seven-day outcome window is inside observed date bounds |
| `month`, `quarter`, `day_of_week` | Known calendar fields; weekdays are Monday=0 through Sunday=6 |

The first 7/30/90-day historical windows remain null until fully observed. The first
90 calendar days account for **4,230 county-days** with incomplete 90-day history.
An unknown previous-event date also remains null; it is not replaced by zero days.

The final six dates have incomplete forward windows. Their **282 county-day labels**
remain null, leaving **494,722 rows with complete labels**. Missing future labels are
never converted into negative outcomes.

Only lagged columns and known calendar fields are predictor candidates. Same-day event,
fatality, and high-event counts are descriptive/target-building fields, not predictors for
a forecast issued at that day's start. Historical first-seen/revision times are unavailable,
so strictly lagged incident dates alone do not establish a leakage-free real-time backtest.
Daily seven-day outcomes overlap: future training must use chronological splits with a
purged horizon and reporting delay, or select non-overlapping weekly origins.

## Validation and dashboard

Checks verify unique county/date keys, 47 counties on every date, incident/fatality
conservation, and all-zero counts on zero-record days. Boundary tests verify historical
lags, future perturbation isolation, and the right-censored labels.

The dashboard's **Daily data foundation** panel shows build dimensions, coverage, zero-day
share, source counts, label completeness, national/county daily charts, and recent rows.
The area selector includes National plus all 47 counties; windows cover 30, 90, or 365 days.
`GET /v1/data/summary` serves build metadata; `GET /v1/data/daily?county=Bomet&days=30`
serves bounded aggregate daily counts. Event notes and local paths are never exposed.

The CSV, Parquet, and daily series stay local and are excluded from GitHub/container builds.
Only aggregate build metadata is packaged. A deployment without the local daily series
shows its build summary and clearly states that activity files are unavailable there.

Completeness here means a complete calendar, not complete reporting. A zero row is **no
recorded event**, not verified absence of violence. Start/end dates stay within the observed
national date bounds; the builder does not extend the restricted export through today.
The account's 12-month recency limit remains visible. The earlier September 2025 forecast
replay is explicitly separate from this daily dataset ending in November 2025.
