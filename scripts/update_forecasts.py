"""Single scheduled ingestion/forecast job. No credentials appear in arguments or logs."""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from dotenv import load_dotenv
from severity_service.ingestion import EventStore, fetch_acled
from severity_service.early_warning import generate

if __name__ == '__main__':
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser()
    yesterday = datetime.now(ZoneInfo('Africa/Nairobi')).date() - timedelta(days=1)
    parser.add_argument('--coverage-end', default=str(yesterday), help='Query through this day; defaults to yesterday in Nairobi. Reporting completeness is not guaranteed.')
    parser.add_argument('--store', type=Path, default=Path(os.getenv('EVENT_STORE_PATH', str(ROOT / 'runtime/events.sqlite3'))))
    parser.add_argument('--model', type=Path, default=ROOT / 'artifacts/forecasting/forecast_model_bundle.joblib')
    args = parser.parse_args()
    store = EventStore(args.store)
    try:
        records, metadata = fetch_acled(args.coverage_end, return_metadata=True)
        store.publish(records, args.coverage_end, **metadata)
        result = generate(store, args.model)
        store.attempt('ok')
        print(f"Forecast saved: {result['origin']} through {result['end_exclusive']} (exclusive); 47 counties")
    except Exception as error:
        store.attempt('failed')
        print(f'Update failed: {error}', file=sys.stderr)
        sys.exit(1)
