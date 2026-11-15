"""Serve build metadata and bounded aggregate time series; private masters stay local."""
import json
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
