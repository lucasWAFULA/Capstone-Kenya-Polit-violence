"""Refresh reported activity independently from the research forecasting model."""
import sys
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from severity_service.reporting import probe_reporting,save_status
from severity_service.historical_ingestion import extract_history
from severity_service.daily_panel import build_daily_dataset

if __name__=='__main__':
    load_dotenv(ROOT/'.env')
    result=probe_reporting()
    save_status(ROOT,result)
    if not result['ready_for_recent_reporting']:
        print(result['notice'],file=sys.stderr)
        sys.exit(2)
    try:
        report=extract_history(ROOT/'data',original=ROOT/'ACLED_Kenya_1997-2025.csv',progress=lambda text:print(text,flush=True))
        today=datetime.now(ZoneInfo('Africa/Nairobi')).date()
        latest=datetime.fromisoformat(report['latest_event_date']).date()
        if report['access_restrictions'] or not today-timedelta(days=13)<=latest<=today:
            result['ready_for_recent_reporting']=False
            raise ValueError('Extraction no longer confirms accessible recent records')
        panel,_=build_daily_dataset(ROOT)
        result.update(sync_status='ok',last_successful_sync_at=panel['built_at'],
            latest_ingested_event_date=report['latest_event_date'],source_run_id=report['run_id'],
            notice='Reported activity refreshed from accessible API records. Forecast models were not retrained or run.')
        save_status(ROOT,result)
        print(f"Reporting refreshed: {report['total_records_retrieved']} records, through {report['latest_event_date']}")
    except Exception:
        result.update(sync_status='failed',notice='Reporting sync failed. Check the preserved raw snapshot; retain previous completed data.')
        save_status(ROOT,result)
        print(result['notice'],file=sys.stderr)
        sys.exit(1)
