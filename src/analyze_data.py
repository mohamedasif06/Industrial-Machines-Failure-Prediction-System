"""Run exploratory analysis without changing the original source dataset."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from project_utils import (
    NUMERIC_FEATURES,
    PROJECT_ROOT,
    TARGET,
    load_and_validate_dataset,
)


FIGURE_DIRECTORY = PROJECT_ROOT / "reports" / "figures"
REPORT_PATH = PROJECT_ROOT / "reports" / "eda_report.md"


def save_target_distribution(frame: pd.DataFrame) -> None:
    counts = frame[TARGET].value_counts().reindex([0, 1], fill_value=0)
    percentages = counts / len(frame) * 100
    figure, axis = plt.subplots(figsize=(6, 4))
    bars = axis.bar(["No failure (0)", "Failure (1)"], counts, color=["#4C78A8", "#E45756"])
    axis.set_title("Machine failure class distribution")
    axis.set_ylabel("Number of rows")
    axis.bar_label(bars, labels=[f"{count:,}\n({percent:.2f}%)" for count, percent in zip(counts, percentages)])
    figure.tight_layout()
    figure.savefig(FIGURE_DIRECTORY / "target_distribution.png", dpi=150)
    plt.close(figure)


def save_feature_distributions(frame: pd.DataFrame) -> None:
    figure, axes = plt.subplots(2, 3, figsize=(14, 8))
    type_counts = frame["Type"].value_counts().sort_index()
    axes[0, 0].bar(type_counts.index, type_counts.values, color="#72B7B2")
    axes[0, 0].set(title="Machine type counts", xlabel="Type", ylabel="Number of rows")
    for axis, column in zip(axes.flat[1:], NUMERIC_FEATURES):
        axis.hist(frame[column], bins=30, color="#4C78A8", edgecolor="white")
        axis.set(title=column, xlabel=column, ylabel="Number of rows")
    figure.suptitle("Input feature distributions", fontsize=15)
    figure.tight_layout()
    figure.savefig(FIGURE_DIRECTORY / "feature_distributions.png", dpi=150)
    plt.close(figure)


def save_feature_failure_comparisons(frame: pd.DataFrame) -> None:
    figure, axes = plt.subplots(2, 3, figsize=(14, 8))
    for axis, column in zip(axes.flat[:5], NUMERIC_FEATURES):
        groups = [frame.loc[frame[TARGET] == label, column] for label in (0, 1)]
        axis.boxplot(groups, tick_labels=["No failure (0)", "Failure (1)"], showfliers=False)
        axis.set_title(column)
        axis.set_ylabel(column)
        axis.tick_params(axis="x", labelrotation=12)

    type_rates = frame.groupby("Type", observed=False)[TARGET].mean().sort_index() * 100
    axes.flat[5].bar(type_rates.index, type_rates.values, color="#F58518")
    axes.flat[5].set(title="Observed failure rate by type", xlabel="Type", ylabel="Failure rate (%)")
    figure.suptitle("Feature values and observed machine failure", fontsize=15)
    figure.tight_layout()
    figure.savefig(FIGURE_DIRECTORY / "features_vs_failure.png", dpi=150)
    plt.close(figure)


def save_correlation_heatmap(frame: pd.DataFrame) -> pd.DataFrame:
    correlation_columns = NUMERIC_FEATURES + [TARGET]
    correlation = frame[correlation_columns].corr(numeric_only=True)
    figure, axis = plt.subplots(figsize=(9, 7))
    image = axis.imshow(correlation, cmap="coolwarm", vmin=-1, vmax=1)
    axis.set_xticks(range(len(correlation.columns)), correlation.columns, rotation=35, ha="right")
    axis.set_yticks(range(len(correlation.index)), correlation.index)
    for row in range(len(correlation.index)):
        for column in range(len(correlation.columns)):
            axis.text(column, row, f"{correlation.iloc[row, column]:.2f}", ha="center", va="center", fontsize=8)
    axis.set_title("Correlation heatmap: numeric inputs and target")
    figure.colorbar(image, ax=axis, label="Pearson correlation")
    figure.tight_layout()
    figure.savefig(FIGURE_DIRECTORY / "numeric_correlation_heatmap.png", dpi=150)
    plt.close(figure)
    return correlation


def build_report(frame: pd.DataFrame, dataset_path, correlation: pd.DataFrame) -> None:
    counts = frame[TARGET].value_counts().reindex([0, 1], fill_value=0)
    percentages = counts / len(frame) * 100
    type_summary = frame.groupby("Type", observed=False)[TARGET].agg(["count", "sum", "mean"])
    type_summary["failure_rate_percent"] = type_summary["mean"] * 100
    numeric_stats = frame[NUMERIC_FEATURES].describe().T

    lines = [
        "# Exploratory Data Analysis Report",
        "",
        f"Source dataset: `{dataset_path.relative_to(PROJECT_ROOT)}` ({len(frame):,} rows).",
        "The source CSV was loaded read-only. Column names were checked exactly, and the target contains only 0 and 1.",
        "",
        "## Agreed fields",
        "",
        "Inputs: `Type`, `Air temperature [K]`, `Process temperature [K]`, `Rotational speed [rpm]`, `Torque [Nm]`, `Tool wear [min]`.",
        "Target: `Machine failure`. IDs and failure-mode labels are excluded from this analysis' predictive input feature set.",
        "",
        "## Target distribution",
        "",
        "| Machine failure | Rows | Percent |",
        "|---:|---:|---:|",
        f"| 0 | {counts[0]:,} | {percentages[0]:.2f}% |",
        f"| 1 | {counts[1]:,} | {percentages[1]:.2f}% |",
        "",
        "The target is imbalanced: failures make up a small fraction of observations. This is a descriptive property of this dataset, not a causal conclusion.",
        "",
        "## Machine type and observed failure rates",
        "",
        "| Type | Rows | Failures | Observed failure rate |",
        "|---|---:|---:|---:|",
    ]
    for machine_type, row in type_summary.iterrows():
        lines.append(f"| {machine_type} | {int(row['count']):,} | {int(row['sum']):,} | {row['failure_rate_percent']:.2f}% |")

    lines.extend(["", "These are observed rates within this dataset; they do not establish that machine type causes failure.", "", "## Numeric feature statistics", "", "| Feature | Mean | Std. dev. | Min | Median | Max |", "|---|---:|---:|---:|---:|---:|"])
    for feature, row in numeric_stats.iterrows():
        lines.append(f"| {feature} | {row['mean']:.3f} | {row['std']:.3f} | {row['min']:.3f} | {row['50%']:.3f} | {row['max']:.3f} |")

    strongest = correlation[TARGET].drop(TARGET).abs().sort_values(ascending=False)
    strongest_name = strongest.index[0]
    strongest_value = correlation.loc[strongest_name, TARGET]
    lines.extend([
        "",
        "## Feature and failure comparisons",
        "",
        "The comparison charts show distributions split by target label and observed failure percentages by machine type. Boxplots hide outliers for readability. These views are descriptive and do not support causal claims.",
        f"Among the numeric inputs, `{strongest_name}` has the largest absolute Pearson correlation with the binary target in this dataset (r = {strongest_value:.3f}). Correlation alone does not show causation or predictive performance.",
        "",
        "## Figures",
        "",
        "- `figures/target_distribution.png` — target counts and percentages.",
        "- `figures/feature_distributions.png` — machine type counts and feature histograms.",
        "- `figures/features_vs_failure.png` — numeric feature boxplots split by failure label and observed failure rate by type.",
        "- `figures/numeric_correlation_heatmap.png` — correlations among the five numeric inputs and target; record IDs and failure-mode labels are omitted.",
        "",
    ])
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    FIGURE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    dataset_path, frame = load_and_validate_dataset()
    if frame.empty:
        raise ValueError("The dataset contains no rows to analyze.")
    missing_numeric = [column for column in NUMERIC_FEATURES if not pd.api.types.is_numeric_dtype(frame[column])]
    if missing_numeric:
        raise ValueError(f"Expected numeric agreed features; non-numeric columns: {missing_numeric}")

    print(f"Dataset: {dataset_path.name} | shape: {frame.shape}")
    print("Numeric feature descriptive statistics:")
    print(frame[NUMERIC_FEATURES].describe().to_string())
    print("\nMachine type counts:")
    print(frame["Type"].value_counts().sort_index().to_string())
    print("\nFailure counts and percentages:")
    counts = frame[TARGET].value_counts().reindex([0, 1], fill_value=0)
    for label, count in counts.items():
        print(f"  {label}: {count} ({count / len(frame) * 100:.2f}%)")
    print("\nFailure rates by type:")
    print((frame.groupby("Type", observed=False)[TARGET].mean() * 100).to_string())

    save_target_distribution(frame)
    save_feature_distributions(frame)
    save_feature_failure_comparisons(frame)
    correlation = save_correlation_heatmap(frame)
    build_report(frame, dataset_path, correlation)
    print(f"\nEDA report: {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Figures: {FIGURE_DIRECTORY.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
