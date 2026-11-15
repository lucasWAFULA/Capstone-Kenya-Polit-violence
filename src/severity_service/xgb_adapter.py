"""Pickle-safe adapter for XGBoost's integer-label requirement."""

from __future__ import annotations

from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier


class LabelEncodedXGBClassifier(BaseEstimator, ClassifierMixin):
    def __init__(
        self, n_estimators=400, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1,
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.random_state = random_state
        self.n_jobs = n_jobs

    def fit(self, X, y, sample_weight=None):
        self.label_encoder_ = LabelEncoder().fit(y)
        encoded_y = self.label_encoder_.transform(y)
        self.classes_ = self.label_encoder_.classes_
        self.model_ = XGBClassifier(
            n_estimators=self.n_estimators, max_depth=self.max_depth,
            learning_rate=self.learning_rate, subsample=self.subsample,
            colsample_bytree=self.colsample_bytree, objective="multi:softprob",
            eval_metric="mlogloss", random_state=self.random_state,
            n_jobs=self.n_jobs,
        )
        self.model_.fit(X, encoded_y, sample_weight=sample_weight)
        return self

    def predict(self, X):
        return self.label_encoder_.inverse_transform(self.model_.predict(X).astype(int))

    def predict_proba(self, X):
        return self.model_.predict_proba(X)
