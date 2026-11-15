import json

from fastapi.testclient import TestClient

from severity_service.app import create_app
from severity_service.data_dashboard import county_activity,map_activity
from test_api import registry


def test_map_aggregates_recorded_counts_without_forecast_probabilities():
    payload={'summary':{'source_run_id':'source','end_date':'2025-11-15'},'counties':{
        'Nairobi':[{'date':'2025-11-14','events':4,'fatalities':2,'high_political_violence_events':0},
                   {'date':'2025-11-15','events':2,'fatalities':3,'high_political_violence_events':1}],
        'Bomet':[{'date':'2025-11-15','events':0,'fatalities':0,'high_political_violence_events':0}]}}
    result=county_activity(payload,7)
    assert result['counties'][0]['events']==6
    assert result['counties'][0]['fatalities']==5
    assert result['counties'][1]['events']==0
    assert all('probability' not in row for row in result['counties'])


def test_packaged_counts_power_map_without_private_data(tmp_path,monkeypatch):
    path=tmp_path/'artifacts/data_quality'
    path.mkdir(parents=True)
    data={'mode':'recorded_activity','end_date':'2025-11-15','counties':[{'county':'Nairobi','events':4}]}
    (path/'county_activity.json').write_text(json.dumps({'windows':{'30':data}}))
    assert map_activity(tmp_path,30)==data
    monkeypatch.setenv('DAILY_DATA_ROOT',str(tmp_path))
    with TestClient(create_app(registry())) as client:
        response=client.get('/v1/data/map?days=30').json()
        assert response['counties']==data['counties']
        assert not response['reporting']['recent_ingestion']
        assert client.get('/v1/data/map?days=20').status_code==422


def test_real_packaged_map_has_47_actual_counties_all_windows():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    for days in [7,30,90,365]:
        result=map_activity(root,days)
        assert len(result['counties'])==47
        assert len({row['county'] for row in result['counties']})==47
        assert result['end_date']=='2025-11-15'
        assert all(row['events']>=0 for row in result['counties'])
