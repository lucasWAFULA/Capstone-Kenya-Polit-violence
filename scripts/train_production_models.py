"""Train, evaluate, refit, and register the primary/challenger models."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, average_precision_score, f1_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler, label_binarize

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from severity_service.features import (  # noqa: E402
    CATEGORICAL_FEATURES, CLASS_ORDER, FEATURE_COLUMNS, HISTORY_FEATURES, NUMERIC_FEATURES,
)
from severity_service.xgb_adapter import LabelEncodedXGBClassifier  # noqa: E402

RANDOM_STATE = 42


def engineer_features(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    required = {
        "event_id_cnty", "event_date", "disorder_type", "event_type", "sub_event_type",
        "actor1", "inter1", "interaction", "civilian_targeting", "admin1", "admin2", "fatalities",
    }
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"Dataset is missing columns: {sorted(missing)}")
    frame = raw.drop_duplicates().copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce")
    frame["fatalities"] = pd.to_numeric(frame["fatalities"], errors="coerce")
    frame = frame.loc[
        frame["event_date"].notna() & frame["fatalities"].notna() & (frame["fatalities"] >= 0)
        & frame["disorder_type"].fillna("").ne("Strategic developments")
    ].sort_values(["event_date", "event_id_cnty"], kind="stable").reset_index(drop=True)
    frame["severity"] = pd.cut(
        frame["fatalities"], bins=[-np.inf, 0, 2, np.inf], labels=CLASS_ORDER, ordered=True,
    )
    frame["year"] = frame["event_date"].dt.year
    frame["month"] = frame["event_date"].dt.month
    frame["quarter"] = frame["event_date"].dt.quarter
    frame["day_of_week"] = frame["event_date"].dt.day_name()
    frame["_violent"] = frame["event_type"].isin(
        ["Battles", "Violence against civilians", "Explosions/Remote violence"]
    ).astype(int)
    frame["_high"] = frame["severity"].eq("High").astype(int)

    daily = frame.groupby(["admin1", "event_date"], dropna=False).agg(
        events=("event_id_cnty", "size"), violent=("_violent", "sum"), high=("_high", "sum"),
    ).reset_index().sort_values(["admin1", "event_date"])

    def county_history(group):
        group = group.sort_values("event_date").copy().set_index("event_date")
        group["county_events_previous_30_days"] = group["events"].rolling("30D", closed="left").sum()
        group["county_events_previous_90_days"] = group["events"].rolling("90D", closed="left").sum()
        group["violent_events_previous_30_days"] = group["violent"].rolling("30D", closed="left").sum()
        group["previous_high_severity_events_in_county"] = group["high"].rolling("90D", closed="left").sum()
        previous_date = pd.Series(group.index, index=group.index).shift(1)
        group["days_since_previous_event_in_county"] = (group.index.to_series() - previous_date).dt.days
        return group.reset_index()

    history = daily.groupby("admin1", group_keys=False, dropna=False).apply(
        lambda group: county_history(group).assign(admin1=group.name), include_groups=False,
    )
    frame = frame.merge(
        history[["admin1", "event_date", *HISTORY_FEATURES[:-1]]],
        on=["admin1", "event_date"], how="left", validate="many_to_one",
    )
    actor_daily = frame.groupby(["actor1", "event_date"], dropna=False).size().rename(
        "actor_events_today"
    ).reset_index().sort_values(["actor1", "event_date"])
    actor_daily["actor_previous_event_count"] = (
        actor_daily.groupby("actor1", dropna=False)["actor_events_today"].cumsum()
        - actor_daily["actor_events_today"]
    )
    frame = frame.merge(
        actor_daily[["actor1", "event_date", "actor_previous_event_count"]],
        on=["actor1", "event_date"], how="left", validate="many_to_one",
    )
    frame[HISTORY_FEATURES] = frame[HISTORY_FEATURES].fillna(0)
    return frame


def preprocessor() -> ColumnTransformer:
    return ColumnTransformer([
        ("categorical", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=5)),
        ]), CATEGORICAL_FEATURES),
        ("numeric", Pipeline([
            ("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()),
        ]), NUMERIC_FEATURES),
    ])


def models() -> dict[str, Pipeline]:
    return {
        "Logistic Regression": Pipeline([
            ("preprocess", clone(preprocessor())),
            ("model", LogisticRegression(max_iter=2000, class_weight="balanced", solver="saga", random_state=42)),
        ]),
        "XGBoost": Pipeline([
            ("preprocess", clone(preprocessor())),
            ("model", LabelEncodedXGBClassifier(random_state=42, n_jobs=-1)),
        ]),
    }


def sample_weights(labels: pd.Series) -> np.ndarray:
    counts = labels.value_counts()
    weights = (len(labels) / (len(CLASS_ORDER) * counts)).to_dict()
    return labels.map(weights).to_numpy()


def evaluate(name: str, model: Pipeline, features, labels, split: str) -> dict:
    prediction = model.predict(features)
    raw = model.predict_proba(features)
    classes = list(model.classes_)
    probability = np.column_stack([raw[:, classes.index(label)] for label in CLASS_ORDER])
    binary = label_binarize(labels, classes=CLASS_ORDER)
    return {
        "model": name, "split": split, "accuracy": accuracy_score(labels, prediction),
        "macro_f1": f1_score(labels, prediction, labels=CLASS_ORDER, average="macro", zero_division=0),
        "high_recall": recall_score(labels, prediction, labels=["High"], average=None, zero_division=0)[0],
        "ovr_roc_auc": roc_auc_score(binary, probability, average="macro", multi_class="ovr"),
        "macro_pr_auc": average_precision_score(binary, probability, average="macro"),
    }


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=PROJECT_ROOT / "ACLED_Kenya_1997-2025.csv")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts" / "production")
    parser.add_argument("--version", default=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
    args = parser.parse_args()
    frame = engineer_features(args.data)
    train = frame["event_date"] < "2022-01-01"
    validation = frame["event_date"].between("2022-01-01", "2023-12-31")
    test = frame["event_date"] >= "2024-01-01"
    candidates = models()
    metrics = []
    for name, model in candidates.items():
        fit_args = {"model__sample_weight": sample_weights(frame.loc[train, "severity"].astype(str))} if name == "XGBoost" else {}
        model.fit(frame.loc[train, FEATURE_COLUMNS], frame.loc[train, "severity"].astype(str), **fit_args)
        metrics.append(evaluate(name, model, frame.loc[validation, FEATURE_COLUMNS], frame.loc[validation, "severity"].astype(str), "validation"))
        metrics.append(evaluate(name, model, frame.loc[test, FEATURE_COLUMNS], frame.loc[test, "severity"].astype(str), "test"))

    # The governed notebook decision is fixed: Logistic serves; XGBoost remains shadow-only.
    final_models = models()
    all_labels = frame["severity"].astype(str)
    final_models["Logistic Regression"].fit(frame[FEATURE_COLUMNS], all_labels)
    final_models["XGBoost"].fit(
        frame[FEATURE_COLUMNS], all_labels, model__sample_weight=sample_weights(all_labels),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    primary_path = args.output / "logistic_regression.joblib"
    challenger_path = args.output / "xgboost.joblib"
    joblib.dump(final_models["Logistic Regression"], primary_path)
    joblib.dump(final_models["XGBoost"], challenger_path)
    pd.DataFrame(metrics).to_csv(args.output / "model_metrics.csv", index=False)
    manifest = {
        "version": args.version, "created_at": datetime.now(timezone.utc).isoformat(),
        "training_data": {"file": args.data.name, "rows": len(frame), "max_event_date": str(frame["event_date"].max().date())},
        "feature_columns": FEATURE_COLUMNS, "class_order": CLASS_ORDER,
        "split_policy": {"train": "<2022-01-01", "validation": "2022-01-01..2023-12-31", "test": ">=2024-01-01"},
        "models": {
            "primary": {"name": "Logistic Regression", "file": primary_path.name, "sha256": digest(primary_path)},
            "challenger": {"name": "XGBoost", "file": challenger_path.name, "sha256": digest(challenger_path)},
        },
        "runtime": {"python": sys.version.split()[0], "scikit_learn": sklearn.__version__, "xgboost": xgboost.__version__},
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"artifact_directory": str(args.output), "version": args.version, "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
