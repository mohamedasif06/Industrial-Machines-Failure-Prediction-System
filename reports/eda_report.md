# Exploratory Data Analysis Report

Source dataset: `Data\raw\ai4i2020.csv` (10,000 rows).
The source CSV was loaded read-only. Column names were checked exactly, and the target contains only 0 and 1.

## Agreed fields

Inputs: `Type`, `Air temperature [K]`, `Process temperature [K]`, `Rotational speed [rpm]`, `Torque [Nm]`, `Tool wear [min]`.
Target: `Machine failure`. IDs and failure-mode labels are excluded from this analysis' predictive input feature set.

## Target distribution

| Machine failure | Rows | Percent |
|---:|---:|---:|
| 0 | 9,661 | 96.61% |
| 1 | 339 | 3.39% |

The target is imbalanced: failures make up a small fraction of observations. This is a descriptive property of this dataset, not a causal conclusion.

## Machine type and observed failure rates

| Type | Rows | Failures | Observed failure rate |
|---|---:|---:|---:|
| H | 1,003 | 21 | 2.09% |
| L | 6,000 | 235 | 3.92% |
| M | 2,997 | 83 | 2.77% |

These are observed rates within this dataset; they do not establish that machine type causes failure.

## Numeric feature statistics

| Feature | Mean | Std. dev. | Min | Median | Max |
|---|---:|---:|---:|---:|---:|
| Air temperature [K] | 300.005 | 2.000 | 295.300 | 300.100 | 304.500 |
| Process temperature [K] | 310.006 | 1.484 | 305.700 | 310.100 | 313.800 |
| Rotational speed [rpm] | 1538.776 | 179.284 | 1168.000 | 1503.000 | 2886.000 |
| Torque [Nm] | 39.987 | 9.969 | 3.800 | 40.100 | 76.600 |
| Tool wear [min] | 107.951 | 63.654 | 0.000 | 108.000 | 253.000 |

## Feature and failure comparisons

The comparison charts show distributions split by target label and observed failure percentages by machine type. Boxplots hide outliers for readability. These views are descriptive and do not support causal claims.
Among the numeric inputs, `Torque [Nm]` has the largest absolute Pearson correlation with the binary target in this dataset (r = 0.191). Correlation alone does not show causation or predictive performance.

## Figures

- `figures/target_distribution.png` — target counts and percentages.
- `figures/feature_distributions.png` — machine type counts and feature histograms.
- `figures/features_vs_failure.png` — numeric feature boxplots split by failure label and observed failure rate by type.
- `figures/numeric_correlation_heatmap.png` — correlations among the five numeric inputs and target; record IDs and failure-mode labels are omitted.
