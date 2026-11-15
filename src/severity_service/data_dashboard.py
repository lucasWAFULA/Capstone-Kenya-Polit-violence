"""Serve build metadata and bounded aggregate time series; private masters stay local."""
import json
from datetime import date,timedelta
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=4)
def read_json(path, modified):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read(path):
    return read_json(str(path),path.stat().st_mtime_ns)


def daily_state(root):
    root=Path(root)
    pointer=root/'data/daily/latest.json'
    if pointer.exists():
        metadata=read(pointer)
        directory=Path(metadata['directory'])
        payload=read(directory/'dashboard.json')
        summary=dict(payload['summary'],available=True,series_available=True)
        source=root/'data/latest.json'
        summary['matches_latest_extraction']=source.exists() and read(source)['run_id']==summary['source_run_id']
        return summary,payload
    public=root/'artifacts/data_quality/daily_summary.json'
    if public.exists():
        return dict(read(public),available=True,series_available=False,matches_latest_extraction=None),None
    return {'available':False,'series_available':False,'notice':'Build the daily county dataset to view coverage and activity.'},None


def county_activity(payload,days):
    summary=payload['summary']
    counties=[]
    for county,series in payload['counties'].items():
        rows=series[-days:]
        counties.append({'county':county,**{key:sum(row[key] for row in rows)
            for key in ['events','fatalities','high_political_violence_events']}})
    return {'mode':'recorded_activity','source_run_id':summary['source_run_id'],
            'start_date':str(date.fromisoformat(summary['end_date'])-timedelta(days=days-1)),
            'end_date':summary['end_date'],'days':days,'counties':counties,
            'access_restrictions':summary.get('access_restrictions',{}),
            'notice':'Actual recorded county totals from the historical API snapshot; not current forecasts.'}


def map_activity(root,days):
    root=Path(root)
    _,payload=daily_state(root)
    if payload is not None:
        return county_activity(payload,days)
    packaged=root/'artifacts/data_quality/county_activity.json'
    if packaged.exists():
        return read(packaged)['windows'][str(days)]
    return None
