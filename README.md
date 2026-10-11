# Industrial Machine Failure Forecasting

This project inspects the AI4I 2020 Predictive Maintenance Dataset, explores and prepares the agreed features, trains/evaluates failure classifiers, and can produce synthetic sensor events for demonstrating the saved classifier. The original CSV stays in `Data/raw/` and is read-only.

## Setup and inspection

Install project dependencies in the existing Windows virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\src\inspect_dataset.py
```

The inspection script discovers a single CSV in `data/raw/` or `Data/raw/`. See [reports/dataset_inspection.md](reports/dataset_inspection.md) for the Phase 1 findings.

## Agreed model fields

Inputs: `Type`, `Air temperature [K]`, `Process temperature [K]`, `Rotational speed [rpm]`, `Torque [Nm]`, and `Tool wear [min]`.

Target: `Machine failure`. `UDI`, `Product ID`, and failure-mode columns are not model inputs.

## Synthetic sensor simulator

The simulator generates independent synthetic readings; it does not replay the historical CSV or require physical IoT hardware. Each reading contains only the six agreed model inputs, calls the saved recommended model through `src/inference.py`, and includes the model-predicted class and estimated probability when supported. The model predicts a failure class from operating measurements; it does not promise a failure at a particular future time. Fault scenarios are synthetic combinations for exploring model/alert behavior and are not confirmed real-world failures. Model probabilities are estimates, not guaranteed real-world probabilities.

Start three simulated machines in normal mode, generating readings every two seconds until Ctrl+C:

```powershell
.\.venv\Scripts\python.exe .\src\simulator.py
```

Run a reproducible short fault-scenario demonstration and append events as newline-delimited JSON:

```powershell
.\.venv\Scripts\python.exe .\src\simulator.py --mode fault_scenario --machines 2 --interval 1 --seed 42 --iterations 3 --jsonl .\reports\simulated_events.jsonl
```

Available options include `--machines`, `--interval`, `--seed`, `--wear-min`, `--wear-max`, `--wear-increment`, `--iterations`, and `--jsonl`. Sensor value ranges are bounded by observed AI4I dataset ranges; normal readings use narrower ranges, while `fault_scenario` explores selected unusual combinations. A scenario never forces the model to predict failure.

Run the simulator checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
