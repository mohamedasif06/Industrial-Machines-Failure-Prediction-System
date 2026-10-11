"""Continuous synthetic sensor simulator for the saved Phase 3 model.

All values are synthetic and are not replayed from the historical CSV. The
sensor limits below are bounded by observed AI4I dataset minima and maxima;
normal-mode readings use narrower operating ranges. A fault_scenario explores
unusual combinations within those observed limits and does not force a model
prediction or represent a confirmed real-world failure.
"""

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TextIO

import numpy as np

from inference import predict_failure
from project_utils import INPUT_FEATURES, PROJECT_ROOT


METADATA_PATH = PROJECT_ROOT / "models" / "metadata.json"

# Observed data bounds: air 295.3–304.5 K, process 305.7–313.8 K,
# speed 1168–2886 rpm, torque 3.8–76.6 Nm, tool wear 0–253 min.
AIR_TEMPERATURE_BOUNDS = (295.3, 304.5)
PROCESS_TEMPERATURE_BOUNDS = (305.7, 313.8)
ROTATIONAL_SPEED_BOUNDS = (1168.0, 2886.0)
TORQUE_BOUNDS = (3.8, 76.6)


@dataclass(frozen=True)
class SimulatorConfig:
    machine_count: int = 3
    interval_seconds: float = 2.0
    mode: str = "normal"
    seed: int | None = None
    wear_min: float = 0.0
    wear_max: float = 253.0
    wear_increment: float = 0.01
    iterations: int | None = None
    jsonl_path: Path | None = None
    machine_modes: tuple[str, ...] | None = None
    session_id: str | None = None

    def validate(self) -> None:
        if self.machine_count < 1:
            raise ValueError("machine_count must be at least 1.")
        if not np.isfinite(self.interval_seconds) or self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be a finite value greater than 0.")
        if self.mode not in {"normal", "fault_scenario", "mixed"}:
            raise ValueError("mode must be 'normal', 'fault_scenario', or 'mixed'.")
        if self.machine_modes is not None:
            allowed_machine_modes = {"normal", "fault_scenario"}
            if self.mode != "mixed":
                raise ValueError("machine_modes can only be configured when mode='mixed'.")
            if len(self.machine_modes) != self.machine_count:
                raise ValueError("machine_modes must contain exactly one mode per machine.")
            if any(machine_mode not in allowed_machine_modes for machine_mode in self.machine_modes):
                raise ValueError("Each machine mode must be 'normal' or 'fault_scenario'.")
            if self.machine_count > 1 and len(set(self.machine_modes)) < 2:
                raise ValueError("Mixed mode must assign both normal and fault_scenario to its machines.")
        elif self.mode == "mixed" and self.machine_count < 2:
            raise ValueError("Mixed mode requires at least two machines.")
        if not np.isfinite(self.wear_min) or not np.isfinite(self.wear_max) or self.wear_max <= self.wear_min:
            raise ValueError("wear_max must be finite and greater than finite wear_min.")
        if self.wear_min < 0 or self.wear_max > 253:
            raise ValueError("Wear bounds must stay within the observed 0–253 min range.")
        if not np.isfinite(self.wear_increment) or self.wear_increment <= 0:
            raise ValueError("wear_increment must be a finite value greater than 0.")
        if self.iterations is not None and self.iterations < 1:
            raise ValueError("iterations must be at least 1 when provided.")


@dataclass
class MachineState:
    machine_id: str
    machine_type: str
    tool_wear: float
    simulation_mode: str = "normal"


