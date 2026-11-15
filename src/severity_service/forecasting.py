"""Retrospective county-week forecasting research, separate from event assessment."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

COUNTIES = ['Baringo', 'Bomet', 'Bungoma', 'Busia', 'Elgeyo Marakwet', 'Embu',
 'Garissa', 'Homa Bay', 'Isiolo', 'Kajiado', 'Kakamega', 'Kericho', 'Kiambu',
 'Kilifi', 'Kirinyaga', 'Kisii', 'Kisumu', 'Kitui', 'Kwale', 'Laikipia', 'Lamu',
 'Machakos', 'Makueni', 'Mandera', 'Marsabit', 'Meru', 'Migori', 'Mombasa',
 'Muranga', 'Nairobi', 'Nakuru', 'Nandi', 'Narok', 'Nyamira', 'Nyandarua',
 'Nyeri', 'Samburu', 'Siaya', 'Taita Taveta', 'Tana River', 'Tharaka-Nithi',
 'Trans Nzoia', 'Turkana', 'Uasin Gishu', 'Vihiga', 'Wajir', 'West Pokot']
VIOLENT_TYPES = ['Battles', 'Violence against civilians', 'Explosions/Remote violence']
NUMERIC = ['events_7d', 'events_30d', 'events_90d', 'high_30d', 'violent_90d',
           'days_since_event', 'no_previous_event', 'activity_change_30d',
           'month_sin', 'month_cos', 'quarter']
FEATURES = ['county', *NUMERIC]
LIMITATION = ('Retrospective research only. Historical first-seen timestamps and record '
              'versions are unavailable. A fixed reporting-delay assumption cannot '
              'reconstruct real-time knowledge or remove revision bias. Zero rows mean '
              'no recorded event, not verified absence of violence.')


def county_weeks(events: pd.DataFrame, *, coverage_end, reporting_delay_days=7,
                 start='2000-01-03', counties=COUNTIES) -> pd.DataFrame:
    """Monday origins, full county calendar, [origin, origin+7) labels.

    Predictors use incident dates strictly before origin minus the assumed delay.
    Explicit coverage_end is the last fully observed date, not today's date.
    """
    if reporting_delay_days < 0:
        raise ValueError('Reporting delay must be nonnegative')
    end = pd.Timestamp(coverage_end).normalize()
    data = events.copy()
    data['event_date'] = pd.to_datetime(data['event_date'], errors='raise').dt.normalize()
    data['fatalities'] = pd.to_numeric(data['fatalities'], errors='raise')
    if data[['event_id_cnty', 'admin1', 'event_date', 'fatalities', 'disorder_type', 'event_type']].isna().any().any():
        raise ValueError('Required event fields contain missing values')
    if (data.fatalities < 0).any():
        raise ValueError('Negative fatalities')
    # The source export repeats events across actor rows. Count incidents, not actors.
    data = data[['event_id_cnty', 'event_date', 'admin1', 'fatalities',
                 'disorder_type', 'event_type']].drop_duplicates()
    if data.event_id_cnty.duplicated().any():
        raise ValueError('Duplicate event IDs: reconcile record versions before forecasting')
    unknown = set(data.admin1) - set(counties)
    if unknown:
        raise ValueError(f'Unrecognised counties: {sorted(unknown)}')
    data = data.loc[(data.event_date <= end) & data.disorder_type.ne('Strategic developments')].copy()
    if data.empty:
        raise ValueError('No eligible events in coverage period')
    data['violent'] = data.event_type.isin(VIOLENT_TYPES).astype(int)
    data['high'] = ((data.fatalities >= 3) & data.violent.eq(1)
                    & data.disorder_type.str.contains('Political violence', regex=False)).astype(int)
    dates = pd.date_range(min(data.event_date.min(), pd.Timestamp(start) - pd.Timedelta(days=365)), end + pd.Timedelta(days=1))
    origins = pd.date_range(start, end - pd.Timedelta(days=6), freq='W-MON')
    origins = origins[origins - pd.Timedelta(days=reporting_delay_days + 90) >= dates.min()]
    if origins.empty:
        raise ValueError('Insufficient history or no fully observed forecast windows')
    rows = []
    for county in counties:
        subset = data.loc[data.admin1.eq(county)]
        daily = subset.groupby('event_date').agg(events=('event_id_cnty', 'size'),
                    high=('high', 'sum'), violent=('violent', 'sum')).reindex(dates, fill_value=0)
        features = pd.DataFrame(index=dates)
        for column, window, name in [('events',7,'events_7d'), ('events',30,'events_30d'),
                ('events',90,'events_90d'), ('high',30,'high_30d'), ('violent',90,'violent_90d')]:
            features[name] = daily[column].shift(1).rolling(window, min_periods=window).sum()
        features['activity_change_30d'] = features.events_30d - features.events_30d.shift(30)
        last = pd.Series(pd.NaT, index=dates, dtype='datetime64[ns]')
        last.loc[daily.events.gt(0)] = dates[daily.events.gt(0)]
        last = last.ffill().shift(1)
        features['no_previous_event'] = last.isna().astype(int)
        features['days_since_event'] = (dates.to_series() - last).dt.days.fillna(3650)
        cutoff = origins - pd.Timedelta(days=reporting_delay_days)
        frame = features.loc[cutoff].copy().reset_index(drop=True)
        frame['origin'] = origins
        frame['history_cutoff_exclusive'] = cutoff
        frame['label_end_exclusive'] = origins + pd.Timedelta(days=7)
        frame['county'] = county
        cumulative = daily.high.cumsum().shift(1, fill_value=0)
        frame['target'] = ((cumulative.loc[origins + pd.Timedelta(days=7)].to_numpy()
                            - cumulative.loc[origins].to_numpy()) > 0).astype(int)
        frame['month_sin'] = np.sin(2 * np.pi * origins.month / 12)
        frame['month_cos'] = np.cos(2 * np.pi * origins.month / 12)
        frame['quarter'] = origins.quarter
        rows.append(frame)
    result = pd.concat(rows, ignore_index=True).sort_values(['origin', 'county']).reset_index(drop=True)
    if result[FEATURES].isna().any().any():
        raise ValueError('Feature history incomplete')
    return result


def candidates():
    preprocess = ColumnTransformer([
        ('county', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ['county']),
        ('numeric', StandardScaler(), NUMERIC)])
    estimators = {
        'Prevalence baseline': DummyClassifier(strategy='prior'),
        'Logistic Regression': LogisticRegression(max_iter=1500, random_state=42),
        'Random Forest': RandomForestClassifier(n_estimators=100, min_samples_leaf=10,
                                                max_depth=12, n_jobs=2, random_state=42),
        'XGBoost': XGBClassifier(n_estimators=150, max_depth=3, learning_rate=.05,
                                n_jobs=2, random_state=42, eval_metric='logloss'),
    }
    return {name: Pipeline([('preprocess', clone(preprocess)), ('model', model)])
            for name, model in estimators.items()}


def metrics(y, probability, threshold=.5):
    prediction = np.asarray(probability) >= threshold
    tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel()
    return {'rows': len(y), 'positives': int(np.sum(y)),
        'precision': precision_score(y, prediction, zero_division=0),
        'recall': recall_score(y, prediction, zero_division=0),
        'macro_f1': f1_score(y, prediction, labels=[0,1], average='macro', zero_division=0),
        'pr_auc': average_precision_score(y, probability) if np.sum(y) else None,
        'roc_auc': roc_auc_score(y, probability) if len(np.unique(y)) == 2 else None,
        'brier_score': brier_score_loss(y, probability),
        'false_alarm_rate': float(fp / (fp + tn)) if fp + tn else None,
        'false_discovery_rate': float(fp / (fp + tp)) if fp + tp else None}


def run_research(data_path, output_path, *, coverage_end, reporting_delay_days=7):
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)
    frame = county_weeks(pd.read_csv(data_path, low_memory=False), coverage_end=coverage_end,
                         reporting_delay_days=reporting_delay_days)
    frame.to_csv(output / 'county_week_dataset.csv', index=False)
    models = candidates()
    rolling = []
    for year in [2019, 2020, 2021]:
        boundary = pd.Timestamp(f'{year}-01-01')
        train = frame.label_end_exclusive + pd.Timedelta(days=reporting_delay_days) <= boundary
        valid = frame.origin.ge(boundary) & frame.label_end_exclusive.le(pd.Timestamp(f'{year+1}-01-01'))
        for name, candidate in models.items():
            model = clone(candidate).fit(frame.loc[train, FEATURES], frame.loc[train, 'target'])
            p = model.predict_proba(frame.loc[valid, FEATURES])[:, 1]
            rolling.append({'model': name, 'year': year, **metrics(frame.loc[valid, 'target'], p)})
            print(f'Rolling evaluation: {year}, {name}', flush=True)
    rolling = pd.DataFrame(rolling)
    rolling.to_csv(output / 'rolling_metrics.csv', index=False)
    eligible = rolling[rolling.model.ne('Prevalence baseline')]
    selected = eligible.groupby('model').pr_auc.mean().idxmax()
    # All fitting and tuning periods precede the untouched 2024+ test.
    train = frame.label_end_exclusive + pd.Timedelta(days=reporting_delay_days) <= pd.Timestamp('2022-01-01')
    calibration = frame.origin.ge('2022-01-01') & (frame.label_end_exclusive + pd.Timedelta(days=reporting_delay_days)).le('2023-01-01')
    tuning = frame.origin.ge('2023-01-01') & (frame.label_end_exclusive + pd.Timedelta(days=reporting_delay_days)).le('2024-01-01')
    test = frame.origin.ge('2024-01-01')
    model = clone(models[selected]).fit(frame.loc[train, FEATURES], frame.loc[train, 'target'])
    def logits(probability):
        p = np.clip(probability, 1e-6, 1 - 1e-6)
        return np.log(p / (1-p)).reshape(-1, 1)
    calibration_p = model.predict_proba(frame.loc[calibration, FEATURES])[:,1]
    calibrator = LogisticRegression(C=1e6).fit(logits(calibration_p), frame.loc[calibration, 'target'])
    raw = model.predict_proba(frame.loc[tuning, FEATURES])[:,1]
    tuned = calibrator.predict_proba(logits(raw))[:,1]
    thresholds = np.linspace(.01, .99, 99)
    threshold = float(max(thresholds, key=lambda t: f1_score(frame.loc[tuning, 'target'], tuned >= t, zero_division=0)))
    test_frame = frame.loc[test, ['county','origin','label_end_exclusive','target']].copy()
    raw = model.predict_proba(frame.loc[test, FEATURES])[:,1]
    probability = calibrator.predict_proba(logits(raw))[:,1]
    test_frame['probability'] = probability
    test_frame.to_csv(output / 'test_predictions.csv', index=False)
    by_county = [{'county': county, **metrics(group.target, group.probability, threshold)}
                 for county, group in test_frame.groupby('county')]
    pd.DataFrame(by_county).to_csv(output / 'county_test_metrics.csv', index=False)
    by_year = [{'year': year, **metrics(group.target, group.probability, threshold)}
               for year, group in test_frame.groupby(test_frame.origin.dt.year)]
    pd.DataFrame(by_year).to_csv(output / 'annual_test_metrics.csv', index=False)
    bins = pd.cut(probability, np.linspace(0,1,11), include_lowest=True)
    calibration_table = test_frame.assign(bin=bins).groupby('bin', observed=True).agg(
        count=('target','size'), mean_probability=('probability','mean'), observed_rate=('target','mean'))
    calibration_table.to_csv(output / 'test_reliability.csv')
    baseline = float(frame.loc[train, 'target'].mean())
    summary = {'status':'retrospective_research_not_live', 'limitation': LIMITATION,
        'coverage_end': str(pd.Timestamp(coverage_end).date()), 'reporting_delay_days': reporting_delay_days,
        'horizon_days':7, 'counties':len(COUNTIES), 'county_weeks':len(frame),
        'selected_model':selected, 'selection':'mean 2019–2021 rolling validation average precision',
        'train':'before 2022; label availability purged at boundaries',
        'calibration':'2022 sigmoid calibration', 'threshold_tuning':'2023 positive-class F1',
        'threshold':threshold, 'test':'2024 onwards; complete seven-day horizons only',
        'test_metrics':metrics(test_frame.target, probability, threshold),
        'uncalibrated_test_metrics':metrics(test_frame.target, raw, threshold),
        'baseline_test_metrics':metrics(test_frame.target, np.full(len(test_frame), baseline), threshold)}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    joblib.dump({'model':model, 'calibrator':calibrator, 'features':FEATURES,
                 'metadata':summary}, output / 'forecast_model_bundle.joblib')
    return summary
