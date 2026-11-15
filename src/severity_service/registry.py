"""Load and validate immutable model artifacts from a local registry directory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import joblib

from .features import CLASS_ORDER, FEATURE_COLUMNS


@dataclass(frozen=True)
class ModelRegistry:
    primary: object
    challenger: object
    manifest: dict

    @classmethod
    def load(cls, directory: Path) -> "ModelRegistry":
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"Model manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("feature_columns") != FEATURE_COLUMNS:
            raise RuntimeError("Artifact feature contract does not match service code")
        if manifest.get("class_order") != CLASS_ORDER:
            raise RuntimeError("Artifact class order does not match service code")

        def load_model(role: str):
            metadata = manifest["models"][role]
            path = directory / metadata["file"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != metadata["sha256"]:
                raise RuntimeError(f"Checksum mismatch for {role} model")
            return joblib.load(path)

        return cls(load_model("primary"), load_model("challenger"), manifest)
