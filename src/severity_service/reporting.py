"""Reporting-access evidence; connectivity never implies current incident coverage."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from uuid import uuid4

import httpx

from .ingestion import API_URL,access_token,active_restrictions,request_json


def probe_reporting(*,client=None,now=None):
    now=now or datetime.now(timezone.utc)
    today=now.astimezone(ZoneInfo('Africa/Nairobi')).date()
    start=today-timedelta(days=13)
    owned=client is None
    client=client or httpx.Client(timeout=60,follow_redirects=False)
    result={'checked_at':now.isoformat(),'api_connected':False,'ready_for_recent_reporting':False,
            'recent_period_start':str(start),'recent_period_end':str(today),
            'recent_records_available':None,'status':'connection_failed',
            'cadence':'ACLED releases event data weekly; this is not an instant incident stream.',
            'notice':'API check failed. Verify local credentials and connectivity.'}
    try:
        token=access_token(client)
        parameters={'country':'Kenya','export_type':'dyadic','cursor':0,'limit':1,'with_total':'true','_format':'json'}
        full=request_json(client,'GET',API_URL,headers={'Authorization':f'Bearer {token}'},params=parameters)
        if full.get('success') is not True:
            raise ValueError('Unsuccessful access query')
        result['api_connected']=True
        restrictions=active_restrictions(full.get('data_query_restrictions')) or {}
        result['access_restrictions']=restrictions
        result['accessible_history_records']=full.get('total_count')
        recent=request_json(client,'GET',API_URL,headers={'Authorization':f'Bearer {token}'},
            params={**parameters,'event_date':f'{start}|{today}','event_date_where':'BETWEEN'})
        if recent.get('success') is not True or recent.get('total_count') is None:
            raise ValueError('Recent query completeness metadata missing')
        recent_restrictions=active_restrictions(recent.get('data_query_restrictions')) or {}
        restrictions=restrictions or recent_restrictions
        result['access_restrictions']=restrictions
        result['recent_records_available']=int(recent['total_count'])
        age=full.get('last_update')
        result['source_update_age_hours']=age
        if restrictions:
            result.update(status='access_delayed',notice='API connected, but account restrictions prevent confirmed current Kenya reporting. Request current event-data access from ACLED.')
        elif result['recent_records_available'] <= 0:
            result.update(status='recency_unconfirmed',notice='No accessible records in the last 14 days. Current coverage cannot be confirmed; historical data remain available.')
        else:
            # An actual event in the requested recent interval is evidence of accessible recent reporting.
            dates=[str(row.get('event_date',''))[:10] for row in recent.get('data',[])]
            if not dates or not all(str(start)<=day<=str(today) for day in dates):
                raise ValueError('Recent query returned dates outside its requested interval')
            result.update(status='recent_reporting_accessible',ready_for_recent_reporting=True,
                notice='Recent Kenya records are accessible. Run the reporting update to ingest them; this does not establish complete reporting or a validated forecast.')
    except Exception:
        result.update(status='check_failed',ready_for_recent_reporting=False,
                      notice='Reporting verification failed; retain historical display until a successful check.')
    finally:
        if owned:client.close()
    return result


def save_status(root,result):
    path=Path(root)/'runtime/reporting_status.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        previous=json.loads(path.read_text(encoding='utf-8'))
        for key in ['last_successful_sync_at','latest_ingested_event_date','source_run_id','sync_status']:
            if key not in result and key in previous:result[key]=previous[key]
    temporary=path.with_suffix('.'+uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(result,indent=2),encoding='utf-8')
    temporary.replace(path)


def reporting_status(root,*,now=None):
    now=now or datetime.now(timezone.utc)
    path=Path(root)/'runtime/reporting_status.json'
    if not path.exists():
        return {'status':'not_checked','api_connected':False,'ready_for_recent_reporting':False,
                'notice':'Run scripts/check_reporting_access.py to verify current API access.','check_stale':True}
    result=json.loads(path.read_text(encoding='utf-8'))
    age=now-datetime.fromisoformat(result['checked_at'])
    result['check_stale']=not timedelta(0)<=age<=timedelta(hours=24)
    if result['check_stale']:
        result.update(ready_for_recent_reporting=False,notice='Access check is older than 24 hours. Recheck before claiming recent reporting access.')
    return result


def reporting_evidence(root,source_run_id,*,now=None):
    now=now or datetime.now(timezone.utc)
    result=reporting_status(root,now=now)
    recent=False
    if result.get('ready_for_recent_reporting') and result.get('sync_status')=='ok' and result.get('source_run_id')==source_run_id:
        when=datetime.fromisoformat(result['last_successful_sync_at'])
        latest=result.get('latest_ingested_event_date')
        today=now.astimezone(ZoneInfo('Africa/Nairobi')).date()
        incident=datetime.fromisoformat(latest).date() if latest else None
        recent=(timedelta(0)<=now-when<=timedelta(hours=24) and incident is not None
                and today-timedelta(days=13)<=incident<=today)
    return {'status':result['status'],'checked_at':result.get('checked_at'),
            'last_successful_sync_at':result.get('last_successful_sync_at'),
            'recent_ingestion':recent}
