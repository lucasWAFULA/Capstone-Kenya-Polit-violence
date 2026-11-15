"""Build a dated historical demonstration from actual held-out predictions."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT / 'artifacts/forecasting'
summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
predictions = pd.read_csv(directory / 'test_predictions.csv')
panel = pd.read_csv(directory / 'county_week_dataset.csv')
origin = predictions.origin.max()
latest = predictions.loc[predictions.origin.eq(origin)]
context = panel.loc[panel.origin.eq(origin)].set_index('county')
records = []
for row in latest.itertuples():
    history = predictions.loc[predictions.county.eq(row.county)].tail(12)
    records.append({'county':row.county, 'probability':row.probability,
        'events_30d':int(context.loc[row.county, 'events_30d']),
        'high_30d':int(context.loc[row.county, 'high_30d']),
        'trend':history[['origin','probability']].to_dict('records')})
payload = {'mode':'historical_demo', 'origin':origin,
    'end_exclusive':latest.label_end_exclusive.iloc[0], 'generated_at':None,
    'snapshot':{'id':None,'source':'historical_export','coverage_end':summary['coverage_end'], 'collected_at':None},
    'history_cutoff_exclusive':str((pd.Timestamp(origin) - pd.Timedelta(days=7)).date()),
    'reporting_delay_days':7, 'threshold':summary['threshold'],
    'model_name':summary['selected_model'], 'model_status':'Retrospective research model; not operationally validated',
    'test_metrics':summary['test_metrics'], 'counties':records}
# This is a forecast origin, not a claimed real-time historical publication date.
(directory / 'dashboard_demo.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')

boundaries_path = ROOT / 'src/severity_service/static/kenya-counties.geojson'
boundaries = json.loads(boundaries_path.read_text(encoding='utf-8'))
aliases = {'Elgeyo-Marakwet':'Elgeyo Marakwet', "Murang'a":'Muranga', 'Tharaka':'Tharaka-Nithi'}
for feature in boundaries['features']:
    name = feature['properties'].get('shapeName') or feature['properties']['county']
    feature['properties'] = {'county':aliases.get(name, name)}
def rounded(value):
    return [rounded(item) for item in value] if isinstance(value,list) else round(value,5)
for feature in boundaries['features']:
    feature['geometry']['coordinates'] = rounded(feature['geometry']['coordinates'])
expected = set(latest.county)
assert len(boundaries['features']) == 47
assert {f['properties']['county'] for f in boundaries['features']} == expected
boundaries_path.write_text(json.dumps(boundaries, separators=(',',':')), encoding='utf-8')
print('Prepared 47-county historical demo and verified map joins')
