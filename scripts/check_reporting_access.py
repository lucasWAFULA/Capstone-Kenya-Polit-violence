"""Check current-data entitlement without downloading or retraining models."""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from severity_service.reporting import probe_reporting,save_status

if __name__=='__main__':
    load_dotenv(ROOT/'.env')
    result=probe_reporting()
    save_status(ROOT,result)
    print(json.dumps(result,indent=2))
    sys.exit(0 if result['ready_for_recent_reporting'] else 2)
