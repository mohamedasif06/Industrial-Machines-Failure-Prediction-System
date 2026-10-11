# Dataset Inspection Report

## Dataset

- **File:** `Data/raw/ai4i2020.csv`
- **Shape:** 10,000 rows × 14 columns
- **Inspection:** Loaded with pandas for read-only inspection. The source CSV was not changed.

## Columns and agreed fields

The seven agreed fields are all present: `Type`, `Air temperature [K]`, `Process temperature [K]`, `Rotational speed [rpm]`, `Torque [Nm]`, `Tool wear [min]`, and `Machine failure`.

Columns found, in file order: `UDI`, `Product ID`, `Type`, `Air temperature [K]`, `Process temperature [K]`, `Rotational speed [rpm]`, `Torque [Nm]`, `Tool wear [min]`, `Machine failure`, `TWF`, `HDF`, `PWF`, `OSF`, `RNF`.

The other column names (`UDI`, `Product ID`, and the failure-mode labels `TWF`, `HDF`, `PWF`, `OSF`, `RNF`) are reported as present in the source but are outside the agreed model inputs. No column names were changed. Model inputs for subsequent phases must remain limited to the six agreed features, with `Machine failure` as the target.

## Data types

| Column | Type |
|---|---|
| UDI | int64 |
| Product ID | string |
| Type | string |
| Air temperature [K] | float64 |
| Process temperature [K] | float64 |
| Rotational speed [rpm] | int64 |
| Torque [Nm] | float64 |
| Tool wear [min] | int64 |
| Machine failure | int64 |
| TWF | int64 |
| HDF | int64 |
| PWF | int64 |
| OSF | int64 |
| RNF | int64 |

## Data quality and target distribution

- **Missing values:** 0 in every column.
- **Duplicate rows:** 0.
- **Unique `Type` values:** 3 (`L`, `M`, and `H`).
- **Machine failure = 0:** 9,661 rows (96.61%).
- **Machine failure = 1:** 339 rows (3.39%).

The target is imbalanced: failure examples are a small share of this dataset. Keep this in mind when evaluating future models.

## Basic statistics

Numeric summaries (mean, standard deviation, min, quartiles, max):

| Column | Mean | Std. dev. | Min | 25% | Median | 75% | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| UDI | 5000.500 | 2886.896 | 1 | 2500.75 | 5000.5 | 7500.25 | 10000 |
| Air temperature [K] | 300.005 | 2.000 | 295.3 | 298.3 | 300.1 | 301.5 | 304.5 |
| Process temperature [K] | 310.006 | 1.484 | 305.7 | 308.8 | 310.1 | 311.1 | 313.8 |
| Rotational speed [rpm] | 1538.776 | 179.284 | 1168 | 1423 | 1503 | 1612 | 2886 |
| Torque [Nm] | 39.987 | 9.969 | 3.8 | 33.2 | 40.1 | 46.8 | 76.6 |
| Tool wear [min] | 107.951 | 63.654 | 0 | 53 | 108 | 162 | 253 |
| Machine failure | 0.034 | 0.181 | 0 | 0 | 0 | 0 | 1 |

Categorical summaries: `Product ID` has 10,000 unique values; `Type` has 3 unique values, with `L` as the most frequent category (6,000 rows). The five failure-mode indicator columns are binary and are not model inputs under the agreed feature list.

## Reproduce

From the project root, run:

```powershell
.\.venv\Scripts\python.exe .\src\inspect_dataset.py
```

The script discovers a single CSV in `data/raw/` or `Data/raw/`, prints this inspection information from the current file, and fails with a clear message if no CSV is found or if multiple candidates need to be resolved.
