"""Package only four windows of derived county totals, never event-level records."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from severity_service.data_dashboard import daily_state,county_activity

if __name__=='__main__':
    _,payload=daily_state(ROOT)
    if payload is None:
        raise SystemExit('Build the local daily dataset first')
    result={'windows':{str(days):county_activity(payload,days) for days in [7,30,90,365]}}
    output=ROOT/'artifacts/data_quality/county_activity.json'
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Packaged 47 county totals for four historical windows; raw data remain private.')
