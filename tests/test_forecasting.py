import pandas as pd
import pytest

from severity_service.forecasting import FEATURES, county_weeks, metrics


def events():
    return pd.DataFrame([
        {'event_id_cnty': str(i), 'event_date': day, 'admin1': 'Nairobi',
         'event_type': 'Battles', 'disorder_type': 'Political violence', 'fatalities': deaths}
        for i, (day, deaths) in enumerate([
            ('1999-01-01', 0), ('1999-12-26', 3), ('1999-12-27', 0),
            ('2000-01-03', 3), ('2000-01-09', 0), ('2000-01-10', 3)])])


def build(data):
    return county_weeks(data, coverage_end='2000-01-10', counties=['Nairobi', 'Bomet'])


def test_complete_calendar_strict_cutoff_and_full_horizons():
    frame = build(events()).set_index('county')
    assert len(frame) == 2  # January 10 origin is right-censored and excluded.
    assert frame.loc['Nairobi', 'events_7d'] == 1
    assert frame.loc['Nairobi', 'high_30d'] == 1
    assert frame.loc['Nairobi', 'target'] == 1
    assert frame.loc['Bomet', 'events_90d'] == 0
    assert frame.loc['Bomet', 'target'] == 0
    assert frame.loc['Bomet', 'no_previous_event'] == 1


def test_future_events_do_not_change_predictors():
    original = build(events())[FEATURES]
    altered = events()
    altered.loc[altered.event_date.ge('1999-12-27'), 'fatalities'] = 100
    pd.testing.assert_frame_equal(original, build(altered)[FEATURES])


def test_target_is_seven_calendar_days_and_political_violence_only():
    data = events()
    data.loc[data.event_date.eq('2000-01-03'), 'disorder_type'] = 'Demonstrations'
    assert build(data).target.sum() == 0  # January 10 belongs to the next horizon.


def test_duplicate_ids_and_unknown_counties_rejected():
    pd.testing.assert_frame_equal(build(events()), build(pd.concat([events(), events().iloc[:1]])))
    conflict = events().iloc[:1].copy()
    conflict['fatalities'] = 9
    with pytest.raises(ValueError, match='Duplicate'):
        build(pd.concat([events(), conflict]))
    data = events()
    data.loc[0, 'admin1'] = 'Unknown'
    with pytest.raises(ValueError, match='Unrecognised'):
        build(data)


def test_metrics_with_no_positive_labels():
    result = metrics([0, 0], [.1, .6])
    assert result['roc_auc'] is None
    assert result['pr_auc'] is None
    assert result['false_alarm_rate'] == .5
