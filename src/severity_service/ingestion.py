"""Authenticated ACLED snapshots with transactional publication and version history."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

from .forecasting import COUNTIES

FIELDS = ['event_id_cnty', 'event_date', 'admin1', 'fatalities', 'disorder_type', 'event_type']
TOKEN_URL = 'https://acleddata.com/oauth/token'
API_URL = 'https://acleddata.com/api/acled/read'
ALIASES = {'Elgeyo-Marakwet': 'Elgeyo Marakwet', "Murang'a": 'Muranga',
           'Murang’a': 'Muranga', 'Tharaka Nithi': 'Tharaka-Nithi', 'Taita-Taveta': 'Taita Taveta'}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def normalise(records, coverage_end):
    if not records:
        raise ValueError('Empty snapshots cannot replace the active data')
    data = pd.DataFrame(records)
    if not set(FIELDS).issubset(data):
        raise ValueError('ACLED response is missing required fields')
    if 'country' in data and not data.country.eq('Kenya').all():
        raise ValueError('Response contains records outside Kenya')
    data = data[FIELDS].copy()
    if data.isna().any().any():
        raise ValueError('Missing required event fields')
    data.admin1 = data.admin1.replace(ALIASES)
    if set(data.admin1) - set(COUNTIES):
        raise ValueError('Unmapped county names in source; snapshot rejected')
    dates = pd.to_datetime(data.event_date, errors='raise')
    if (dates > pd.Timestamp(coverage_end)).any():
        raise ValueError('Source records exceed the declared coverage end')
    if dates.min() > pd.Timestamp('2000-01-01'):
        raise ValueError('Full-history snapshot required; recent-only access is insufficient')
    data.event_date = dates.dt.strftime('%Y-%m-%d')
    data.fatalities = pd.to_numeric(data.fatalities, errors='raise')
    if not data.fatalities.ge(0).all() or not data.fatalities.mod(1).eq(0).all():
        raise ValueError('Fatalities must be finite nonnegative integers')
    data.fatalities = data.fatalities.astype(int)
    data = data.drop_duplicates()
    if data.event_id_cnty.duplicated().any():
        raise ValueError('Conflicting versions of an event in one snapshot')
    return data.to_dict('records')


def request_json(client, method, url, **kwargs):
    for attempt in range(3):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            if attempt == 2:
                # Never echo credentials, tokens, source bodies, or request headers.
                raise RuntimeError('ACLED request failed; check connectivity and account access') from None
    raise RuntimeError('ACLED request failed')


def active_restrictions(value):
    """Empty restriction buckets are metadata, not access limitations."""
    if isinstance(value, dict):
        return {key: item for key, raw in value.items() if (item := active_restrictions(raw))}
    if isinstance(value, list):
        return [item for raw in value if (item := active_restrictions(raw))]
    return value if value not in (None, '', False) else None


def access_token(client):
    token = os.getenv('ACLED_ACCESS_TOKEN')
    if token:
        return token
    username, password = os.getenv('ACLED_USERNAME'), os.getenv('ACLED_PASSWORD')
    if not username or not password:
        raise RuntimeError('Set ACLED_USERNAME and ACLED_PASSWORD, or ACLED_ACCESS_TOKEN locally')
    token = request_json(client, 'POST', TOKEN_URL, data={
        'username':username, 'password':password, 'grant_type':'password',
        'client_id':'acled', 'scope':'authenticated'}).get('access_token')
    if not token:
        raise RuntimeError('ACLED authentication returned no access token')
    return token


def fetch_acled(coverage_end, *, client=None, return_metadata=False):
    """Cursor pagination, dyadic events; partial/restricted downloads fail closed."""
    owned = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=False)
    try:
        token = access_token(client)
        records, cursors, cursor, expected = [], set(), '0', None
        for _ in range(1000):
            payload = request_json(client, 'GET', API_URL,
                headers={'Authorization': f'Bearer {token}'}, params={
                    '_format': 'json', 'country': 'Kenya', 'export_type': 'dyadic',
                    'event_date': str(coverage_end), 'event_date_where': '<=',
                    'limit': 5000, 'cursor': cursor, 'with_total': 'true'})
            if payload.get('success') is not True or not isinstance(payload.get('data'), list):
                raise RuntimeError('ACLED response did not confirm a successful data query')
            if active_restrictions(payload.get('data_query_restrictions')):
                raise RuntimeError('ACLED reports query restrictions; confirm full Kenya/history/recency access')
            age = payload.get('last_update')
            if age is None or not 0 <= float(age) <= 8 * 24:
                raise RuntimeError('Source update age is unknown or exceeds eight days')
            if 'next_cursor' not in payload or payload.get('total_count') is None:
                raise RuntimeError('Pagination completeness metadata missing')
            total = int(payload['total_count'])
            if expected is not None and total != expected:
                raise RuntimeError('Source changed during pagination; retry the complete snapshot')
            expected = total
            records.extend(payload['data'])
            next_cursor = payload['next_cursor']
            if next_cursor is None:
                if len(records) != expected:
                    raise RuntimeError('Partial snapshot rejected: total count mismatch')
                result = normalise(records, coverage_end)
                metadata = {'source_updated_at': (datetime.now(timezone.utc) - timedelta(hours=float(age))).isoformat()}
                return (result, metadata) if return_metadata else result
            cursor = str(next_cursor)
            if cursor in cursors or not payload['data']:
                raise RuntimeError('Pagination cursor stalled; no snapshot published')
            cursors.add(cursor)
        raise RuntimeError('Pagination safety limit reached')
    finally:
        if owned:
            client.close()


class EventStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS snapshots (
                  id INTEGER PRIMARY KEY, collected_at TEXT NOT NULL,
                  coverage_end TEXT NOT NULL, source TEXT NOT NULL, event_count INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS first_seen (
                  event_id TEXT PRIMARY KEY, first_seen_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS versions (
                  snapshot_id INTEGER, event_id TEXT, payload TEXT NOT NULL,
                  PRIMARY KEY(snapshot_id,event_id));
                CREATE TABLE IF NOT EXISTS forecasts (
                  id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, origin TEXT NOT NULL,
                  snapshot_id INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (
                  id INTEGER PRIMARY KEY, finished_at TEXT NOT NULL, outcome TEXT NOT NULL);
            ''')
            if 'source_updated_at' not in {row[1] for row in db.execute('PRAGMA table_info(snapshots)')}:
                db.execute('ALTER TABLE snapshots ADD COLUMN source_updated_at TEXT')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def publish(self, records, coverage_end, source='acled_api', collected_at=None, source_updated_at=None):
        records = normalise(records, coverage_end)
        collected = collected_at or utcnow()
        with self.connect() as db:
            cursor = db.execute('INSERT INTO snapshots(collected_at,coverage_end,source,event_count,source_updated_at) VALUES(?,?,?,?,?)',
                                (collected, str(coverage_end), source, len(records), source_updated_at))
            snapshot_id = cursor.lastrowid
            db.executemany('INSERT OR IGNORE INTO first_seen VALUES(?,?)',
                           [(r['event_id_cnty'], collected) for r in records])
            db.executemany('INSERT INTO versions VALUES(?,?,?)',
                           [(snapshot_id, r['event_id_cnty'], json.dumps(r, sort_keys=True)) for r in records])
        return snapshot_id

    def snapshot(self, snapshot_id=None):
        with self.connect() as db:
            row = db.execute('SELECT * FROM snapshots WHERE id=?', (snapshot_id,)).fetchone() if snapshot_id else db.execute(
                'SELECT * FROM snapshots ORDER BY id DESC LIMIT 1').fetchone()
            if row is None:
                raise ValueError('No ingested snapshot available')
            records = [json.loads(r['payload']) for r in db.execute(
                'SELECT payload FROM versions WHERE snapshot_id=?', (row['id'],))]
        return dict(row), pd.DataFrame(records)

    def save_forecast(self, payload):
        with self.connect() as db:
            db.execute('INSERT INTO forecasts(created_at,origin,snapshot_id,payload) VALUES(?,?,?,?)',
                       (payload['generated_at'], payload['origin'], payload['snapshot']['id'], json.dumps(payload)))

    def latest_forecast(self):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM forecasts ORDER BY id DESC LIMIT 1').fetchone()
        return json.loads(row['payload']) if row else None

    def attempt(self, outcome):
        with self.connect() as db:
            db.execute('INSERT INTO attempts(finished_at,outcome) VALUES(?,?)', (utcnow(), outcome))

    def last_attempt(self):
        with self.connect() as db:
            row = db.execute('SELECT finished_at,outcome FROM attempts ORDER BY id DESC LIMIT 1').fetchone()
        return dict(row) if row else None

    def forecast_history(self):
        with self.connect() as db:
            rows = db.execute('''SELECT payload FROM forecasts WHERE id IN
                (SELECT MAX(id) FROM forecasts GROUP BY origin) ORDER BY origin DESC LIMIT 12''').fetchall()
        return [json.loads(row['payload']) for row in reversed(rows)]
