"""Train and evaluate two imbalanced binary classifiers on saved Phase 2 splits."""

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from project_utils import INPUT_FEATURES, PROJECT_ROOT, TARGET


PROCESSED_DIRECTORY = PROJECT_ROOT / "Data" / "processed"
MODEL_DIRECTORY = PROJECT_ROOT / "models"
REPORT_DIRECTORY = PROJECT_ROOT / "reports"
TRAIN_PATH = PROCESSED_DIRECTORY / "train.csv"
TEST_PATH = PROCESSED_DIRECTORY / "test.csv"
PREPROCESSING_PATH = PROCESSED_DIRECTORY / "preprocessing.json"
RANDOM_SEED = 42
CV_FOLDS = 5


def model_input(model: Any, features: pd.DataFrame) -> Any:
    """Keep XGBoost's feature order while avoiding its restricted name syntax."""
    if isinstance(model, XGBClassifier):
        return features.to_numpy()
    return features


def load_and_validate_splits() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, dict[str, Any]]:
    """Read fixed Phase 2 artifacts and validate their schema and values."""
    required_files = [TRAIN_PATH, TEST_PATH, PREPROCESSING_PATH]
    missing_files = [str(path) for path in required_files if not path.is_file()]
    if missing_files:
        raise FileNotFoundError("Required Phase 2 files are missing: " + ", ".join(missing_files))

    metadata = json.loads(PREPROCESSING_PATH.read_text(encoding="utf-8"))
    if metadata.get("input_features") != INPUT_FEATURES or metadata.get("target") != TARGET:
        raise ValueError("preprocessing.json feature order or target does not match the agreed schema.")
    mapping = metadata.get("type_encoding", {}).get("mapping")
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("preprocessing.json must contain the saved Type encoding mapping.")
    expected_mapping = {str(name): int(code) for name, code in mapping.items()}
    if mapping != expected_mapping or len(set(expected_mapping.values())) != len(expected_mapping):
        raise ValueError("Saved Type mapping must map string categories to unique integer codes.")

    expected_columns = INPUT_FEATURES + [TARGET]
    excluded = {"UDI", "Product ID", "TWF", "HDF", "PWF", "OSF", "RNF"}
    datasets = []
    for path, name in ((TRAIN_PATH, "training"), (TEST_PATH, "testing")):
        frame = pd.read_csv(path)
        if frame.columns.tolist() != expected_columns:
            raise ValueError(
                f"{name} columns must appear in exact agreed order {expected_columns}; "
                f"found {frame.columns.tolist()}."
            )
        present_excluded = excluded.intersection(frame.columns)
        if present_excluded:
            raise ValueError(f"Excluded columns found in {name} data: {sorted(present_excluded)}")
        if frame.empty or frame.isna().any().any():
            raise ValueError(f"{name} data must be non-empty and contain no missing values.")
        if not set(frame[TARGET].unique()).issubset({0, 1}):
            raise ValueError(f"{name} target must contain only binary classes 0 and 1.")
        for feature in INPUT_FEATURES:
            if not pd.api.types.is_numeric_dtype(frame[feature]):
                raise TypeError(f"{name} feature {feature!r} must be numeric after preprocessing.")
            if not np.isfinite(frame[feature].to_numpy(dtype=float)).all():
                raise ValueError(f"{name} feature {feature!r} contains non-finite values.")
        allowed_type_codes = set(expected_mapping.values())
        if not set(frame["Type"].astype(int).unique()).issubset(allowed_type_codes):
            raise ValueError(f"{name} Type values do not match the saved encoding mapping.")
        datasets.append(frame)

    train, test = datasets
    return (
        train.loc[:, INPUT_FEATURES],
        train[TARGET].astype(int),
        test.loc[:, INPUT_FEATURES],
        test[TARGET].astype(int),
        metadata,
    )


def create_models() -> dict[str, Any]:
    """Return the fixed model configurations used for this reproducible run."""
    return {
        "Random Forest": RandomForestClassifier(
            n_estimators=400,
            max_depth=None,
            min_samples_leaf=2,
            random_state=RANDOM_SEED,
            n_jobs=1,
        ),
        "XGBoost": XGBClassifier(
            n_estimators=400,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=1.0,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=RANDOM_SEED,
            n_jobs=1,
            tree_method="hist",
        ),
    }


