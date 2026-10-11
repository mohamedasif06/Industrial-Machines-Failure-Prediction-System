"""Phase 4 simulator checks using the existing Phase 3 inference artifact."""

import json
import sys
import unittest
from io import StringIO
from pathlib import Path

PROJECT_ROOT_FOR_TESTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT_FOR_TESTS / "src"))

from inference import predict_failure
from project_utils import INPUT_FEATURES, PROJECT_ROOT
from simulator import (
    SimulatorConfig,
    SyntheticSensorSimulator,
    build_argument_parser,
    run_simulation,
)


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.config = SimulatorConfig(machine_count=2, seed=1234, iterations=1)
        self.simulator = SyntheticSensorSimulator(self.config)

    def test_feature_names_and_order_are_exact(self):
        reading = self.simulator.generate_reading(self.simulator.machines[0])
        self.assertEqual(list(reading), INPUT_FEATURES)

    def test_default_interval_is_two_seconds_in_config_and_cli(self):
        self.assertEqual(SimulatorConfig().interval_seconds, 2.0)
        self.assertEqual(build_argument_parser().parse_args([]).interval, 2.0)

    def test_type_uses_saved_mapping_categories(self):
        metadata = json.loads((PROJECT_ROOT / "models" / "metadata.json").read_text(encoding="utf-8"))
        allowed_types = set(metadata["type_mapping"])
        for machine in self.simulator.machines:
            self.assertIn(machine.machine_type, allowed_types)

    def test_sensor_values_are_within_plausible_ranges(self):
        reading = self.simulator.generate_reading(self.simulator.machines[0])
        self.simulator.validate_reading(reading)
        self.assertGreaterEqual(reading["Air temperature [K]"], 295.3)
        self.assertLessEqual(reading["Air temperature [K]"], 304.5)
        self.assertGreaterEqual(reading["Process temperature [K]"], 305.7)
        self.assertLessEqual(reading["Process temperature [K]"], 313.8)
        self.assertGreaterEqual(reading["Rotational speed [rpm]"], 1168)
        self.assertLessEqual(reading["Rotational speed [rpm]"], 2886)
        self.assertGreaterEqual(reading["Torque [Nm]"], 3.8)
        self.assertLessEqual(reading["Torque [Nm]"], 76.6)

    def test_tool_wear_increases_and_respects_bounds(self):
        config = SimulatorConfig(machine_count=1, seed=7, wear_min=1.0, wear_max=1.1, wear_increment=0.05)
        simulator = SyntheticSensorSimulator(config)
        machine = simulator.machines[0]
        machine.tool_wear = 1.02
        before = machine.tool_wear
        first = simulator.generate_reading(machine)["Tool wear [min]"]
        second = simulator.generate_reading(machine)["Tool wear [min]"]
        self.assertGreaterEqual(first, before)
        self.assertGreaterEqual(second, first)
        self.assertLessEqual(second, config.wear_max)

    def test_existing_saved_model_inference_returns_valid_output(self):
        reading = self.simulator.generate_reading(self.simulator.machines[0])
        prediction = predict_failure(reading)
        self.assertIn(prediction["predicted_class"], (0, 1))
        self.assertIn("estimated_failure_probability", prediction)
        self.assertGreaterEqual(prediction["estimated_failure_probability"], 0.0)
        self.assertLessEqual(prediction["estimated_failure_probability"], 1.0)

    def test_fixed_seed_reproduces_generated_readings(self):
        first = SyntheticSensorSimulator(SimulatorConfig(machine_count=3, seed=99))
        second = SyntheticSensorSimulator(SimulatorConfig(machine_count=3, seed=99))
        readings_a = [first.generate_reading(machine) for machine in first.machines]
        readings_b = [second.generate_reading(machine) for machine in second.machines]
        self.assertEqual(readings_a, readings_b)

    def test_mixed_mode_assigns_stable_per_machine_scenarios(self):
        config = SimulatorConfig(machine_count=4, mode="mixed", seed=12)
        first = SyntheticSensorSimulator(config)
        second = SyntheticSensorSimulator(config)
        assignments = [(machine.machine_id, machine.simulation_mode) for machine in first.machines]
        self.assertEqual(assignments, [
            ("SIM-MACHINE-001", "normal"),
            ("SIM-MACHINE-002", "fault_scenario"),
            ("SIM-MACHINE-003", "normal"),
            ("SIM-MACHINE-004", "fault_scenario"),
        ])
        self.assertEqual(assignments, [(machine.machine_id, machine.simulation_mode) for machine in second.machines])

    def test_explicit_mixed_assignment_and_authentic_inference_per_event(self):
        simulator = SyntheticSensorSimulator(SimulatorConfig(
            machine_count=2,
            mode="mixed",
            machine_modes=("normal", "fault_scenario"),
            seed=12,
        ))
        actual_predictions = []

        def recording_predictor(features):
            prediction = predict_failure(features)
            actual_predictions.append(prediction)
            return prediction

        events = simulator.generate_events(recording_predictor)
        self.assertEqual(len(actual_predictions), len(events))
        self.assertEqual([event["simulation_mode"] for event in events], ["normal", "fault_scenario"])
        self.assertEqual([event["predicted_class"] for event in events], [item["predicted_class"] for item in actual_predictions])
        self.assertEqual([event["machine_id"] for event in events], ["SIM-MACHINE-001", "SIM-MACHINE-002"])
        self.assertTrue(all(event["simulated"] for event in events))
        self.assertEqual(len({event["timestamp"] for event in events}), 2)

    def test_keyboard_interrupt_shuts_down_cleanly(self):
        output = StringIO()
        simulator = SyntheticSensorSimulator(SimulatorConfig(machine_count=2, seed=1234))

        def interrupt(_seconds):
            raise KeyboardInterrupt

        ticks = run_simulation(
            simulator,
            predictor=lambda _features: {"predicted_class": 0, "model_name": "test"},
            sleep_function=interrupt,
            output=output,
            error_output=StringIO(),
        )
        self.assertEqual(ticks, 1)
        self.assertIn("stopped cleanly", output.getvalue())

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            SyntheticSensorSimulator(SimulatorConfig(machine_count=0))
        with self.assertRaises(ValueError):
            SyntheticSensorSimulator(SimulatorConfig(interval_seconds=0))
        with self.assertRaises(ValueError):
            SyntheticSensorSimulator(SimulatorConfig(wear_min=2, wear_max=1))
        with self.assertRaises(ValueError):
            SyntheticSensorSimulator(SimulatorConfig(mode="surprise"))
        with self.assertRaises(ValueError):
            SyntheticSensorSimulator(SimulatorConfig(machine_count=1, mode="mixed"))


if __name__ == "__main__":
    unittest.main()
