"""Load the saved recommended model and predict from six agreed input values."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from project_utils import INPUT_FEATURES, PROJECT_ROOT


DEFAULT_METADATA_PATH = PROJECT_ROOT / "models" / "metadata.json"


def load_recommended_model(metadata_path: Path = DEFAULT_METADATA_PATH):
    """Load metadata and the selected model without retraining."""
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Model metadata was not found: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("feature_order") != INPUT_FEATURES:
        raise ValueError("Saved model feature order does not match the agreed six features.")
    artifact_path = PROJECT_ROOT / metadata.get("recommended_artifact", "")
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Recommended model artifact was not found: {artifact_path}")
    model = joblib.load(artifact_path)
    return model, metadata


def predict_failure(input_values: Mapping[str, Any]) -> dict[str, Any]:
    """Predict one machine failure label from original Type and five numeric readings.

    Type must be one of the original categories (for example, ``"L"``). The
    mapping saved during Phase 2 is applied exactly as recorded in metadata.
    """
    if not isinstance(input_values, Mapping):
        raise TypeError("input_values must be a mapping with the six agreed feature names.")
    missing = [name for name in INPUT_FEATURES if name not in input_values]
    extra = [name for name in input_values if name not in INPUT_FEATURES]
    if missing or extra:
        raise ValueError(f"Invalid input keys. Missing: {missing}; unexpected: {extra}.")

    model, metadata = load_recommended_model()
    type_mapping = metadata.get("type_mapping", {})
    machine_type = input_values["Type"]
    if machine_type not in type_mapping:
        raise ValueError(f"Unknown Type {machine_type!r}; expected one of {sorted(type_mapping)}.")

    row = {"Type": type_mapping[machine_type]}
    for feature in INPUT_FEATURES[1:]:
        try:
            value = float(input_values[feature])
        except (TypeError, ValueError) as error:
            raise ValueError(f"Feature {feature!r} must be a finite number.") from error
        if not np.isfinite(value):
            raise ValueError(f"Feature {feature!r} must be a finite number.")
        row[feature] = value
    features = pd.DataFrame([[row[name] for name in INPUT_FEATURES]], columns=INPUT_FEATURES)
    model_features = features.to_numpy() if isinstance(model, XGBClassifier) else features
    prediction = int(model.predict(model_features)[0])
    if prediction not in (0, 1):
        raise ValueError(f"Model returned invalid prediction class {prediction}.")

    result: dict[str, Any] = {
        "predicted_class": prediction,
        "predicted_label": "failure" if prediction == 1 else "no failure",
        "model_name": metadata["recommended_model"],
        "probability_note": "Model estimate; not a guaranteed real-world failure probability.",
    }
    if hasattr(model, "predict_proba"):
        result["estimated_failure_probability"] = float(model.predict_proba(model_features)[0, 1])
    return result