class SyntheticSensorSimulator:
    """Generate independent, reproducible synthetic readings for machines."""

    def __init__(self, config: SimulatorConfig):
        config.validate()
        if not METADATA_PATH.is_file():
            raise FileNotFoundError(f"Saved model metadata not found: {METADATA_PATH}")
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        if metadata.get("feature_order") != INPUT_FEATURES:
            raise ValueError("Saved model metadata feature order does not match simulator inputs.")
        type_mapping = metadata.get("type_mapping")
        if not isinstance(type_mapping, dict) or not type_mapping:
            raise ValueError("Saved model metadata does not contain a Type mapping.")

        self.config = config
        self.rng = random.Random(config.seed)
        self.type_categories = tuple(type_mapping.keys())
        if config.machine_modes is not None:
            machine_modes = config.machine_modes
        elif config.mode == "mixed":
            # Deterministic alternating assignment: machine 1 normal, 2 fault,
            # 3 normal, etc. Explicit assignments remain configurable above.
            machine_modes = tuple(
                "normal" if index % 2 == 0 else "fault_scenario"
                for index in range(config.machine_count)
            )
        else:
            machine_modes = (config.mode,) * config.machine_count
        self.machines = [
            MachineState(
                machine_id=f"SIM-MACHINE-{index + 1:03d}",
                machine_type=self.rng.choice(self.type_categories),
                tool_wear=self.rng.uniform(config.wear_min, min(config.wear_max, max(config.wear_min, 180.0))),
                simulation_mode=machine_modes[index],
            )
            for index in range(config.machine_count)
        ]

    def generate_reading(self, machine: MachineState) -> dict[str, Any]:
        """Generate exactly the six agreed features in the required order."""
        if machine.simulation_mode == "normal":
            air_temperature = self.rng.uniform(298.0, 302.0)
            process_temperature = self._correlated_process_temperature(air_temperature, 10.0, 0.35)
            rotational_speed = self._clip(self.rng.gauss(1538.8, 100.0), 1250.0, 1850.0)
            torque = self._clip(self.rng.gauss(40.0, 8.0), 18.0, 62.0)
        else:
            scenario = self.rng.choice(("thermal_edge", "high_load", "cool_high_speed"))
            if scenario == "thermal_edge":
                air_temperature = self.rng.uniform(303.0, AIR_TEMPERATURE_BOUNDS[1])
                process_temperature = self._correlated_process_temperature(air_temperature, 10.0, 0.3)
                rotational_speed = self._clip(self.rng.gauss(1450.0, 90.0), 1168.0, 1800.0)
                torque = self.rng.uniform(48.0, 70.0)
            elif scenario == "high_load":
                air_temperature = self.rng.uniform(299.0, 302.0)
                process_temperature = self._correlated_process_temperature(air_temperature, 10.0, 0.4)
                rotational_speed = self.rng.uniform(1168.0, 1300.0)
                torque = self.rng.uniform(65.0, TORQUE_BOUNDS[1])
            else:
                air_temperature = self.rng.uniform(AIR_TEMPERATURE_BOUNDS[0], 297.0)
                process_temperature = self._correlated_process_temperature(air_temperature, 10.0, 0.35)
                rotational_speed = self.rng.uniform(2300.0, ROTATIONAL_SPEED_BOUNDS[1])
                torque = self.rng.uniform(TORQUE_BOUNDS[0], 20.0)

        increment = self.config.wear_increment * self.rng.uniform(0.75, 1.25)
        machine.tool_wear = min(self.config.wear_max, max(self.config.wear_min, machine.tool_wear + increment))

        reading = {
            "Type": machine.machine_type,
            "Air temperature [K]": round(air_temperature, 2),
            "Process temperature [K]": round(process_temperature, 2),
            "Rotational speed [rpm]": int(round(rotational_speed)),
            "Torque [Nm]": round(torque, 2),
            "Tool wear [min]": round(machine.tool_wear, 3),
        }
        self.validate_reading(reading)
        return reading

    @staticmethod
    def _clip(value: float, minimum: float, maximum: float) -> float:
        return min(max(value, minimum), maximum)

    def _correlated_process_temperature(self, air_temperature: float, difference_mean: float, difference_std: float) -> float:
        difference = max(7.0, self.rng.gauss(difference_mean, difference_std))
        return self._clip(
            air_temperature + difference,
            PROCESS_TEMPERATURE_BOUNDS[0],
            PROCESS_TEMPERATURE_BOUNDS[1],
        )

    def validate_reading(self, reading: dict[str, Any]) -> None:
        if list(reading) != INPUT_FEATURES:
            raise ValueError(f"Generated feature order mismatch: {list(reading)}")
        if reading["Type"] not in self.type_categories:
            raise ValueError(f"Generated Type {reading['Type']!r} is not in the saved Type mapping.")
        numeric_bounds = {
            "Air temperature [K]": AIR_TEMPERATURE_BOUNDS,
            "Process temperature [K]": PROCESS_TEMPERATURE_BOUNDS,
            "Rotational speed [rpm]": ROTATIONAL_SPEED_BOUNDS,
            "Torque [Nm]": TORQUE_BOUNDS,
            "Tool wear [min]": (self.config.wear_min, self.config.wear_max),
        }
        for name, (minimum, maximum) in numeric_bounds.items():
            value = reading[name]
            if not isinstance(value, (int, float)) or not np.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f"Generated value for {name!r} is outside allowed range: {value!r}.")

    def generate_events(self, predictor: Callable[[dict[str, Any]], dict[str, Any]] = predict_failure) -> list[dict[str, Any]]:
        """Generate a complete simulation tick, using saved-model inference."""
        events = []
        for machine in self.machines:
            features = self.generate_reading(machine)
            try:
                prediction = predictor(features)
                predicted_class = int(prediction["predicted_class"])
                if predicted_class not in (0, 1):
                    raise ValueError(f"Inference returned invalid class {predicted_class}.")
                probability = prediction.get("estimated_failure_probability")
                if probability is not None and (
                    not isinstance(probability, (int, float))
                    or not np.isfinite(probability)
                    or not 0.0 <= probability <= 1.0
                ):
                    raise ValueError(f"Inference returned invalid estimated probability {probability!r}.")
            except Exception as error:
                raise RuntimeError(
                    f"Inference failed for {machine.machine_id}; simulator is stopping: {error}"
                ) from error

            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "machine_id": machine.machine_id,
                **({"session_id": self.config.session_id} if self.config.session_id else {}),
                "simulation_mode": machine.simulation_mode,
                "simulated": True,
                **features,
                "predicted_class": predicted_class,
                "predicted_label": prediction.get("predicted_label", "failure" if predicted_class else "no failure"),
                "model_name": prediction.get("model_name", "saved recommended model"),
            }
            if probability is not None:
                event["estimated_failure_probability"] = float(probability)
            events.append(event)
        return events


