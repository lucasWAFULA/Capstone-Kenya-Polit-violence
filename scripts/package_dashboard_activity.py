"""Package bounded daily aggregates from a verified panel, without raw incident records."""
import argparse
import json
from pathlib import Path


def package(source_root: Path, output: Path):
    pointer = json.loads((source_root / 'data/daily/latest.json').read_text(encoding='utf-8'))
    payload = json.loads((Path(pointer['directory']) / 'dashboard.json').read_text(encoding='utf-8'))
    summary = json.loads((output / 'daily_summary.json').read_text(encoding='utf-8'))
    if payload['summary']['source_run_id'] != summary['source_run_id']:
        raise ValueError('Daily series and packaged summary must come from the same source run')
    if set(payload['counties']) != set(summary['county_names']):
        raise ValueError('County coverage does not match the packaged summary')
    keys = ('date', 'events', 'fatalities', 'high_political_violence_events')
    def bounded(rows):
        return [{key: row[key] for key in keys} for row in rows[-365:]]
    result = {'summary': summary, 'national': bounded(payload['national']),
              'counties': {county: bounded(rows) for county, rows in payload['counties'].items()}}
    (output / 'daily_activity.json').write_text(json.dumps(result, separators=(',', ':')), encoding='utf-8')
    print('Packaged verified 365-day national and 47-county aggregate series; no incident records.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'artifacts/data_quality')
    args = parser.parse_args()
    package(args.source_root, args.output)
