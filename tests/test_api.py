from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from severity_service.app import create_app
from severity_service.features import CLASS_ORDER, FEATURE_COLUMNS
from severity_service.registry import ModelRegistry


class FixedModel:
    classes_ = np.array(CLASS_ORDER)

    def __init__(self, probabilities):
        self.probabilities = np.array(probabilities)

    def predict_proba(self, frame):
        assert list(frame.columns) == FEATURE_COLUMNS
        return np.tile(self.probabilities, (len(frame), 1))


def registry():
    return ModelRegistry(
        primary=FixedModel([0.1, 0.2, 0.7]),
        challenger=FixedModel([0.6, 0.3, 0.1]),
        manifest={
            "version": "test-1", "models": {
                "primary": {"name": "Logistic Regression"},
                "challenger": {"name": "XGBoost"},
            },
        },
    )


EVENT = {
    "event_date": "2026-09-20", "disorder_type": "Political violence",
    "event_type": "Battles", "sub_event_type": "Armed clash", "admin1": "Nairobi",
    "admin2": "Nairobi", "inter1": 1, "interaction": 12, "civilian_targeting": None,
    "county_events_previous_30_days": 8, "county_events_previous_90_days": 20,
    "violent_events_previous_30_days": 4, "previous_high_severity_events_in_county": 1,
    "days_since_previous_event_in_county": 2, "actor_previous_event_count": 15,
}


def test_predict_serves_primary_only():
    with TestClient(create_app(registry())) as client:
        response = client.post("/v1/predict", json=EVENT)
    assert response.status_code == 200
    body = response.json()
    assert body["severity"] == "High"
    assert body["model_name"] == "Logistic Regression"
    assert body["model_version"] == "test-1"
    assert body["probabilities"] == {"Low": 0.1, "Moderate": 0.2, "High": 0.7}
    assert "X-Process-Time-Ms" in response.headers


def test_rejects_missing_history_and_unknown_fields():
    invalid = {**EVENT, "unknown": 1}
    invalid.pop("actor_previous_event_count")
    with TestClient(create_app(registry())) as client:
        response = client.post("/v1/predict", json=invalid)
    assert response.status_code == 422


def test_batch_limit_and_readiness():
    with TestClient(create_app(registry())) as client:
        ready = client.get("/health/ready")
        prediction = client.post("/v1/predict/batch", json={"events": [EVENT, EVENT]})
    assert ready.json() == {"status": "ready", "model_version": "test-1"}
    assert len(prediction.json()) == 2


def test_dashboard_and_guide_aliases():
    with TestClient(create_app(registry())) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        if "K-PVIEWS" in page.text:
            assert '/ui/assets/' in page.text
            assert "K-PVIEWS" in client.get('/event-assessment').text
            import re
            assets = re.findall(r'(?:src|href)="(/ui/assets/[^\"]+)"', page.text)
            assert assets
            for asset in assets:
                assert client.get(asset).status_code == 200
        else:
            assert "Event Severity Monitor" in page.text
            assert "National risk overview" in page.text
            assert "Event Severity Monitor" in client.get('/event-assessment').text
        assert len(client.get('/static/kenya-counties.geojson').json()['features']) == 47
        forecasts = client.get('/v1/forecasts').json()
        assert len(forecasts['counties']) == 47
        assert client.get('/v1/alerts').json()['alerts'] == []
        assert client.get("/health").json()["status"] == "ready"
        assert client.post("/predict", json=EVENT).json()["severity"] == "High"


def test_governance_metadata_and_fatalities_rejection():
    with TestClient(create_app(registry())) as client:
        info = client.get('/v1/models/info')
        assert info.status_code == 200
        assert info.json()['primary'] == 'Logistic Regression'
        assert 'file' not in info.json()['training_data']
        assert client.post('/v1/predict', json={**EVENT, 'fatalities': 3}).status_code == 422


def test_rejects_negative_history_and_empty_batch():
    with TestClient(create_app(registry())) as client:
        assert client.post("/predict", json={**EVENT, "actor_previous_event_count": -1}).status_code == 422
        assert client.post("/v1/predict/batch", json={"events": []}).status_code == 422
        assert client.post("/v1/predict/batch", json={"events": [EVENT] * 1001}).status_code == 422


def test_real_artifacts_match_primary_pipeline():
    from pathlib import Path
    import pandas as pd
    from severity_service.features import add_calendar_features

    real = ModelRegistry.load(Path(__file__).resolve().parents[1] / "artifacts/production")
    frame = add_calendar_features(pd.DataFrame([EVENT])).fillna(np.nan)
    expected = real.primary.predict_proba(frame)[0]
    with TestClient(create_app(real)) as client:
        response = client.post("/v1/predict", json=EVENT)
        assert response.status_code == 200
        result = response.json()
        assert result["severity"] == real.primary.predict(frame)[0]
        assert abs(sum(result["probabilities"].values()) - 1) < 1e-8
        for label, probability in zip(real.primary.classes_, expected):
            assert np.isclose(result["probabilities"][label], probability)
