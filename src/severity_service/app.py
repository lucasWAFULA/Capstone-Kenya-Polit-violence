"""FastAPI application serving the governed primary model with shadow scoring."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from .features import CLASS_ORDER, add_calendar_features
from .registry import ModelRegistry
from .schemas import BatchRequest, EventFeatures, Prediction

LOGGER = logging.getLogger("severity_service")
LOGGER.setLevel(logging.INFO)


def _probabilities(model, frame: pd.DataFrame) -> np.ndarray:
    raw = model.predict_proba(frame)
    classes = list(model.classes_)
    return np.column_stack([raw[:, classes.index(label)] for label in CLASS_ORDER])


def _score(app: FastAPI, events: list[EventFeatures]) -> list[Prediction]:
    registry: ModelRegistry = app.state.registry
    frame = add_calendar_features(pd.DataFrame([event.model_dump() for event in events]))
    # The training pipeline imputes numpy missing values, not Python None.
    frame = frame.fillna(np.nan)
    primary_prob = _probabilities(registry.primary, frame)
    challenger_prob = _probabilities(registry.challenger, frame)
    request_ids = [str(uuid4()) for _ in events]
    primary_labels = [CLASS_ORDER[index] for index in primary_prob.argmax(axis=1)]
    challenger_labels = [CLASS_ORDER[index] for index in challenger_prob.argmax(axis=1)]
    primary_meta = registry.manifest["models"]["primary"]
    challenger_meta = registry.manifest["models"]["challenger"]

    for index, request_id in enumerate(request_ids):
        LOGGER.info(json.dumps({
            "event": "shadow_prediction", "request_id": request_id,
            "primary_prediction": primary_labels[index],
            "challenger_prediction": challenger_labels[index],
            "models_agree": primary_labels[index] == challenger_labels[index],
            "primary_high_probability": float(primary_prob[index, 2]),
            "challenger_high_probability": float(challenger_prob[index, 2]),
            "challenger_model": challenger_meta["name"],
            "model_version": registry.manifest["version"],
        }, separators=(",", ":")))

    return [
        Prediction(
            request_id=request_ids[index], severity=primary_labels[index],
            probabilities={label: float(primary_prob[index, pos]) for pos, label in enumerate(CLASS_ORDER)},
            model_name=primary_meta["name"], model_version=registry.manifest["version"],
        )
        for index in range(len(events))
    ]


def create_app(registry: ModelRegistry | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.registry = registry or ModelRegistry.load(
            Path(os.getenv("MODEL_REGISTRY_DIR", str(Path(__file__).resolve().parents[2] / "artifacts/production")))
        )
        yield

    app = FastAPI(title="Kenya Event Severity API", version="1.0.0", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(Path(__file__).with_name("dashboard.html"))

    @app.middleware("http")
    async def timing(request: Request, call_next):
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time-Ms"] = f"{(perf_counter() - started) * 1000:.2f}"
        return response

    @app.get("/health/live")
    def liveness():
        return {"status": "ok"}

    @app.get("/health")
    @app.get("/health/ready")
    def readiness(request: Request):
        if not hasattr(request.app.state, "registry"):
            raise HTTPException(status_code=503, detail="models not loaded")
        return {"status": "ready", "model_version": request.app.state.registry.manifest["version"]}

    @app.post("/predict", response_model=Prediction)
    @app.post("/v1/predict", response_model=Prediction)
    def predict(event: EventFeatures, request: Request):
        return _score(request.app, [event])[0]

    @app.post("/v1/predict/batch", response_model=list[Prediction])
    def predict_batch(payload: BatchRequest, request: Request):
        return _score(request.app, payload.events)

    return app


app = create_app()
