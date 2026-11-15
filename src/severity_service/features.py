"""Shared feature contract used by training and online inference."""

from __future__ import annotations

import pandas as pd

CLASS_ORDER = ["Low", "Moderate", "High"]
CATEGORICAL_FEATURES = [
    "disorder_type", "event_type", "sub_event_type", "admin1", "admin2",
    "inter1", "interaction", "civilian_targeting", "day_of_week",
]
HISTORY_FEATURES = [
    "county_events_previous_30_days",
    "county_events_previous_90_days",
    "violent_events_previous_30_days",
    "previous_high_severity_events_in_county",
    "days_since_previous_event_in_county",
    "actor_previous_event_count",
]
NUMERIC_FEATURES = ["year", "month", "quarter", *HISTORY_FEATURES]
FEATURE_COLUMNS = [*CATEGORICAL_FEATURES, *NUMERIC_FEATURES]


def add_calendar_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert event_date into the calendar fields expected by both models."""
    result = frame.copy()
    dates = pd.to_datetime(result.pop("event_date"), errors="raise")
    result["year"] = dates.dt.year
    result["month"] = dates.dt.month
    result["quarter"] = dates.dt.quarter
    result["day_of_week"] = dates.dt.day_name()
    return result[FEATURE_COLUMNS]