def calculate_metrics(y_true: pd.Series, y_pred: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    matrix = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = (int(value) for value in matrix.ravel())
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    beta = 2.0
    f2 = (1 + beta**2) * precision * recall / (beta**2 * precision + recall) if (precision or recall) else 0.0
    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1_score": float(f1),
        "f2_score": float(f2),
        "average_precision_pr_auc": float(average_precision_score(y_true, probabilities)),
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "confusion_matrix": {"labels": [0, 1], "matrix": matrix.astype(int).tolist()},
        "true_negatives": tn,
        "false_positives": fp,
        "false_negatives": fn,
        "true_positives": tp,
        "threshold": 0.5,
    }


def cross_validate_models(
    models: dict[str, Any], features: pd.DataFrame, target: pd.Series
) -> dict[str, dict[str, float]]:
    """Compare fixed models using only stratified folds from the training split."""
    splitter = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)
    summaries: dict[str, dict[str, float]] = {}
    for model_name, prototype in models.items():
        fold_metrics = []
        for fit_indices, validation_indices in splitter.split(features, target):
            fold_model = clone(prototype)
            fit_features = features.iloc[fit_indices]
            fit_target = target.iloc[fit_indices]
            validation_features = features.iloc[validation_indices]
            validation_target = target.iloc[validation_indices]
            weights = compute_sample_weight(class_weight="balanced", y=fit_target)
            fold_model.fit(model_input(fold_model, fit_features), fit_target, sample_weight=weights)
            fold_validation_features = model_input(fold_model, validation_features)
            predictions = fold_model.predict(fold_validation_features)
            probabilities = fold_model.predict_proba(fold_validation_features)[:, 1]
            fold_metrics.append(calculate_metrics(validation_target, predictions, probabilities))
        metric_names = ["precision", "recall", "f1_score", "f2_score", "average_precision_pr_auc", "roc_auc"]
        summaries[model_name] = {
            name: float(np.mean([fold[name] for fold in fold_metrics])) for name in metric_names
        }
    return summaries


