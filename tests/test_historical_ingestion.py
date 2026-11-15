import json

import httpx
import pandas as pd
import pytest

from severity_service.historical_ingestion import extract_history
from severity_service.ingestion import active_restrictions


def record(number):
    return {'event_id_cnty':f'KEN{number}','event_date':'1999-01-01','country':'Kenya',
            'admin1':'Nairobi','fatalities':'3','disorder_type':'Political violence',
            'event_type':'Battles','notes':'Untouched original narrative', 'timestamp':'12345',
            'sub_event_type':'Armed clash','assoc_actor_1':''}


def test_archive_all_fields_and_restrictions_before_cleaning(tmp_path,monkeypatch):
    monkeypatch.setenv('ACLED_ACCESS_TOKEN','test-token')
    restrictions={'countries':[], 'date_recency':{'quantity':12,'unit':'Months','date':'2025-11-15','timestamp':1}}
    def handler(request):
        first=request.url.params['cursor']=='0'
        restriction={**restrictions,'date_recency':{**restrictions['date_recency'],'timestamp':1 if first else 2}}
        return httpx.Response(200,json={'success':True,'data':[record(1 if first else 2)],
                    'total_count':2,'next_cursor':123 if first else None,'data_query_restrictions':restriction})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report=extract_history(tmp_path,client=client,progress=lambda _:None)
    assert report['total_records_retrieved']==2
    assert report['raw_shape']==[2,11]
    assert report['unique_counties']==1
    assert not report['eligible_for_current_forecasts']
    pointer=json.loads((tmp_path/'latest.json').read_text())
    raw=pd.read_parquet(tmp_path/'raw'/pointer['run_id']/'kenya_acled_raw.parquet')
    assert raw.notes.iloc[0]=='Untouched original narrative'
    assert raw.fatalities.iloc[0]=='3'
    assert raw.assoc_actor_1.iloc[0]==''
    clean=pd.read_parquet(tmp_path/'processed'/pointer['run_id']/'kenya_acled_master.parquet')
    assert clean.fatalities.iloc[0]==3 and clean.severity.iloc[0]=='High'
    assert pd.isna(clean.assoc_actor_1.iloc[0])
    assert report['missing_values_clean']['assoc_actor_1']==2
    assert (tmp_path/'raw'/pointer['run_id']/'page-0001.json').exists()


def test_partial_download_preserves_raw_and_existing_master_pointer(tmp_path,monkeypatch):
    monkeypatch.setenv('ACLED_ACCESS_TOKEN','test-token')
    (tmp_path/'latest.json').write_text('{"run_id":"previous"}')
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={
        'success':True,'data':[record(1)],'total_count':2,'next_cursor':None}))) as client:
        with pytest.raises(ValueError,match='Incomplete'):
            extract_history(tmp_path,client=client,progress=lambda _:None)
    assert json.loads((tmp_path/'latest.json').read_text())['run_id']=='previous'
    manifests=list((tmp_path/'raw').glob('*/manifest.json'))
    assert json.loads(manifests[0].read_text())['status']=='failed'
    assert list((tmp_path/'raw').glob('*/page-0001.json'))


def test_empty_access_restriction_buckets_are_not_restrictions():
    assert not active_restrictions({'countries':[],'event_types':[],'date_recency':None})
    assert active_restrictions({'date_recency':{'quantity':12}})
