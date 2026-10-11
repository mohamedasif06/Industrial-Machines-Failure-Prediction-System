"""Thin adapter that reuses the project's existing model inference function."""

import json
import sys
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT

SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from inference import predict_failure  # noqa: E402


class InferenceService:
    """Expose saved-model inference and a lightweight availability check."""

    def predict(self, values: dict[str, Any]) -> dict[str, Any]:
        return predict_failure(values)

    def availability(self) -> tuple[bool, str | None, str]:
        metadata_path = PROJECT_ROOT / "models" / "metadata.json"
        if not metadata_path.is_file():
            return False, None, f"Model metadata not found: {metadata_path}"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return False, None, f"Model metadata cannot be read: {error}"
        artifact_name = metadata.get("recommended_artifact")
        model_name = metadata.get("recommended_model")
        artifact_path = PROJECT_ROOT / str(artifact_name or "")
        if not artifact_name or not artifact_path.is_file():
            return False, model_name, f"Recommended model artifact is unavailable: {artifact_path}"
        return True, model_name, "Saved model metadata and artifact are available."