def write_comparison_report(results: dict[str, Any], selected_name: str, cv_results: dict[str, Any]) -> None:
    lines = [
        "# Model Training and Evaluation Report",
        "",
        "Models were trained using the saved Phase 2 training split. The Phase 2 test split was not used for fitting, resampling, or selecting the model.",
        "Class weights were applied as per-row balanced sample weights calculated from the relevant training rows only. No resampling was used.",
        "Both test evaluations use the default 0.5 probability threshold; probabilities are model estimates, not calibrated real-world failure probabilities.",
        "",
        "## Test set metrics",
        "",
        "| Model | Precision | Recall | F1 | Average precision (PR-AUC) | ROC-AUC | Accuracy | False positives | False negatives |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model_name, metrics in results.items():
        lines.append(
            f"| {model_name} | {metrics['precision']:.3f} | {metrics['recall']:.3f} | "
            f"{metrics['f1_score']:.3f} | {metrics['average_precision_pr_auc']:.3f} | "
            f"{metrics['roc_auc']:.3f} | {metrics['accuracy']:.3f} | "
            f"{metrics['false_positives']} | {metrics['false_negatives']} |"
        )
    lines.extend(["", "Confusion matrices use rows = actual `[0, 1]` and columns = predicted `[0, 1]`.", ""])
    for model_name, metrics in results.items():
        lines.extend([
            f"### {model_name}",
            "",
            f"Confusion matrix: `[[{metrics['confusion_matrix']['matrix'][0][0]}, {metrics['confusion_matrix']['matrix'][0][1]}], "
            f"[{metrics['confusion_matrix']['matrix'][1][0]}, {metrics['confusion_matrix']['matrix'][1][1]}]]`.",
            f"This model missed **{metrics['false_negatives']}** failures (false negatives) and raised **{metrics['false_positives']}** false alarms (false positives) on the test split.",
            "",
        ])
    lines.extend([
        "## Training-only model selection",
        "",
        f"The recommended model is **{selected_name}**, selected using the higher mean F2 score over {CV_FOLDS}-fold stratified cross-validation on training data only. F2 weights recall more heavily than precision to reflect the cost of missed failures; PR-AUC is the next tie-breaker.",
        "",
        "| Model | CV precision | CV recall | CV F2 | CV average precision (PR-AUC) |",
        "|---|---:|---:|---:|---:|",
    ])
    for model_name, metrics in cv_results.items():
        lines.append(f"| {model_name} | {metrics['precision']:.3f} | {metrics['recall']:.3f} | {metrics['f2_score']:.3f} | {metrics['average_precision_pr_auc']:.3f} |")
    lines.extend([
        "",
        "## Why accuracy is secondary",
        "",
        "Only 3.39% of the full dataset is failures. A classifier that predicts no failures would still achieve about 96.61% accuracy while detecting none of them. Precision, recall, F-scores, PR-AUC, ROC-AUC, and false-positive/false-negative counts provide a more useful view of failure detection and alarm burden.",
        "",
        "No prediction horizon is implied by this classification task.",
        "",
    ])
    (REPORT_DIRECTORY / "model_comparison.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    x_train, y_train, x_test, y_test, phase2_metadata = load_and_validate_splits()
    prototypes = create_models()

    # Model choice is made using training-only cross-validation, never the test split.
    cv_results = cross_validate_models(prototypes, x_train, y_train)
    selected_name = max(
        prototypes,
        key=lambda name: (cv_results[name]["f2_score"], cv_results[name]["average_precision_pr_auc"]),
    )

    test_results = {}
    for model_name, model in prototypes.items():
        training_weights = compute_sample_weight(class_weight="balanced", y=y_train)
        model.fit(model_input(model, x_train), y_train, sample_weight=training_weights)
        model_test_features = model_input(model, x_test)
        predictions = model.predict(model_test_features)
        probabilities = model.predict_proba(model_test_features)[:, 1]
        test_results[model_name] = calculate_metrics(y_test, predictions, probabilities)
        artifact_name = "random_forest.joblib" if model_name == "Random Forest" else "xgboost.joblib"
        joblib.dump(model, MODEL_DIRECTORY / artifact_name)

    selected_filename = "random_forest.joblib" if selected_name == "Random Forest" else "xgboost.joblib"
    selected_path = MODEL_DIRECTORY / "recommended_model.joblib"
    joblib.dump(joblib.load(MODEL_DIRECTORY / selected_filename), selected_path)

    metadata = {
        "recommended_model": selected_name,
        "recommended_artifact": "models/recommended_model.joblib",
        "model_artifacts": {
            "Random Forest": "models/random_forest.joblib",
            "XGBoost": "models/xgboost.joblib",
        },
        "feature_order": INPUT_FEATURES,
        "target": TARGET,
        "type_mapping": phase2_metadata["type_encoding"]["mapping"],
        "random_seed": RANDOM_SEED,
        "class_weighting": "balanced sample weights computed from training rows only",
        "test_probability_threshold": 0.5,
        "selection_method": f"{CV_FOLDS}-fold stratified CV on training data only; highest mean F2, then average precision",
        "cross_validation_metrics": cv_results,
        "parameters": {name: model.get_params(deep=False) for name, model in prototypes.items()},
        "training_rows": len(x_train),
        "test_rows": len(x_test),
        "phase2_split_seed": phase2_metadata.get("split", {}).get("random_seed"),
    }
    (MODEL_DIRECTORY / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (REPORT_DIRECTORY / "model_metrics.json").write_text(json.dumps(test_results, indent=2), encoding="utf-8")
    write_comparison_report(test_results, selected_name, cv_results)

    print("Test metrics (classification threshold = 0.5):")
    for model_name, metrics in test_results.items():
        print(
            f"{model_name}: precision={metrics['precision']:.4f}, recall={metrics['recall']:.4f}, "
            f"F1={metrics['f1_score']:.4f}, AP/PR-AUC={metrics['average_precision_pr_auc']:.4f}, "
            f"ROC-AUC={metrics['roc_auc']:.4f}, accuracy={metrics['accuracy']:.4f}, "
            f"confusion={metrics['confusion_matrix']['matrix']}"
        )
    print(f"Recommended model (training-only CV): {selected_name}")
    print(f"Saved selected model: {selected_path.relative_to(PROJECT_ROOT)}")
    print(f"Metrics: {(REPORT_DIRECTORY / 'model_metrics.json').relative_to(PROJECT_ROOT)}")
    print(f"Report: {(REPORT_DIRECTORY / 'model_comparison.md').relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
