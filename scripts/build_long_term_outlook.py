"""Reproduce the separate 2026–2030 annual count outlook from a verified daily panel."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from severity_service.outlook import build_outlook
from severity_service.forecasting import COUNTIES


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, help='Workspace containing the verified local daily panel')
    parser.add_argument('--annual-input', type=Path, help='Previously packaged annual_history.json, for data-free reproduction')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/outlook')
    args = parser.parse_args()
    if bool(args.source_root) == bool(args.annual_input):
        parser.error('Choose --source-root or --annual-input')
    if args.source_root:
        pointer = json.loads((args.source_root / 'data/daily/latest.json').read_text(encoding='utf-8'))
        directory = Path(pointer['directory'])
        summary = json.loads((directory / 'quality_report.json').read_text(encoding='utf-8'))
        frame = pd.read_parquet(directory / 'county_daily.parquet', columns=['date', 'county', 'high_political_violence_events'])
        frame['date'] = pd.to_datetime(frame['date'])
        coverage = pd.Timestamp(summary['end_date'])
        last_complete = coverage.year if coverage.month == 12 and coverage.day == 31 else coverage.year - 1
        frame['year'] = frame.date.dt.year
        frame = frame.loc[frame.year.between(2000, last_complete)]
        for year, group in frame.groupby('year'):
            expected_days = 366 if pd.Timestamp(year=year, month=12, day=31).is_leap_year else 365
            if len(group) != expected_days * 47 or group.duplicated(['county', 'date']).any() or set(group.county) != set(COUNTIES):
                raise ValueError(f'Incomplete county calendar in {year}')
        annual = frame.pivot_table(index='year', columns='county', values='high_political_violence_events', aggfunc='sum').astype(int)
        package = {'source': {'coverage_end': summary['end_date'], 'source_run_id': summary['source_run_id'],
                              'aggregation': 'Complete calendar-year counts from the verified daily panel'},
                   'years': annual.index.tolist(), 'counties': {c: annual[c].tolist() for c in annual}}
    else:
        package = json.loads(args.annual_input.read_text(encoding='utf-8'))
        annual = pd.DataFrame(package['counties'], index=package['years'])
        if set(annual) != set(COUNTIES):
            raise ValueError('Annual input must cover all 47 counties')
    encoded = json.dumps(package, sort_keys=True, separators=(',', ':')).encode()
    source = dict(package['source'], annual_input_sha256=hashlib.sha256(encoded).hexdigest())
    result = build_outlook(annual, source=source)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'annual_history.json').write_text(json.dumps(package, indent=2), encoding='utf-8')
    (args.output / 'outlook.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('start_year', 'end_year', 'training_end_year', 'selected_model', 'validation_scores', 'test_metrics')}, indent=2))
