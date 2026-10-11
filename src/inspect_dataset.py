"""Inspect the AI4I dataset without changing the source CSV."""

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORIES = (PROJECT_ROOT / "data" / "raw", PROJECT_ROOT / "Data" / "raw")
EXPECTED_COLUMNS = (
    "Type",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
    "Machine failure",
)


def validate_columns(columns: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Compare source column names exactly; do not trim or normalize them."""
    source_names = set(columns)
    present = [name for name in EXPECTED_COLUMNS if name in source_names]
    missing = [name for name in EXPECTED_COLUMNS if name not in source_names]
    unexpected = [name for name in columns if name not in EXPECTED_COLUMNS]
    return present, missing, unexpected


def find_dataset() -> Path:
    """Find exactly one CSV in a conventional raw-data directory."""
    # Windows treats ``data`` and ``Data`` as the same path, so resolve and
    # deduplicate candidates before deciding whether there is ambiguity.
    candidates = {
        path.resolve()
        for directory in RAW_DIRECTORIES
        if directory.is_dir()
        for path in directory.glob("*.csv")
        if path.is_file()
    }
    csv_files = sorted(candidates)
    if not csv_files:
        searched = ", ".join(str(directory) for directory in RAW_DIRECTORIES)
        raise FileNotFoundError(
            f"No CSV dataset was found in the raw-data folders: {searched}. "
            "Place the original CSV in one of those folders and try again."
        )
    if len(csv_files) > 1:
        files = "\n".join(f"  - {path}" for path in csv_files)
        raise RuntimeError(
            "More than one CSV was found; refusing to guess which dataset to inspect:\n"
            f"{files}"
        )
    return csv_files[0]


def inspect_dataset(dataset_path: Path) -> None:
    """Print a reproducible overview of the dataset."""
    frame = pd.read_csv(dataset_path)

    print(f"Dataset filename: {dataset_path.name}")
    print(f"Dataset path: {dataset_path.relative_to(PROJECT_ROOT)}")
    print(f"Shape: {frame.shape} (rows, columns)")
    print("Column names:")
    for column in frame.columns:
        print(f"  - {column}")

    print("\nFirst five rows:")
    print(frame.head().to_string(index=False))
    print("\nData types:")
    print(frame.dtypes.to_string())
    print("\nMissing values by column:")
    print(frame.isna().sum().to_string())
    print(f"\nDuplicate rows: {int(frame.duplicated().sum())}")
    print("\nBasic statistics (all columns):")
    print(frame.describe(include="all").to_string())

    present, missing, unexpected = validate_columns(frame.columns.tolist())
    print("\nAgreed-column check:")
    print(f"Present ({len(present)}/{len(EXPECTED_COLUMNS)}): {present}")
    print(f"Missing: {missing if missing else 'None'}")
    print(f"Unexpected column names (reported as-is): {unexpected if unexpected else 'None'}")

    if "Machine failure" in frame.columns:
        counts = frame["Machine failure"].value_counts(dropna=False).reindex(
            [0, 1], fill_value=0
        )
        percentages = counts / len(frame) * 100 if len(frame) else counts.astype(float)
        print("\nMachine failure class distribution:")
        for label in (0, 1):
            print(f"  {label}: {counts[label]} ({percentages[label]:.2f}%)")
    else:
        print("\nCannot report failure class distribution: 'Machine failure' is missing.")

    if "Type" in frame.columns:
        print(f"\nUnique values in Type: {frame['Type'].nunique(dropna=True)}")
    else:
        print("\nCannot report unique Type values: 'Type' is missing.")


if __name__ == "__main__":
    inspect_dataset(find_dataset())
