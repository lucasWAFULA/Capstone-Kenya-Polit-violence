"""Generate fresh research forecasts and suppress stale review alerts."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd

from .forecasting import FEATURES, county_weeks
from .ingestion import EventStore, utcnow

NAIROBI = ZoneInfo('Africa/Nairobi')
ROOT = Path(__file__).resolve().parents[2]


def generate(store: EventStore, model_path, *, origin=None, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NAIROBI).date()
    origin = pd.Timestamp(origin or (today + timedelta(days=1))).date()
    if origin != today + timedelta(days=1):
        raise ValueError('New runs must target tomorrow; use saved snapshots for historical replay')
    snapshot, events = store.snapshot()
    collected = datetime.fromisoformat(snapshot['collected_at'])
    if snapshot['source'] != 'acled_api':
        raise ValueError('Only authenticated API snapshots can generate current research forecasts')
    if not timedelta(0) <= now - collected <= timedelta(days=8):
        raise ValueError('Snapshot is stale or future-dated; ingest a fresh complete release')
    if not snapshot.get('source_updated_at') or not timedelta(0) <= now - datetime.fromisoformat(snapshot['source_updated_at']) <= timedelta(days=8):
        raise ValueError('Source update is stale or unknown')
    if pd.Timestamp(snapshot['coverage_end']).date() > today:
        raise ValueError('Coverage end cannot be in the future')
    bundle = joblib.load(model_path)
    if bundle['features'] != FEATURES:
        raise ValueError('Forecast model feature contract mismatch')
    metadata = bundle['metadata']
    delay = metadata['reporting_delay_days']
    frame = county_weeks(events, coverage_end=snapshot['coverage_end'],
                         reporting_delay_days=delay, forecast_origin=origin)
    raw = np.clip(bundle['model'].predict_proba(frame[FEATURES])[:, 1], 1e-6, 1-1e-6)
    probability = bundle['calibrator'].predict_proba(np.log(raw / (1-raw)).reshape(-1,1))[:,1]
    if not np.isfinite(probability).all() or not ((probability >= 0) & (probability <= 1)).all():
        raise ValueError('Invalid forecast probabilities')
    records = []
    for i, row in frame.reset_index(drop=True).iterrows():
        records.append({'county':row['county'], 'probability':float(probability[i]),
                        'events_30d':int(row['events_30d']), 'high_30d':int(row['high_30d'])})
    payload = {'mode':'current_research', 'generated_at':now.isoformat(), 'origin':str(origin),
        'end_exclusive':str(origin + timedelta(days=7)), 'snapshot':snapshot,
        'history_cutoff_exclusive':str(origin - timedelta(days=delay)),
        'reporting_delay_days':delay, 'threshold':metadata['threshold'],
        'model_name':metadata['selected_model'], 'model_status':'Research model; not operationally validated',
        'test_metrics':metadata['test_metrics'], 'counties':records}
    store.save_forecast(payload)
    return payload


def dashboard_state(store=None, *, now=None, demo_path=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NAIROBI).date()
    payload = store.latest_forecast() if store else None
    attempt = store.last_attempt() if store else None
    if payload is None:
        path = Path(demo_path or ROOT / 'artifacts/forecasting/dashboard_demo.json')
        if not path.exists():
            return {'mode':'unavailable', 'fresh':False, 'alerts':[], 'counties':[],
                    'notice':'No forecasts yet. Configure ACLED access and run the ingestion job.',
                    'last_attempt':attempt}
        payload = json.loads(path.read_text(encoding='utf-8'))
    current = payload['mode'] == 'current_research'
    origin = pd.Timestamp(payload['origin']).date()
    end = pd.Timestamp(payload['end_exclusive']).date()
    fresh = (current and origin <= today + timedelta(days=1) and today < end
             and origin >= today - timedelta(days=6)
             and timedelta(0) <= now - datetime.fromisoformat(payload['snapshot']['collected_at']) <= timedelta(days=8)
             and bool(payload['snapshot'].get('source_updated_at'))
             and timedelta(0) <= now - datetime.fromisoformat(payload['snapshot']['source_updated_at']) <= timedelta(days=8))
    if current and attempt and attempt['outcome'] == 'failed' and attempt['finished_at'] >= payload['generated_at']:
        fresh = False
    payload['fresh'] = fresh
    payload['last_attempt'] = attempt
    payload['alerts'] = [dict(row, message='Review contextual information; probabilistic research signal')
                         for row in payload['counties'] if row['probability'] >= payload['threshold']] if fresh else []
    payload['notice'] = ('Fresh input data · research review signals only; high false-alert rate in evaluation.'
                         if fresh else 'Historical or stale results · current review alerts are suppressed. Run a successful fresh ingestion to update.')
    payload['counties'] = sorted(payload['counties'], key=lambda r: r['probability'], reverse=True)
    if current and store:
        history = store.forecast_history()
        for county in payload['counties']:
            county['trend'] = [{'origin':run['origin'], 'probability':row['probability']}
                for run in history for row in run['counties'] if row['county'] == county['county']]
    return payload
