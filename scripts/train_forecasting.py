"""Run the separate county-week research experiment."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from severity_service.forecasting import run_research

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=ROOT / 'ACLED_Kenya_1997-2025.csv')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/forecasting')
    parser.add_argument('--coverage-end', required=True, help='Last fully observed day, YYYY-MM-DD')
    parser.add_argument('--reporting-delay-days', type=int, default=7)
    args = parser.parse_args()
    print(json.dumps(run_research(args.data, args.output, coverage_end=args.coverage_end,
                                 reporting_delay_days=args.reporting_delay_days), indent=2))
