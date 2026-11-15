"""Inspect the latest complete historical extraction without exposing event narratives."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    pointer = json.loads((ROOT/'data/latest.json').read_text(encoding='utf-8'))
    processed = Path(pointer['processed_directory'])
    report = json.loads((processed/'quality_report.json').read_text(encoding='utf-8'))
    raw = pd.read_parquet(Path(pointer['raw_directory'])/'kenya_acled_raw.parquet')
    print('Total records:',report['total_records_retrieved'])
    print('Event dates:',report['earliest_event_date'],'through',report['latest_event_date'])
    print('Unique counties:',report['unique_counties'])
    print('Raw dataset shape:',raw.shape)
    print('Clean dataset shape:',tuple(report['clean_shape']))
    print('\nCounty distribution:')
    print(pd.Series(report['county_distribution']).head(15).to_string())
    print('\nEvent types:')
    print(pd.Series(report['event_types']).to_string())
    print('\nRaw missing values:')
    print(pd.Series(report['missing_values_raw']).head(15).to_string())
    print('\nStandardised missing values (including blank source strings):')
    print(pd.Series(report['missing_values_clean']).head(15).to_string())
    print('\nOriginal comparison:')
    print(json.dumps(report['original_comparison'],indent=2))
    print('\nAccount restrictions:')
    print(json.dumps(report['access_restrictions'],indent=2))
