"""Fetch and verify all Kenya records available to the configured account. No training."""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from severity_service.historical_ingestion import extract_history

if __name__ == '__main__':
    load_dotenv(ROOT/'.env')
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'data')
    parser.add_argument('--original',type=Path,default=ROOT/'ACLED_Kenya_1997-2025.csv')
    args=parser.parse_args()
    try:
        report=extract_history(args.output,original=args.original)
        print('\nExtraction completed successfully!')
        for key in ['total_records_retrieved','earliest_event_date','latest_event_date','unique_counties','raw_shape','clean_shape']:
            print(f'{key}: {report[key]}')
        print('Quality report:',Path(report['processed_directory'])/'quality_report.json')
        if report['access_restrictions']:
            print('Account restrictions recorded. This extraction does not enable current forecasts.')
    except Exception as error:
        print(f'Historical extraction failed ({type(error).__name__}). Raw pages are preserved; the last complete dataset is unchanged.',file=sys.stderr)
        sys.exit(1)
