"""HTTP request and response schemas."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class EventFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_date: date
    disorder_type: str
    event_type: str
    sub_event_type: str
    admin1: str
    admin2: str
    inter1: int
    interaction: int
    civilian_targeting: str | None = None
    county_events_previous_30_days: NonNegative
    county_events_previous_90_days: NonNegative
    violent_events_previous_30_days: NonNegative
    previous_high_severity_events_in_county: NonNegative
    days_since_previous_event_in_county: NonNegative
    actor_previous_event_count: NonNegative


class Prediction(BaseModel):
    request_id: str
    severity: str
    probabilities: dict[str, float]
    model_name: str
    model_version: str


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: Annotated[list[EventFeatures], Field(min_length=1, max_length=1000)]
