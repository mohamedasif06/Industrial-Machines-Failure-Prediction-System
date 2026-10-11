"""Shared paths and schema checks for the project scripts."""

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORIES = (PROJECT_ROOT / "data" / "raw", PROJECT_ROOT / "Data" / "raw")
INPUT_FEATURES = [
    "Type",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
]
TARGET = "Machine failure"
REQUIRED_COLUMNS = INPUT_FEATURES + [TARGET]
NUMERIC_FEATURES = INPUT_FEATURES[1:]


def find_dataset() -> Path:
    """Return the only CSV in the project's conventional raw-data folder."""
    candidates = {
        path.resolve()
        for directory in RAW_DIRECTORIES
        if directory.is_dir()
        for path in directory.glob("*.csv")
        if path.is_file()
    }
    files = sorted(candidates)
    if not files:
        searched = ", ".join(str(directory) for directory in RAW_DIRECTORIES)
        raise FileNotFoundError(f"No CSV dataset found in: {searched}")
    if len(files) != 1:
        found = "\n".join(f"  - {path}" for path in files)
        raise RuntimeError(f"Expected one raw CSV, found {len(files)}:\n{found}")
    return files[0]


def load_and_validate_dataset() -> tuple[Path, pd.DataFrame]:
    """Load the source CSV and validate exact required names and binary target."""
    path = find_dataset()
    frame = pd.read_csv(path)
    missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
    if missing:
        raise ValueError(
            "Dataset is missing required columns (names are matched exactly): "
            + ", ".join(repr(name) for name in missing)
        )
    if frame[TARGET].isna().any():
        raise ValueError(f"Target column {TARGET!r} contains missing values.")
    observed = set(frame[TARGET].unique())
    if not observed.issubset({0, 1}):
        raise ValueError(
            f"Target column {TARGET!r} must contain only 0 and 1; "
            f"found {sorted(observed, key=str)}."
        )
    return path, frame
