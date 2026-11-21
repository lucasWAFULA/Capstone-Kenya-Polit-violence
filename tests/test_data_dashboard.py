import json

from fastapi.testclient import TestClient

from severity_service.app import create_app
from severity_service.data_dashboard import daily_state
from test_api import registry


def test_missing_and_metadata_only_deployment(tmp_path):
    assert not daily_state(tmp_path)[0]['available']
    directory=tmp_path/'artifacts/data_quality'
    directory.mkdir(parents=True)
    (directory/'daily_summary.json').write_text(json.dumps({'rows':47,'source_run_id':'source'}))
    summary,payload=daily_state(tmp_path)
    assert summary['available'] and not summary['series_available'] and payload is None


def test_daily_endpoint_bounds_and_private_aggregate_only(tmp_path,monkeypatch):
    root=tmp_path/'data'
    output=root/'daily/example'
    output.mkdir(parents=True)
    summary={'source_run_id':'source','end_date':'2025-11-15'}
    rows=[{'date':'2025-11-15','events':0,'fatalities':0,'high_political_violence_events':0}]
    (output/'dashboard.json').write_text(json.dumps({'summary':summary,'national':rows,'counties':{'Nairobi':rows}}))
    (root/'daily/latest.json').write_text(json.dumps({'directory':str(output)}))
    (root/'latest.json').write_text(json.dumps({'run_id':'source'}))
    monkeypatch.setenv('DAILY_DATA_ROOT',str(tmp_path))
    with TestClient(create_app(registry())) as client:
        assert client.get('/v1/data/summary').json()['matches_latest_extraction']
        response=client.get('/v1/data/daily?county=Nairobi&days=7')
        assert response.status_code==200
        assert response.json()['series'][0]['events']==0
        assert 'directory' not in response.text
        assert client.get('/v1/data/daily?county=Unknown').status_code==422
        assert client.get('/v1/data/daily?days=366').status_code==422


def test_new_extraction_marks_old_panel_as_older(tmp_path):
    root=tmp_path/'data'
    output=root/'daily/example'
    output.mkdir(parents=True)
    (output/'dashboard.json').write_text(json.dumps({'summary':{'source_run_id':'old'},'national':[],'counties':{}}))
    (root/'daily/latest.json').write_text(json.dumps({'directory':str(output)}))
    (root/'latest.json').write_text(json.dumps({'run_id':'new'}))
    assert daily_state(tmp_path)[0]['matches_latest_extraction'] is False


def test_packaged_daily_series_requires_matching_provenance(tmp_path):
    directory = tmp_path / 'artifacts/data_quality'
    directory.mkdir(parents=True)
    (directory / 'daily_summary.json').write_text(json.dumps({'source_run_id': 'verified'}))
    path = directory / 'daily_activity.json'
    payload = {'summary': {'source_run_id': 'other'}, 'national': [], 'counties': {}}
    path.write_text(json.dumps(payload))
    assert daily_state(tmp_path)[1] is None
    payload['summary']['source_run_id'] = 'verified'
    path.write_text(json.dumps(payload))
    summary, series = daily_state(tmp_path)
    assert summary['series_available'] and series['summary']['source_run_id'] == 'verified'
