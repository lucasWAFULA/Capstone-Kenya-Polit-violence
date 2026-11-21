import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from severity_service.app import create_app
from severity_service.outlook import METHODS, build_outlook, predict
from test_api import registry

ROOT = Path(__file__).resolve().parents[1]


def history():
    package = json.loads((ROOT / 'artifacts/outlook/annual_history.json').read_text())
    return pd.DataFrame(package['counties'], index=package['years']), package['source']


def test_outlook_dates_county_coverage_nonnegative_bands_and_reconciliation():
    annual, source = history()
    result = build_outlook(annual, source=source)
    assert result['training_end_year'] == 2024
    assert result['excluded_partial_year'] == 2025
    assert result['unobserved_bridge_years'] == [2025]
    assert result['holdout_period'] == [2019, 2024]
    assert len(result['counties']) == 47
    for series in [result['national'], *result['counties']]:
        assert [r['year'] for r in series['projections']] == list(range(2026, 2031))
        assert [r['lead_years'] for r in series['projections']] == list(range(2, 7))
        for row in series['projections']:
            assert 0 <= row['lower'] <= row['expected'] <= row['upper']
            assert all(np.isfinite(row[k]) for k in ('lower', 'expected', 'upper'))
    for i, national in enumerate(result['national']['projections']):
        assert abs(national['expected'] - sum(c['projections'][i]['expected'] for c in result['counties'])) < .005


def test_heldout_outcomes_cannot_change_model_selection_or_validation_scores():
    annual, source = history()
    before = build_outlook(annual, source=source)
    altered = annual.copy()
    altered.loc[2019:] += 1000
    after = build_outlook(altered, source=source)
    assert before['selected_model'] == after['selected_model']
    assert before['validation_scores'] == after['validation_scores']
    assert before['test_metrics'] != after['test_metrics']


def test_partial_year_and_missing_calendar_rejected():
    annual, source = history()
    annual.loc[2025] = 1
    with pytest.raises(ValueError, match='Partial'):
        build_outlook(annual, source=source)
    annual = annual.drop(2025).drop(2010)
    with pytest.raises(ValueError):
        build_outlook(annual, source=source)


def test_serialized_outlook_reproduces_from_committed_annual_counts():
    annual, source = history()
    result = build_outlook(annual, source=source)
    saved = json.loads((ROOT / 'artifacts/outlook/outlook.json').read_text())
    for key in ('selected_model', 'validation_scores', 'test_metrics', 'national', 'counties'):
        assert result[key] == saved[key]


def test_outlook_endpoint_is_separate_from_weekly_probabilities_and_alerts():
    with TestClient(create_app(registry())) as client:
        response = client.get('/v1/outlook')
        assert response.status_code == 200
        body = response.json()
        assert body['mode'] == 'long_term_research_outlook'
        assert body['operationally_validated'] is False
        assert body['start_year'] == 2026 and body['end_year'] == 2030
        assert 'probability' not in body['national']['projections'][0]
        assert client.get('/v1/alerts').json()['alerts'] == []


def test_count_predictors_reject_invalid_history():
    for method in METHODS:
        assert np.isfinite(predict([0] * 10, 6, method)).all()
        with pytest.raises(ValueError):
            predict([1, 2, -1, 0, 1], 6, method)