def print_event(event: dict[str, Any], output: TextIO = sys.stdout) -> None:
    probability = event.get("estimated_failure_probability")
    probability_text = f" | estimated p(failure)={probability:.3f}" if probability is not None else ""
    print(
        f"[{event['timestamp']}] SIMULATED {event['machine_id']} ({event['simulation_mode']}) "
        f"Type={event['Type']} air={event['Air temperature [K]']:.2f}K "
        f"process={event['Process temperature [K]']:.2f}K "
        f"speed={event['Rotational speed [rpm]']}rpm torque={event['Torque [Nm]']:.2f}Nm "
        f"wear={event['Tool wear [min]']:.3f}min -> {event['predicted_label']} "
        f"(class {event['predicted_class']}){probability_text}",
        file=output,
        flush=True,
    )


def run_simulation(
    simulator: SyntheticSensorSimulator,
    predictor: Callable[[dict[str, Any]], dict[str, Any]] = predict_failure,
    sleep_function: Callable[[float], None] = time.sleep,
    output: TextIO = sys.stdout,
    error_output: TextIO = sys.stderr,
) -> int:
    """Run until Ctrl+C or configured iteration count; return tick count."""
    jsonl_file = None
    if simulator.config.jsonl_path is not None:
        destination = simulator.config.jsonl_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        jsonl_file = destination.open("a", encoding="utf-8")
        print(f"Appending newline-delimited events to {destination}", file=output)

    print(
        f"Starting synthetic simulator: mode={simulator.config.mode}, "
        f"machines={simulator.config.machine_count}, interval={simulator.config.interval_seconds:g}s. "
        "Press Ctrl+C to stop.",
        file=output,
    )
    ticks = 0
    try:
        while simulator.config.iterations is None or ticks < simulator.config.iterations:
            events = simulator.generate_events(predictor)
            for event in events:
                print_event(event, output)
                if jsonl_file is not None:
                    jsonl_file.write(json.dumps(event, ensure_ascii=False) + "\n")
                    jsonl_file.flush()
            ticks += 1
            if simulator.config.iterations is None or ticks < simulator.config.iterations:
                sleep_function(simulator.config.interval_seconds)
    except KeyboardInterrupt:
        print("\nShutdown requested. Simulator stopped cleanly.", file=output)
    except RuntimeError as error:
        print(f"\nERROR: {error}", file=error_output)
        raise
    finally:
        if jsonl_file is not None:
            jsonl_file.close()
    return ticks


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate synthetic sensor events for the saved failure classifier.")
    parser.add_argument("--mode", choices=("normal", "fault_scenario", "mixed"), default="normal")
    parser.add_argument(
        "--machine-modes",
        default=None,
        help="Optional comma-separated per-machine modes for mixed mode, e.g. normal,fault_scenario,normal.",
    )
    parser.add_argument("--machines", type=int, default=3, help="Number of simulated machines (default: 3).")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between readings per machine (default: 2).")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed for reproducible synthetic readings.")
    parser.add_argument("--wear-min", type=float, default=0.0, help="Lower tool-wear bound in minutes (0–253).")
    parser.add_argument("--wear-max", type=float, default=253.0, help="Upper tool-wear bound in minutes (0–253).")
    parser.add_argument("--wear-increment", type=float, default=0.01, help="Mean tool-wear increment per reading in minutes.")
    parser.add_argument("--iterations", type=int, default=None, help="Optional number of ticks, useful for short demonstrations.")
    parser.add_argument("--jsonl", type=Path, default=None, help="Optional path for append-only newline-delimited JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    config = SimulatorConfig(
        machine_count=args.machines,
        interval_seconds=args.interval,
        mode=args.mode,
        machine_modes=tuple(part.strip() for part in args.machine_modes.split(",")) if args.machine_modes else None,
        seed=args.seed,
        wear_min=args.wear_min,
        wear_max=args.wear_max,
        wear_increment=args.wear_increment,
        iterations=args.iterations,
        jsonl_path=args.jsonl,
    )
    try:
        simulator = SyntheticSensorSimulator(config)
        run_simulation(simulator)
    except (ValueError, FileNotFoundError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
