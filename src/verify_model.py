"""Read-only checks for the trained model artifact and inference interface."""

import json

from inference import predict_failure
from project_utils import INPUT_FEATURES, PROJECT_ROOT


def main() -> None:
    metadata_path = PROJECT_ROOT / "models" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata["feature_order"] != INPUT_FEATURES:
        raise AssertionError("Saved feature order differs from the agreed schema.")

    valid_input = {
        "Type": "L",
        "Air temperature [K]": 300.0,
        "Process temperature [K]": 310.0,
        "Rotational speed [rpm]": 1500,
        "Torque [Nm]": 40.0,
        "Tool wear [min]": 100,
    }
    result = predict_failure(valid_input)
    if result["predicted_class"] not in (0, 1):
        raise AssertionError(f"Unexpected prediction class: {result}")
    if not 0.0 <= result["estimated_failure_probability"] <= 1.0:
        raise AssertionError(f"Invalid estimated probability: {result}")
    print(f"Reloaded-model prediction: {result}")

    invalid_cases = [
        ({key: value for key, value in valid_input.items() if key != "Torque [Nm]"}, ValueError),
        ({**valid_input, "UDI": 1}, ValueError),
        ({**valid_input, "Type": "unknown"}, ValueError),
        ({**valid_input, "Torque [Nm]": float("nan")}, ValueError),
    ]
    for invalid_input, expected_error in invalid_cases:
        try:
            predict_failure(invalid_input)
        except expected_error:
            continue
        raise AssertionError(f"Invalid input was not rejected: {invalid_input}")
    print("Input validation checks passed: missing field, extra excluded field, unknown Type, and non-finite value.")
    print("Saved-model loading check passed; no retraining occurred.")


if __name__ == "__main__":
    main()
