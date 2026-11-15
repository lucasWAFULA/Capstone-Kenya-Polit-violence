"""Complete observed county calendars, strictly lagged features, and censored labels."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from .forecasting import COUNTIES, VIOLENT_TYPES
from .ingestion import ALIASES, FIELDS

COUNT_COLUMNS = ['events', 'context_events', 'fatalities', 'violent_events',
                 'high_severity_events', 'high_political_violence_events']


def county_daily(events, *, start=None, end=None, counties=COUNTIES):
    data = events[FIELDS].copy()
    if data.isna().any().any():
        raise ValueError('Required event fields contain missing values')
    data['event_date'] = pd.to_datetime(data.event_date, errors='raise').dt.normalize()
    data['admin1'] = data.admin1.replace(ALIASES)
    data['fatalities'] = pd.to_numeric(data.fatalities, errors='raise')
    if not data.fatalities.ge(0).all() or not data.fatalities.mod(1).eq(0).all():
        raise ValueError('Fatalities must be finite nonnegative integers')
    data = data.drop_duplicates()
    if data.event_id_cnty.duplicated().any():
        raise ValueError('Conflicting event IDs cannot be aggregated')
    if set(data.admin1) - set(counties) or len(set(counties)) != len(counties):
        raise ValueError('County contract mismatch')
    if data.empty:
        raise ValueError('No events available')
    start = pd.Timestamp(start or data.event_date.min()).normalize()
    end = pd.Timestamp(end or data.event_date.max()).normalize()
    if start < data.event_date.min() or end > data.event_date.max() or start > end:
        raise ValueError('Panel range must stay within the observed national date bounds')
    data = data.loc[data.event_date.between(start,end)].copy()
    data['context'] = data.disorder_type.ne('Strategic developments').astype(int)
    data['violent'] = data.event_type.isin(VIOLENT_TYPES).astype(int)
    data['high'] = data.fatalities.ge(3).astype(int)
    data['high_political'] = (data.high.eq(1) & data.violent.eq(1)
                            & data.disorder_type.str.contains('Political violence',regex=False)).astype(int)
    grouped = data.groupby(['admin1','event_date']).agg(
        events=('event_id_cnty','size'),context_events=('context','sum'),fatalities=('fatalities','sum'),
        violent_events=('violent','sum'),high_severity_events=('high','sum'),
        high_political_violence_events=('high_political','sum'))
    calendar = pd.date_range(start,end,freq='D')
    rows = []
    for county in counties:
        if county in grouped.index.get_level_values(0):
            daily = grouped.loc[county].reindex(calendar,fill_value=0).astype('int64')
        else:
            daily = pd.DataFrame(0,index=calendar,columns=COUNT_COLUMNS,dtype='int64')
        daily.index.name = 'date'
        daily['county'] = county
        daily['is_zero_record_day'] = daily.events.eq(0)
        for column, window, name in [('context_events',7,'events_previous_7_days'),
            ('context_events',30,'events_previous_30_days'),('context_events',90,'events_previous_90_days'),
            ('high_political_violence_events',30,'high_political_previous_30_days'),
            ('violent_events',90,'violent_previous_90_days')]:
            # NaN during the warm-up period means insufficient observed history, not zero.
            daily[name] = daily[column].shift(1).rolling(window,min_periods=window).sum().astype('Int64')
        daily['history_90d_complete'] = (calendar - start).days >= 90
        last = pd.Series(pd.NaT,index=calendar,dtype='datetime64[ns]')
        last.loc[daily.context_events.gt(0)] = calendar[daily.context_events.gt(0)]
        last = last.ffill().shift(1)
        daily['no_previous_context_event'] = last.isna()
        daily['days_since_previous_context_event'] = (calendar.to_series()-last).dt.days.astype('Int64')
        # Seven days beginning at this day's origin: [date, date+7).
        future = daily.high_political_violence_events.iloc[::-1].rolling(7,min_periods=7).sum().iloc[::-1]
        daily['target_window_complete'] = future.notna()
        daily['high_political_events_next_7_days'] = future.astype('Int64')
        daily['target_high_next_7_days'] = future.gt(0).astype('Int8').mask(future.isna())
        daily['month'] = calendar.month
        daily['quarter'] = calendar.quarter
        daily['day_of_week'] = calendar.day_of_week
        rows.append(daily.reset_index())
    panel = pd.concat(rows,ignore_index=True).sort_values(['date','county']).reset_index(drop=True)
    assert len(panel) == len(calendar)*len(counties)
    assert panel.events.sum() == len(data)
    assert panel.fatalities.sum() == data.fatalities.sum()
    return panel


def build_daily_dataset(root, *, output_root=None):
    root = Path(root)
    source = json.loads((root/'data/latest.json').read_text(encoding='utf-8'))
    source_dir = Path(source['processed_directory'])
    events = pd.read_parquet(source_dir/'kenya_acled_master.parquet')
    source_report = json.loads((source_dir/'quality_report.json').read_text(encoding='utf-8'))
    panel = county_daily(events)
    build_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
    output_root = Path(output_root or root/'data/daily')
    output = output_root/build_id
    output.mkdir(parents=True,exist_ok=False)
    panel.to_parquet(output/'county_daily.parquet',index=False)
    panel.to_csv(output/'county_daily.csv',index=False)
    report = {'build_id':build_id,'source_run_id':source['run_id'],
        'built_at':datetime.now(timezone.utc).isoformat(),
        'start_date':str(panel.date.min().date()),'end_date':str(panel.date.max().date()),
        'counties':len(COUNTIES),'county_names':COUNTIES,'calendar_days':int(panel.date.nunique()),'rows':len(panel),
        'columns':len(panel.columns),'source_events':int(panel.events.sum()),
        'zero_record_county_days':int(panel.is_zero_record_day.sum()),
        'labelled_rows':int(panel.target_window_complete.sum()),
        'censored_label_rows':int((~panel.target_window_complete).sum()),
        'positive_label_rows':int(panel.target_high_next_7_days.sum()),
        'warmup_90d_rows':int((~panel.history_90d_complete).sum()),
        'access_restrictions':source_report['access_restrictions'],
        'checks':{'unique_county_dates':not bool(panel.duplicated(['county','date']).any()),
                  '47_counties_every_day':bool(panel.groupby('date').county.nunique().eq(47).all()),
                  'event_counts_conserved':int(panel.events.sum())==len(events),
                  'fatalities_conserved':int(panel.fatalities.sum())==int(events.fatalities.sum()),
                  'zero_day_counts_zero':bool(panel.loc[panel.is_zero_record_day,COUNT_COLUMNS].eq(0).all().all())},
        'interpretation':'Zero rows mean no recorded event in this snapshot, not verified absence of violence.',
        'availability':'Incident-date panel from a retrospective snapshot; historic reporting/revision availability is not reconstructed.',
        'target_definition':'At least one political violence event with 3+ fatalities in [date, date+7); last six dates have unknown labels.',
        'history_definition':'Predictors exclude the observation day; incomplete initial windows remain null. Counts include all event types except Strategic developments for context.',
        'training_status':'No model trained or forecast refreshed from this panel.'}
    (output/'quality_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    # Compact local aggregate series for the API, never expose event records or local file paths.
    recent = panel.loc[panel.date.ge(panel.date.max()-pd.Timedelta(days=364)),['date','county','events','fatalities','high_political_violence_events']].copy()
    recent['date'] = recent.date.dt.strftime('%Y-%m-%d')
    series = {county:group.drop(columns='county').to_dict('records') for county,group in recent.groupby('county')}
    national = recent.groupby('date')[['events','fatalities','high_political_violence_events']].sum().reset_index().to_dict('records')
    dashboard = {'summary':report,'national':national,'counties':series}
    (output/'dashboard.json').write_text(json.dumps(dashboard,separators=(',',':')),encoding='utf-8')
    pointer = output_root/(build_id+'.tmp')
    pointer.write_text(json.dumps({'directory':str(output.resolve()),'build_id':build_id}),encoding='utf-8')
    pointer.replace(output_root/'latest.json')
    # Only aggregate build metadata is packaged; the panel and daily series stay private.
    public_dir = root/'artifacts/data_quality'
    public_dir.mkdir(parents=True,exist_ok=True)
    (public_dir/'daily_summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report, output
