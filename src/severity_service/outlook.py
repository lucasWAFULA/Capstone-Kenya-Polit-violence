"""Annual count outlook, separate from the seven-day classification experiment."""
from __future__ import annotations

import numpy as np
import pandas as pd

METHODS = ('Recent five-year mean', 'Damped log trend')


def predict(history, horizon, method):
    """Fit only the supplied historical annual counts; return nonnegative count means."""
    values = np.asarray(history, dtype=float)
    if len(values) < 5 or horizon < 1 or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('At least five finite nonnegative annual counts are required')
    if method == METHODS[0]:
        return np.repeat(values[-5:].mean(), horizon)
    if method != METHODS[1]:
        raise ValueError('Unknown annual outlook method')
    recent = np.log1p(values[-10:])
    slope, _ = np.polyfit(np.arange(len(recent)), recent, 1)
    # Prespecified damping and cap avoid explosive extrapolation; not fitted to the holdout.
    slope = np.clip(slope, -.1, .1)
    steps = np.cumsum(.8 ** np.arange(1, horizon + 1))
    level = np.mean(recent[-3:])
    return np.maximum(0, np.expm1(level + slope * steps))


def evaluate(actual, expected):
    actual, expected = np.asarray(actual), np.asarray(expected)
    return {'mae': float(np.abs(actual - expected).mean()),
            'rmse': float(np.sqrt(np.square(actual - expected).mean()))}


def build_outlook(annual: pd.DataFrame, *, source, start_year=2026, years=5):
    """Select using pre-holdout rolling origins, evaluate six years, then refit all history.

    annual: complete years by counties, with no partial-year exposure adjustments.
    The six-year lead covers the 2025 bridge plus displayed 2026–2030 after a 2024 fit.
    """
    annual = annual.sort_index().sort_index(axis=1)
    if not annual.index.is_unique or annual.isna().any().any() or len(annual) < 25:
        raise ValueError('At least 25 complete, unique annual observations are required')
    if list(annual.index) != list(range(int(annual.index.min()), int(annual.index.max()) + 1)):
        raise ValueError('Annual history must have a complete consecutive calendar')
    if not np.isfinite(annual.to_numpy()).all() or (annual.to_numpy() < 0).any():
        raise ValueError('Annual counts must be finite and nonnegative')
    end = int(annual.index.max())
    coverage = pd.Timestamp(source['coverage_end'])
    last_complete = coverage.year if (coverage.month, coverage.day) == (12, 31) else coverage.year - 1
    if end > last_complete:
        raise ValueError('Partial or future years cannot enter annual training')
    if not np.equal(annual.to_numpy(), np.floor(annual.to_numpy())).all():
        raise ValueError('Annual observed counts must be integers')
    horizon = start_year + years - 1 - end
    if years != 5 or start_year <= end or horizon > 6:
        raise ValueError('This experiment supports five displayed years at most six leads after fitting')
    holdout_origin = end - 6
    validation_origins = range(int(annual.index.min()) + 9, holdout_origin - 5)
    records = {}
    scores = {}
    for method in METHODS:
        actual, predicted = [], []
        for origin in validation_origins:
            history = annual.loc[:origin]
            expected = np.column_stack([predict(history[c], 6, method) for c in annual])
            actual.append(annual.loc[origin + 1:origin + 6].to_numpy())
            predicted.append(expected)
        if not actual:
            raise ValueError('Insufficient pre-holdout validation origins')
        records[method] = (np.stack(actual), np.stack(predicted))
        scores[method] = evaluate(*records[method])
    selected = min(METHODS, key=lambda m: scores[m]['mae'])
    observed, estimated = records[selected]
    # Empirical error bands; pooled counties, separately aggregated national errors.
    scaled = np.abs(observed - estimated) / np.sqrt(estimated + 1)
    county_width = np.maximum.accumulate(np.quantile(scaled, .8, axis=(0, 2)))
    national_width = np.maximum.accumulate(np.quantile(np.abs(observed.sum(axis=2) - estimated.sum(axis=2)), .8, axis=0))
    test = annual.loc[holdout_origin + 1:end].to_numpy()
    test_pred = np.column_stack([predict(annual.loc[:holdout_origin, c], 6, selected) for c in annual])
    test_width = county_width[:, None] * np.sqrt(test_pred + 1)
    test_metrics = evaluate(test, test_pred)
    test_metrics['empirical_band_coverage'] = float(((test >= np.maximum(0, test_pred - test_width)) & (test <= test_pred + test_width)).mean())
    test_metrics['national'] = evaluate(test.sum(axis=1), test_pred.sum(axis=1))
    test_metrics['national']['empirical_band_coverage'] = float((np.abs(test.sum(axis=1) - test_pred.sum(axis=1)) <= national_width).mean())
    baseline_test = np.column_stack([predict(annual.loc[:holdout_origin, c], 6, METHODS[0]) for c in annual])
    projected = np.column_stack([predict(annual[c], horizon, selected) for c in annual])
    def series(column=None):
        expected = projected.sum(axis=1) if column is None else projected[:, column]
        widths = national_width[:horizon] if column is None else county_width[:horizon] * np.sqrt(expected + 1)
        return [{'year': end + i + 1, 'expected': round(float(value), 4),
                 'lower': round(float(max(0, value - widths[i])), 4),
                 'upper': round(float(value + widths[i]), 4), 'lead_years': i + 1}
                for i, value in enumerate(expected) if end + i + 1 >= start_year]
    def history(column=None):
        values = annual.sum(axis=1) if column is None else annual.iloc[:, column]
        return [{'year': int(year), 'observed': int(value)} for year, value in values.items()]
    return {'mode': 'long_term_research_outlook', 'operationally_validated': False,
            'target': 'Annual recorded high-severity political violence event count (3+ fatalities)',
            'start_year': start_year, 'end_year': start_year + years - 1, 'source': source,
            'training_start_year': int(annual.index.min()), 'training_end_year': end,
            'excluded_partial_year': coverage.year if last_complete < coverage.year else None,
            'unobserved_bridge_years': list(range(end + 1, start_year)),
            'selected_model': selected, 'validation_scores': scores,
            'validation_origins': list(validation_origins),
            'holdout_period': [holdout_origin + 1, end], 'test_metrics': test_metrics,
            'baseline_test_metrics': evaluate(test, baseline_test),
            'band': {'label': 'Empirical 80% validation-error band', 'nominal_level': .8,
                     'note': 'Exploratory error bands, not calibrated probability intervals. Overlapping validation windows are dependent. National bands use aggregate errors, not summed county bounds.'},
            'assumptions': {'damping': .8, 'absolute_log_slope_cap': .1,
                            'recent_mean_window': 5, 'trend_window': 10},
            'notice': '2026–2030 research projections from historical counts, not current intelligence or seven-day probabilities. Partial 2025 is excluded; 2025 is an unobserved bridge. Reporting and structural changes can invalidate extrapolation. No alerts are generated.',
            'national': {'history': history(), 'projections': series()},
            'counties': [{'county': c, 'history': history(i), 'projections': series(i)} for i, c in enumerate(annual)]}
