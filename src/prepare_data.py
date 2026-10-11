"""Create reproducible stratified train/test splits for later modeling."""

import json

import pandas as pd
from sklearn.model_selection import train_test_split

from project_utils import INPUT_FEATURES, PROJECT_ROOT, REQUIRED_COLUMNS, TARGET, load_and_validate_dataset


TEST_SIZE = 0.20
RANDOM_SEED = 42
PROCESSED_DIRECTORY = PROJECT_ROOT / "Data" / "processed"


def encode_type_from_training_data(
    train_features: pd.DataFrame, test_features: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Map machine categories to deterministic integer codes learned from train only."""
    categories = sorted(train_features["Type"].dropna().unique().tolist())
    if train_features["Type"].isna().any() or test_features["Type"].isna().any():
        raise ValueError("Input feature 'Type' contains missing values.")
    category_to_code = {category: index for index, category in enumerate(categories)}
    unknown = sorted(set(test_features["Type"].unique()) - set(category_to_code))
    if unknown:
        raise ValueError(f"Test split contains Type values absent from training data: {unknown}")

    train_encoded = train_features.copy()
    test_encoded = test_features.copy()
    train_encoded["Type"] = train_encoded["Type"].map(category_to_code).astype("int64")
    test_encoded["Type"] = test_encoded["Type"].map(category_to_code).astype("int64")
    return train_encoded, test_encoded, category_to_code


def main() -> None:
    dataset_path, frame = load_and_validate_dataset()
    if frame.empty:
        raise ValueError("The dataset contains no rows to split.")
    if frame["Type"].isna().any():
        raise ValueError("Input feature 'Type' contains missing values.")
    selected = frame.loc[:, REQUIRED_COLUMNS].copy()
    features = selected.loc[:, INPUT_FEATURES]
    target = selected[TARGET]

    train_features, test_features, train_target, test_target = train_test_split(
        features,
        target,
        test_size=TEST_SIZE,
        random_state=RANDOM_SEED,
        stratify=target,
    )
    train_features, test_features, type_mapping = encode_type_from_training_data(
        train_features, test_features
    )
    train_frame = train_features.assign(**{TARGET: train_target})
    test_frame = test_features.assign(**{TARGET: test_target})

    PROCESSED_DIRECTORY.mkdir(parents=True, exist_ok=True)
    train_path = PROCESSED_DIRECTORY / "train.csv"
    test_path = PROCESSED_DIRECTORY / "test.csv"
    metadata_path = PROCESSED_DIRECTORY / "preprocessing.json"
    train_frame.to_csv(train_path, index=False)
    test_frame.to_csv(test_path, index=False)

    metadata = {
        "source_dataset": str(dataset_path.relative_to(PROJECT_ROOT)),
        "input_features": INPUT_FEATURES,
        "target": TARGET,
        "excluded_source_columns": ["UDI", "Product ID", "TWF", "HDF", "PWF", "OSF", "RNF"],
        "type_encoding": {
            "method": "integer category encoding",
            "fit_on": "training split only",
            "mapping": type_mapping,
            "note": "Codes are category identifiers, not a numeric order or measured quantity.",
        },
        "split": {
            "test_size": TEST_SIZE,
            "random_seed": RANDOM_SEED,
            "stratified_by": TARGET,
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Source dataset: {dataset_path.name}")
    print(f"Input features ({len(INPUT_FEATURES)}): {INPUT_FEATURES}")
    print(f"Target: {TARGET}")
    print(f"Type encoding learned from training split: {type_mapping}")
    print(f"Train rows: {len(train_frame)}; failures: {int(train_target.sum())}; non-failures: {int((train_target == 0).sum())}")
    print(f"Test rows: {len(test_frame)}; failures: {int(test_target.sum())}; non-failures: {int((test_target == 0).sum())}")
    print(f"Train columns: {train_frame.columns.tolist()}")
    print(f"Train CSV: {train_path.relative_to(PROJECT_ROOT)}")
    print(f"Test CSV: {test_path.relative_to(PROJECT_ROOT)}")
    print(f"Preprocessing metadata: {metadata_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
