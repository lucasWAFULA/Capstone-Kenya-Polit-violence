import pandas as pd
import pytest

from severity_service.daily_panel import COUNT_COLUMNS,county_daily


def events():
    return pd.DataFrame([
        {'event_id_cnty':'A','event_date':'2020-01-01','admin1':'Nairobi','fatalities':3,
         'event_type':'Battles','disorder_type':'Political violence'},
        {'event_id_cnty':'B','event_date':'2020-01-02','admin1':'Nairobi','fatalities':0,
         'event_type':'Strategic developments','disorder_type':'Strategic developments'},
        {'event_id_cnty':'C','event_date':'2020-01-08','admin1':'Nairobi','fatalities':4,
         'event_type':'Violence against civilians','disorder_type':'Political violence'},
        {'event_id_cnty':'D','event_date':'2020-04-10','admin1':'Nairobi','fatalities':0,
         'event_type':'Protests','disorder_type':'Demonstrations'}])


def test_full_47_county_calendar_and_zero_days():
    panel=county_daily(events())
    assert len(panel)==101*47
    assert panel.groupby('date').county.nunique().eq(47).all()
    assert panel.duplicated(['date','county']).sum()==0
    assert panel.events.sum()==4 and panel.fatalities.sum()==7
    assert panel.loc[panel.county.eq('Bomet'),COUNT_COLUMNS].eq(0).all().all()


def test_lagged_windows_do_not_include_today_or_future():
    panel=county_daily(events(),counties=['Nairobi']).set_index('date')
    assert pd.isna(panel.loc['2020-01-07','events_previous_7_days'])
    assert panel.loc['2020-01-08','events_previous_7_days']==1  # Strategic developments excluded.
    assert panel.loc['2020-01-09','events_previous_7_days']==1
    altered=events()
    altered.loc[altered.event_date.ge('2020-01-08'),'fatalities']=100
    changed=county_daily(altered,counties=['Nairobi']).set_index('date')
    columns=['events_previous_7_days','high_political_previous_30_days','days_since_previous_context_event']
    pd.testing.assert_frame_equal(panel.loc[:'2020-01-08',columns],changed.loc[:'2020-01-08',columns])


def test_next7_labels_boundaries_and_censoring():
    panel=county_daily(events(),counties=['Nairobi']).set_index('date')
    assert panel.loc['2020-01-01','high_political_events_next_7_days']==1  # Jan 8 excluded.
    assert panel.loc['2020-01-02','target_high_next_7_days']==1  # Jan 8 included.
    assert panel.loc['2020-04-04','target_high_next_7_days']==0
    assert panel.loc['2020-04-05':,'target_high_next_7_days'].isna().all()
    assert panel.target_window_complete.sum()==95
    assert panel.history_90d_complete.sum()==11


def test_rejects_conflicting_ids_and_unobserved_date_extension():
    with pytest.raises(ValueError,match='observed'):
        county_daily(events(),end='2020-04-11')
    duplicate=events().iloc[:1].copy()
    duplicate.fatalities=5
    with pytest.raises(ValueError,match='Conflicting'):
        county_daily(pd.concat([events(),duplicate]))
