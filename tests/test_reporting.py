from datetime import datetime,timedelta,timezone

import httpx

from severity_service.reporting import probe_reporting,save_status,reporting_status,reporting_evidence

NOW=datetime(2026,11,15,12,tzinfo=timezone.utc)


def response_client(restricted=False, count=2):
    def handle(request):
        recent='event_date' in request.url.params
        return httpx.Response(200,json={'success':True,'total_count':count if recent else 19505,
            'data':[{'event_date':'2026-11-12'}] if recent and count else [],
            'data_query_restrictions':{'date_recency':{'quantity':12,'unit':'Months','date':'2025-11-15'}} if restricted else {'countries':[]}})
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_connected_but_delayed_does_not_mean_recent_reporting(monkeypatch):
    monkeypatch.setenv('ACLED_ACCESS_TOKEN','test-token')
    with response_client(restricted=True,count=0) as client:
        result=probe_reporting(client=client,now=NOW)
    assert result['api_connected'] and not result['ready_for_recent_reporting']
    assert result['status']=='access_delayed' and result['recent_records_available']==0


def test_recent_reporting_access_does_not_require_optional_last_update(monkeypatch):
    monkeypatch.setenv('ACLED_ACCESS_TOKEN','test-token')
    with response_client() as client:
        result=probe_reporting(client=client,now=NOW)
    assert result['ready_for_recent_reporting']
    assert result['source_update_age_hours'] is None


def test_no_recent_records_keeps_recency_unconfirmed(monkeypatch):
    monkeypatch.setenv('ACLED_ACCESS_TOKEN','test-token')
    with response_client(count=0) as client:
        result=probe_reporting(client=client,now=NOW)
    assert result['status']=='recency_unconfirmed'
    assert not result['ready_for_recent_reporting']


def test_stale_check_and_unmatched_or_old_data_never_label_recent(tmp_path):
    result={'checked_at':NOW.isoformat(),'status':'recent_reporting_accessible',
        'api_connected':True,'ready_for_recent_reporting':True,'sync_status':'ok',
        'last_successful_sync_at':NOW.isoformat(),'latest_ingested_event_date':'2026-11-12','source_run_id':'current'}
    save_status(tmp_path,result)
    assert reporting_evidence(tmp_path,'current',now=NOW)['recent_ingestion']
    assert not reporting_evidence(tmp_path,'older',now=NOW)['recent_ingestion']
    assert not reporting_status(tmp_path,now=NOW+timedelta(days=2))['ready_for_recent_reporting']
    result['latest_ingested_event_date']='2025-11-15'
    save_status(tmp_path,result)
    assert not reporting_evidence(tmp_path,'current',now=NOW)['recent_ingestion']


def test_new_check_preserves_last_ingestion_evidence(tmp_path):
    save_status(tmp_path,{'checked_at':NOW.isoformat(),'last_successful_sync_at':NOW.isoformat(),
        'source_run_id':'source','status':'recent_reporting_accessible'})
    save_status(tmp_path,{'checked_at':NOW.isoformat(),'status':'access_delayed','ready_for_recent_reporting':False})
    assert reporting_status(tmp_path,now=NOW)['source_run_id']=='source'
