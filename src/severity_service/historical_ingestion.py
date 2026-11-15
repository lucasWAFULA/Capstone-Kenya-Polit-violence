"""Archive all available API fields before cleaning; never train or forecast here."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pandas as pd

from .forecasting import COUNTIES
from .ingestion import API_URL, ALIASES, FIELDS, access_token, active_restrictions, request_json, utcnow


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def restriction_signature(value):
    # A rolling recency cutoff timestamp can advance between pages without an entitlement change.
    if isinstance(value,dict):
        return {key:restriction_signature(item) for key,item in value.items() if key != 'timestamp'}
    if isinstance(value,list):
        return [restriction_signature(item) for item in value]
    return value


def compare_original(clean, original):
    if original is None or not Path(original).exists():
        return {'available':False}
    old = pd.read_csv(original, low_memory=False)
    old_ids, new_ids = set(old.event_id_cnty), set(clean.event_id_cnty)
    old_projection = old[FIELDS].drop_duplicates()
    old_projection.admin1 = old_projection.admin1.replace(ALIASES)
    old_projection.event_date = pd.to_datetime(old_projection.event_date).dt.strftime('%Y-%m-%d')
    old_projection.fatalities = pd.to_numeric(old_projection.fatalities)
    conflicts = old_projection.event_id_cnty.duplicated(keep=False)
    comparable = old_projection.loc[~conflicts].merge(clean[FIELDS], on='event_id_cnty', suffixes=('_old','_new'))
    differences = pd.DataFrame({col:comparable[f'{col}_old'].ne(comparable[f'{col}_new']) for col in FIELDS[1:]})
    return {'available':True, 'original_rows':len(old), 'original_unique_events':len(old_ids),
            'new_unique_events':len(new_ids), 'added_event_ids':len(new_ids-old_ids),
            'original_ids_not_in_api':len(old_ids-new_ids), 'comparable_common_events':len(comparable),
            'changed_common_events':int(differences.any(axis=1).sum()),
            'changed_fields':{col:int(differences[col].sum()) for col in differences},
            'note':'Differences in a current snapshot do not reconstruct historic revision times.'}


def clean_and_report(raw, *, restrictions, original=None):
    if not set(FIELDS).issubset(raw):
        raise ValueError('Required forecasting fields missing from raw export')
    clean = raw.copy()
    if 'country' not in clean or not clean.country.eq('Kenya').all():
        raise ValueError('Non-Kenya or missing country records')
    for column in clean.select_dtypes(include=['object','string']).columns:
        clean[column] = clean[column].map(lambda value: value.strip() if isinstance(value,str) else value)
        clean[column] = clean[column].replace('', pd.NA)
    clean.admin1 = clean.admin1.replace(ALIASES)
    dates = pd.to_datetime(clean.event_date, errors='coerce')
    fatalities = pd.to_numeric(clean.fatalities, errors='coerce')
    if clean[FIELDS].isna().any().any() or dates.isna().any() or not fatalities.ge(0).all() or not fatalities.mod(1).eq(0).all():
        raise ValueError('Invalid required values; raw archive preserved for review')
    clean.event_date = dates.dt.strftime('%Y-%m-%d')
    clean.fatalities = fatalities.astype('int64')
    unknown = sorted(set(clean.admin1)-set(COUNTIES))
    if unknown:
        raise ValueError('Unknown counties; reconcile aliases before publishing the master dataset')
    exact_duplicates = int(clean.duplicated().sum())
    clean = clean.drop_duplicates()
    if clean.event_id_cnty.duplicated().any():
        raise ValueError('Duplicate dyadic event IDs; raw archive preserved for review')
    clean = clean.sort_values(['event_date','event_id_cnty']).reset_index(drop=True)
    clean['severity'] = clean.fatalities.map(lambda n:'Low' if n == 0 else 'Moderate' if n <= 2 else 'High')
    # This is the installation's receipt time, not historic first publication.
    clean['observed_in_snapshot_at'] = utcnow()
    report = {'total_records_retrieved':len(raw), 'raw_shape':list(raw.shape), 'clean_shape':list(clean.shape),
        'earliest_event_date':clean.event_date.min(), 'latest_event_date':clean.event_date.max(),
        'unique_counties':int(clean.admin1.nunique()), 'missing_counties':sorted(set(COUNTIES)-set(clean.admin1)),
        'exact_duplicates_removed':exact_duplicates, 'access_restrictions':restrictions,
        'eligible_for_current_forecasts':False,
        'current_forecast_note':'Historical extraction only; no forecasts generated. Access restrictions and freshness require separate checks.',
        'county_distribution':{str(k):int(v) for k,v in clean.admin1.value_counts().items()},
        'event_types':{str(k):int(v) for k,v in clean.event_type.value_counts().items()},
        'missing_values_raw':{str(k):int(v) for k,v in raw.isna().sum().sort_values(ascending=False).items()},
        'missing_values_clean':{str(k):int(v) for k,v in clean.isna().sum().sort_values(ascending=False).items()},
        'severity_counts':{str(k):int(v) for k,v in clean.severity.value_counts().items()},
        'original_comparison':compare_original(clean, original),
        'availability_note':'API timestamp is last upload, not historical first-seen time. Original raw page JSON is preserved unchanged.'}
    return clean, report


def extract_history(output_root, *, client=None, original=None, progress=print):
    root = Path(output_root)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    raw_dir, processed_dir = root/'raw'/run_id, root/'processed'/run_id
    raw_dir.mkdir(parents=True, exist_ok=False)
    manifest = {'run_id':run_id, 'status':'incomplete', 'started_at':utcnow(), 'api_url':API_URL,
                'query':{'country':'Kenya','export_type':'dyadic','inter_num':1,'limit':5000,'with_total':'true','_format':'json'},
                'pages':[], 'notes':'Read-only historical extraction. No model fitting or current forecasting.'}
    write_json(raw_dir/'manifest.json', manifest)
    owned = client is None
    client = client or httpx.Client(timeout=120, follow_redirects=False)
    try:
        token = access_token(client)
        records, cursors, cursor, expected, restrictions = [], {'0'}, '0', None, None
        for page in range(1,1001):
            payload = request_json(client, 'GET', API_URL, headers={'Authorization':f'Bearer {token}'},
                                   params={**manifest['query'], 'cursor':cursor})
            # Save the original response before any parsing, cleaning, or deduplication.
            page_path = raw_dir/f'page-{page:04d}.json'
            with page_path.open('x',encoding='utf-8') as stream:
                json.dump(payload, stream, ensure_ascii=False)
            manifest['pages'].append({'file':page_path.name,
                                     'sha256':hashlib.sha256(page_path.read_bytes()).hexdigest()})
            write_json(raw_dir/'manifest.json', manifest)
            if payload.get('success') is not True or not isinstance(payload.get('data'),list):
                raise ValueError('API query unsuccessful; no master dataset published')
            if 'next_cursor' not in payload or payload.get('total_count') is None:
                raise ValueError('Missing cursor or total_count; extraction completeness cannot be verified')
            active = active_restrictions(payload.get('data_query_restrictions')) or {}
            total = int(payload['total_count'])
            if expected is not None and (total != expected or restriction_signature(active) != restriction_signature(restrictions)):
                raise ValueError('Source totals or access changed mid-extraction; rerun the snapshot')
            expected, restrictions = total, active
            records.extend(payload['data'])
            progress(f'Retrieved {len(payload["data"])} records | Total: {len(records)} / {expected}')
            following = payload['next_cursor']
            if following is None:
                if len(records) != expected or not records:
                    raise ValueError('Incomplete or empty extraction; no master dataset published')
                break
            cursor = str(following)
            if cursor in cursors or not payload['data']:
                raise ValueError('Repeated/stalled cursor; no master dataset published')
            cursors.add(cursor)
        else:
            raise ValueError('Pagination safety limit reached')
        raw = pd.DataFrame(records)
        raw.to_csv(raw_dir/'kenya_acled_raw.csv', index=False)
        raw.to_parquet(raw_dir/'kenya_acled_raw.parquet', index=False)
        clean, report = clean_and_report(raw, restrictions=restrictions, original=original)
        processed_dir.mkdir(parents=True, exist_ok=False)
        clean.to_csv(processed_dir/'kenya_acled_master.csv',index=False)
        clean.to_parquet(processed_dir/'kenya_acled_master.parquet',index=False)
        report.update(run_id=run_id, completed_at=utcnow(), raw_directory=str(raw_dir.resolve()),
                      processed_directory=str(processed_dir.resolve()))
        write_json(processed_dir/'quality_report.json',report)
        manifest.update(status='complete', completed_at=report['completed_at'],total_records=len(raw),
                        access_restrictions=restrictions)
        write_json(raw_dir/'manifest.json',manifest)
        # One atomic pointer publishes a matching raw/master/report set; older runs remain intact.
        pointer = root/('latest-' + run_id + '.tmp')
        write_json(pointer,{'run_id':run_id,'raw_directory':str(raw_dir.resolve()),
                            'processed_directory':str(processed_dir.resolve())})
        os.replace(pointer,root/'latest.json')
        return report
    except Exception:
        manifest.update(status='failed', finished_at=utcnow())
        write_json(raw_dir/'manifest.json',manifest)
        raise
    finally:
        if owned:
            client.close()
