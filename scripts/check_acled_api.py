"""Print connection metadata only, never OAuth tokens or event narratives."""
import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from severity_service.ingestion import API_URL, access_token, request_json

if __name__ == '__main__':
    load_dotenv(ROOT / '.env')
    try:
        with httpx.Client(timeout=120) as client:
            token = access_token(client)
            response = request_json(client,'GET',API_URL,
                headers={'Authorization':f'Bearer {token}'},params={
                    'country':'Kenya','export_type':'dyadic','cursor':0,'limit':1,'with_total':'true','_format':'json'})
            print(json.dumps({k:response.get(k) for k in ['status','success','count','total_count','next_cursor','last_update','data_query_restrictions']},indent=2))
            print('Response keys:', sorted(response))
            print('Event field names:', sorted(response.get('data',[{}])[0]) if response.get('data') else [])
    except Exception:
        print('Connection check failed. Check local credentials, network access, and ACLED API entitlement.',file=sys.stderr)
        sys.exit(1)
