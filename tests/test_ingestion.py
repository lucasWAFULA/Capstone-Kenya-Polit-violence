from datetime import datetime, timezone
import json

import httpx
import pandas as pd
import pytest

from severity_service.ingestion import EventStore, fetch_acled, normalise
from severity_service.early_warning import dashboard_state, generate
from severity_service.forecasting import county_weeks, FEATURES


def records():
    return [{'event_id_cnty':'KEN1', 'event_date':'1999-01-01', 'admin1':'Nairobi',
             'fatalities':3, 'disorder_type':'Political violence', 'event_type':'Battles', 'country':'Kenya'}]


def test_oauth_cursor_pages_and_total(monkeypatch):
    monkeypatch.delenv('ACLED_ACCESS_TOKEN', raising=False)
    monkeypatch.setenv('ACLED_USERNAME','test-user')
    monkeypatch.setenv('ACLED_PASSWORD','not-a-real-password')
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == 'POST':
            return httpx.Response(200, json={'access_token':'test-token'})
        cursor = request.url.params['cursor']
        row = dict(records()[0], event_id_cnty='KEN1' if cursor == '0' else 'KEN2')
        return httpx.Response(200, json={'success':True, 'data':[row], 'total_count':2,
                                       'last_update':24, 'next_cursor':'123' if cursor == '0' else None})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_acled('2025-09-07',client=client)
    assert len(result) == 2
    assert calls[2].url.params['cursor'] == '123'
    assert calls[1].headers['Authorization'] == 'Bearer test-token'
    assert calls[1].url.params['export_type'] == 'dyadic'


@pytest.mark.parametrize('change', [
    {'total_count':2}, {'data_query_restrictions':{'recency':'restricted'}},
    {'success':False}, {'next_cursor':'0'},
    {'last_update':250}, {'last_update':None},
])
def test_incomplete_or_restricted_download_not_published(monkeypatch, change):
    monkeypatch.setenv('ACLED_ACCESS_TOKEN','test-token')
    payload = {'success':True,'data':records(),'total_count':1,'next_cursor':None,'last_update':24, **change}
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,json=payload))) as client:
        with pytest.raises(RuntimeError):
            fetch_acled('2025-09-07',client=client)


def test_revision_first_seen_and_failed_validation_atomic(tmp_path):
    store = EventStore(tmp_path/'events.sqlite3')
    first = store.publish(records(), '2025-09-07', collected_at='2026-11-01T00:00:00+00:00')
    revised = [dict(records()[0], fatalities=5)]
    second = store.publish(revised, '2025-09-07', collected_at='2026-11-08T00:00:00+00:00')
    assert store.snapshot(first)[1].fatalities.iloc[0] == 3
    assert store.snapshot(second)[1].fatalities.iloc[0] == 5
    with store.connect() as db:
        assert db.execute('SELECT first_seen_at FROM first_seen').fetchone()[0] == '2026-11-01T00:00:00+00:00'
    with pytest.raises(ValueError):
        store.publish([dict(records()[0], admin1='Unknown')], '2025-09-07')
    assert store.snapshot()[0]['id'] == second


def test_no_future_labels_and_identical_research_serving_features():
    data = pd.DataFrame(records())
    historical = county_weeks(data, coverage_end='2000-01-10', start='2000-01-03')
    serving = county_weeks(data, coverage_end='2000-01-02', forecast_origin='2000-01-03')
    assert 'target' not in serving
    pd.testing.assert_frame_equal(historical.loc[historical.origin.eq('2000-01-03'), FEATURES].reset_index(drop=True), serving[FEATURES])
    with pytest.raises(ValueError, match='coverage'):
        county_weeks(data, coverage_end='2000-01-02', forecast_origin='2026-11-16')


def sample_forecast():
    return {'mode':'current_research','origin':'2026-11-16','end_exclusive':'2026-11-23',
        'generated_at':'2026-11-15T12:00:00+00:00', 'threshold':.08,
        'snapshot':{'id':1, 'collected_at':'2026-11-15T11:00:00+00:00', 'source_updated_at':'2026-11-14T11:00:00+00:00'},
        'counties':[{'county':'Nairobi','probability':.2}]}


def test_alerts_expire_and_failed_updates_suppress(tmp_path):
    store = EventStore(tmp_path/'events.sqlite3')
    store.save_forecast(sample_forecast())
    now = datetime(2026,11,15,13,tzinfo=timezone.utc)
    fresh = dashboard_state(store,now=now)
    assert fresh['fresh'] and len(fresh['alerts']) == 1
    assert not dashboard_state(store,now=datetime(2026,11,24,tzinfo=timezone.utc))['alerts']
    with store.connect() as db:
        db.execute('INSERT INTO attempts(finished_at,outcome) VALUES(?,?)', ('2026-11-15T12:30:00+00:00','failed'))
    assert not dashboard_state(store,now=now)['alerts']


def test_historical_demo_never_issues_current_alerts(tmp_path):
    path=tmp_path/'demo.json'
    demo=sample_forecast()
    demo.update(mode='historical_demo',generated_at=None)
    path.write_text(json.dumps(demo))
    state=dashboard_state(demo_path=path,now=datetime(2026,11,15,tzinfo=timezone.utc))
    assert state['mode']=='historical_demo' and not state['alerts'] and not state['fresh']


def test_old_export_cannot_be_used_for_current_forecast(tmp_path):
    store=EventStore(tmp_path/'events.sqlite3')
    store.publish(records(),'2025-09-07',source='historical_export')
    with pytest.raises(ValueError,match='authenticated'):
        generate(store, 'unused-model')


def test_real_forecasting_bundle_with_versioned_snapshot(tmp_path):
    from pathlib import Path
    store=EventStore(tmp_path/'events.sqlite3')
    now=datetime(2026,11,15,12,tzinfo=timezone.utc)
    store.publish(records(),'2026-11-14',collected_at='2026-11-15T11:00:00+00:00',
                  source_updated_at='2026-11-14T11:00:00+00:00')
    model=Path(__file__).resolve().parents[1]/'artifacts/forecasting/forecast_model_bundle.joblib'
    forecast=generate(store,model,now=now)
    assert len(forecast['counties']) == 47
    assert forecast['origin'] == '2026-11-16'
    assert all(0 <= row['probability'] <= 1 for row in forecast['counties'])
    assert dashboard_state(store,now=now)['fresh']
