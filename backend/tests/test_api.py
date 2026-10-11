"""API, store, simulator lifecycle, WebSocket, and saved-model integration checks."""

import asyncio
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.main import create_app
from app.services.inference_service import InferenceService
from app.services.telemetry_service import TelemetryService


FEATURES = {
    "Type": "L",
    "Air temperature [K]": 300.0,
    "Process temperature [K]": 310.0,
    "Rotational speed [rpm]": 1500,
    "Torque [Nm]": 40.0,
    "Tool wear [min]": 100,
}


def event(machine_id="SIM-A", timestamp="2026-10-10T10:00:00.000Z", predicted_class=0):
    return {
        "timestamp": timestamp,
        "session_id": "unassigned",
        "machine_id": machine_id,
        "simulation_mode": "normal",
        "simulated": True,
        **FEATURES,
        "predicted_class": predicted_class,
        "predicted_label": "failure" if predicted_class else "no failure",
        "model_name": "XGBoost",
        "estimated_failure_probability": 0.01 if predicted_class == 0 else 0.8,
    }


class FakeInference:
    def __init__(self):
        self.received = None
        self.available = True

    def availability(self):
        return self.available, "XGBoost", "test model status"

    def predict(self, values):
        self.received = values
        return {
            "predicted_class": 0,
            "predicted_label": "no failure",
            "model_name": "XGBoost",
            "probability_note": "test estimate",
            "estimated_failure_probability": 0.01,
        }


def make_client(inference=None, telemetry=None):
    inference = inference or FakeInference()
    telemetry = telemetry or TelemetryService(history_limit=20)
    return TestClient(create_app(inference, telemetry)), inference, telemetry


def test_health_reports_model_availability():
    client, _, _ = make_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["model_available"] is True
    assert response.json()["recommended_model"] == "XGBoost"


def test_prediction_accepts_exactly_six_inputs_and_calls_inference():
    client, inference, _ = make_client()
    response = client.post("/api/predict", json=FEATURES)
    assert response.status_code == 200
    assert response.json()["predicted_class"] == 0
    assert list(inference.received) == list(FEATURES)


def test_prediction_rejects_missing_extra_invalid_and_nonfinite_values():
    client, _, _ = make_client()
    missing = dict(FEATURES)
    missing.pop("Torque [Nm]")
    extra = {**FEATURES, "UDI": 1}
    invalid_type = {**FEATURES, "Type": "unknown"}
    for body in (missing, extra, invalid_type):
        assert client.post("/api/predict", json=body).status_code == 422
    nonfinite = {**FEATURES, "Torque [Nm]": "NaN"}
    assert client.post("/api/predict", json=nonfinite).status_code == 422


def test_unavailable_model_returns_service_unavailable():
    inference = FakeInference()
    inference.available = False
    client, _, _ = make_client(inference)
    assert client.post("/api/predict", json=FEATURES).status_code == 503


def test_empty_history_and_machine_not_found():
    client, _, _ = make_client()
    assert client.get("/api/events").json() == {"event_count": 0, "events": []}
    assert client.get("/api/machines").json() == {
        "machine_count": 0, "session_id": None, "machines_with_readings": 0, "machines": [],
    }
    assert client.get("/api/machines/UNKNOWN").status_code == 404


def test_latest_machine_aggregation_and_event_endpoints():
    telemetry = TelemetryService(history_limit=10)
    asyncio.run(telemetry.ingest(event("SIM-A", "2026-10-10T10:00:00.000Z", 0)))
    asyncio.run(telemetry.ingest(event("SIM-A", "2026-10-10T10:00:05.000Z", 1)))
    asyncio.run(telemetry.ingest(event("SIM-B", "2026-10-10T10:00:02.000Z", 0)))
    client, _, _ = make_client(telemetry=telemetry)
    machines = client.get("/api/machines").json()
    assert machines["machine_count"] == 2
    latest_a = client.get("/api/machines/SIM-A").json()
    assert latest_a["latest_event"]["predicted_class"] == 1
    events = client.get("/api/events?limit=2").json()
    assert events["event_count"] == 2
    assert events["events"][0]["machine_id"] == "SIM-A"


def test_event_store_is_bounded_and_deduplicates():
    telemetry = TelemetryService(history_limit=2)
    first = event("SIM-A", "2026-10-10T10:00:00.000Z")
    assert asyncio.run(telemetry.ingest(first)) is True
    assert asyncio.run(telemetry.ingest(first)) is False
    asyncio.run(telemetry.ingest(event("SIM-B", "2026-10-10T10:00:01.000Z")))
    asyncio.run(telemetry.ingest(event("SIM-C", "2026-10-10T10:00:02.000Z")))
    assert len(asyncio.run(telemetry.recent_events(10))) == 2


def test_alert_policy_configuration_requires_positive_integers():
    for options in (
        {"alert_activation_threshold": 0},
        {"alert_recovery_threshold": -1},
        {"alert_activation_threshold": 1.5},
        {"alert_limit": True},
    ):
        try:
            TelemetryService(**options)
        except ValueError:
            continue
        raise AssertionError(f"Invalid alert policy configuration was accepted: {options}")


def test_managed_alert_confirmation_updates_one_episode_per_machine_and_preserves_events():
    telemetry = TelemetryService(history_limit=20, alert_activation_threshold=2, alert_recovery_threshold=3)

    async def add_events():
        assert await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:00Z", 1)) is True
        # Replayed telemetry identity must not advance the alert confirmation.
        assert await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:00Z", 1)) is False
        assert (await telemetry.alert_snapshot())["active_count"] == 0
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:05Z", 1))
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:10Z", 1))
        await telemetry.ingest(event("SIM-B", "2026-10-10T10:00:11Z", 1))
        await telemetry.ingest(event("SIM-B", "2026-10-10T10:00:12Z", 1))
        return await telemetry.alert_snapshot(), await telemetry.recent_events(20)

    snapshot, events = asyncio.run(add_events())
    assert snapshot["active_count"] == 2
    assert snapshot["resolved_count"] == 0
    assert len(events) == 5  # all unique telemetry is retained, including pending confirmation
    assert len(snapshot["alerts"]) == 2
    alert_a = next(alert for alert in snapshot["alerts"] if alert.machine_id == "SIM-A")
    assert alert_a.occurrence_count == 3
    assert alert_a.first_seen.isoformat().startswith("2026-10-10T10:00:00")
    assert alert_a.last_seen.isoformat().startswith("2026-10-10T10:00:10")
    assert alert_a.status == "active"


def test_managed_alert_activation_resets_and_recovery_resolves_then_allows_new_episode():
    telemetry = TelemetryService(history_limit=30, alert_activation_threshold=2, alert_recovery_threshold=3)

    async def run_lifecycle():
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:00Z", 1))
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:01Z", 0))
        assert (await telemetry.alert_snapshot())["alerts"] == []
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:02Z", 1))
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:03Z", 1))
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:04Z", 0))
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:05Z", 0))
        assert (await telemetry.alert_snapshot())["active_count"] == 1
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:06Z", 0))
        resolved_snapshot = await telemetry.alert_snapshot()
        assert resolved_snapshot["active_count"] == 0
        assert resolved_snapshot["resolved_count"] == 1
        resolved = resolved_snapshot["alerts"][0]
        assert resolved.status == "resolved"
        assert resolved.resolved_at.isoformat().startswith("2026-10-10T10:00:06")
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:07Z", 1))
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:08Z", 1))
        return resolved, await telemetry.alert_snapshot()

    resolved, final = asyncio.run(run_lifecycle())
    assert final["active_count"] == 1
    assert final["resolved_count"] == 1
    assert len({alert.alert_id for alert in final["alerts"]}) == 2
    new_alert = next(alert for alert in final["alerts"] if alert.status == "active")
    assert new_alert.alert_id != resolved.alert_id
    assert new_alert.alert_id.endswith(":2")
    assert new_alert.occurrence_count == 2


def test_alert_snapshot_endpoint_returns_current_managed_state():
    telemetry = TelemetryService()

    async def add_confirmed_alert():
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:00Z", 1))
        await telemetry.ingest(event("SIM-A", "2026-10-10T10:00:01Z", 1))

    asyncio.run(add_confirmed_alert())
    client, _, _ = make_client(telemetry=telemetry)
    response = client.get("/api/alerts")
    assert response.status_code == 200
    assert response.json()["active_count"] == 1
    assert response.json()["resolved_count"] == 0
    assert response.json()["alerts"][0]["occurrence_count"] == 2


def test_websocket_publishes_alert_lifecycle_and_reconnect_snapshot(monkeypatch):
    import app.services.telemetry_service as telemetry_module

    predictions = [1, 1, 1, 0, 0, 0, 1, 1]

    class SequenceSimulator:
        def __init__(self, config):
            self.config = config
            self.generated = False

        def generate_events(self):
            if self.generated:
                return []
            self.generated = True
            return [event("SIM-A", f"2026-10-10T10:00:{index:02d}Z", predicted_class)
                    for index, predicted_class in enumerate(predictions, start=1)]

    monkeypatch.setattr(telemetry_module, "SyntheticSensorSimulator", SequenceSimulator)
    client, _, telemetry = make_client(telemetry=TelemetryService(history_limit=50))
    with client:
        with client.websocket_connect("/ws/telemetry") as websocket:
            assert websocket.receive_json()["event_type"] == "session.snapshot"
            started = client.post("/api/simulator/start", json={"machine_count": 1, "interval_seconds": 60})
            assert started.status_code == 202
            start_snapshot = websocket.receive_json()
            assert start_snapshot["event_type"] == "session.snapshot"
            assert start_snapshot["status"]["session_id"] == started.json()["session_id"]
            messages = [websocket.receive_json() for _ in range(14)]
            telemetry_messages = [message for message in messages if "timestamp" in message]
            alert_messages = [message for message in messages if message.get("event_type", "").startswith("alert.")]
            assert len(telemetry_messages) == 8
            assert [message["event_type"] for message in alert_messages] == [
                "alert.created", "alert.updated", "alert.updated", "alert.updated",
                "alert.resolved", "alert.created",
            ]
            assert client.get("/api/events?limit=50").json()["event_count"] == 8
            assert client.get("/api/alerts").json()["active_count"] == 1
        # A fresh client can recover the same active and resolved episodes from REST.
        with client.websocket_connect("/ws/telemetry"):
            snapshot = client.get("/api/alerts").json()
            assert snapshot["active_count"] == 1
            assert snapshot["resolved_count"] == 1
            assert len(snapshot["alerts"]) == 2
            assert len(telemetry._events) == 8
        assert client.post("/api/simulator/stop").json()["running"] is False


def test_existing_saved_model_inference_integration():
    client = TestClient(create_app(InferenceService(), TelemetryService()))
    response = client.post("/api/predict", json=FEATURES)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["predicted_class"] in (0, 1)
    assert 0 <= body["estimated_failure_probability"] <= 1


def test_simulator_websocket_delivery_and_disconnect(monkeypatch):
    import app.services.telemetry_service as telemetry_module

    class FakeSimulator:
        def __init__(self, config):
            self.config = config
            self.calls = 0

        def generate_events(self):
            self.calls += 1
            return [event(timestamp=f"2026-10-10T10:00:{self.calls:02d}.000Z")]

    monkeypatch.setattr(telemetry_module, "SyntheticSensorSimulator", FakeSimulator)
    client, _, telemetry = make_client()
    with client:
        with client.websocket_connect("/ws/telemetry") as websocket:
            assert websocket.receive_json()["event_type"] == "session.snapshot"
            started = client.post("/api/simulator/start", json={"machine_count": 1, "interval_seconds": 60})
            assert started.status_code == 202
            assert started.json()["mode"] == "normal"
            assert client.post("/api/simulator/start", json={"machine_count": 1}).status_code == 409
            assert websocket.receive_json()["event_type"] == "session.snapshot"
            received = websocket.receive_json()
            assert received["machine_id"] == "SIM-A"
            assert received["simulated"] is True
            stopped = client.post("/api/simulator/stop")
            assert stopped.status_code == 200
            assert stopped.json()["running"] is False
    assert len(telemetry._clients) == 0


def test_existing_simulator_runs_inference_and_populates_backend_history():
    """Exercise actual src/simulator.py and saved inference through the backend."""
    client, _, _ = make_client(InferenceService(), TelemetryService(history_limit=50))
    with client:
        with client.websocket_connect("/ws/telemetry") as websocket:
            assert websocket.receive_json()["event_type"] == "session.snapshot"
            started = client.post("/api/simulator/start", json={
                "machine_count": 3,
                "interval_seconds": 60,
                "seed": 23,
            })
            assert started.status_code == 202, started.text
            assert websocket.receive_json()["event_type"] == "session.snapshot"
            received_events = [websocket.receive_json() for _ in range(3)]
            assert {event["session_id"] for event in received_events} == {started.json()["session_id"]}
            assert [event["machine_id"] for event in received_events] == [
                "SIM-MACHINE-001", "SIM-MACHINE-002", "SIM-MACHINE-003",
            ]
            for received in received_events:
                assert received["simulated"] is True
                assert list(key for key in received if key in FEATURES) == list(FEATURES)
                assert not {"UDI", "Product ID", "TWF", "HDF", "PWF", "OSF", "RNF"}.intersection(received)
                assert received["predicted_class"] in (0, 1)
                assert 0 <= received["estimated_failure_probability"] <= 1
            machines = client.get("/api/machines").json()
            assert machines["machine_count"] == 3
            assert machines["machines_with_readings"] == 3
            history = client.get("/api/events").json()
            assert history["event_count"] == 3
            assert history["events"] == list(reversed(received_events))
            stopped = client.post("/api/simulator/stop")
            assert stopped.json()["running"] is False


def test_mixed_simulator_publishes_machine_specific_modes_and_predictions():
    client, _, _ = make_client(InferenceService(), TelemetryService(history_limit=50))
    with client:
        with client.websocket_connect("/ws/telemetry") as websocket:
            assert websocket.receive_json()["event_type"] == "session.snapshot"
            started = client.post("/api/simulator/start", json={
                "mode": "mixed",
                "machine_count": 2,
                "machine_modes": ["normal", "fault_scenario"],
                "interval_seconds": 60,
                "seed": 23,
            })
            assert started.status_code == 202, started.text
            assert started.json()["mode"] == "mixed"
            assert websocket.receive_json()["event_type"] == "session.snapshot"
            events = [websocket.receive_json(), websocket.receive_json()]
            assert [item["machine_id"] for item in events] == ["SIM-MACHINE-001", "SIM-MACHINE-002"]
            assert [item["simulation_mode"] for item in events] == ["normal", "fault_scenario"]
            assert len({item["timestamp"] for item in events}) == 2
            assert all(item["simulated"] is True and item["predicted_class"] in (0, 1) for item in events)
            assert client.get("/api/machines").json()["machine_count"] == 2
            assert client.get("/api/events").json()["event_count"] == 2
            assert client.post("/api/simulator/stop").json()["running"] is False
            assert websocket.receive_json()["event_type"] == "session.snapshot"


def test_mixed_simulator_request_validates_machine_assignments():
    client, _, _ = make_client()
    assert client.post("/api/simulator/start", json={"mode": "mixed", "machine_count": 1}).status_code == 422
    assert client.post("/api/simulator/start", json={
        "mode": "mixed", "machine_count": 2, "machine_modes": ["normal"],
    }).status_code == 422
    assert client.post("/api/simulator/start", json={
        "mode": "mixed", "machine_count": 2, "machine_modes": ["normal", "normal"],
    }).status_code == 422


def test_simulator_interval_default_propagation_and_stop_status(monkeypatch):
    import app.services.telemetry_service as telemetry_module
    from app.schemas import SimulatorStartRequest
    from simulator import SimulatorConfig, build_argument_parser

    class QuietSimulator:
        def __init__(self, config):
            self.config = config
            self.machines = []

        def generate_events(self):
            return []

    monkeypatch.setattr(telemetry_module, "SyntheticSensorSimulator", QuietSimulator)
    assert SimulatorStartRequest().interval_seconds == 2.0
    assert SimulatorConfig().interval_seconds == 2.0
    assert build_argument_parser().parse_args([]).interval == 2.0

    client, _, _ = make_client()
    with client:
        default_start = client.post("/api/simulator/start", json={})
        assert default_start.status_code == 202
        assert default_start.json()["interval_seconds"] == 2.0
        assert client.get("/api/simulator/status").json()["interval_seconds"] == 2.0
        stopped = client.post("/api/simulator/stop").json()
        assert stopped["running"] is False
        assert stopped["interval_seconds"] == 2.0

        configured_start = client.post("/api/simulator/start", json={"interval_seconds": 0.25})
        assert configured_start.status_code == 202
        assert configured_start.json()["interval_seconds"] == 0.25
        assert client.get("/api/simulator/status").json()["interval_seconds"] == 0.25
        configured_stop = client.post("/api/simulator/stop").json()
        assert configured_stop["running"] is False
        assert configured_stop["interval_seconds"] == 0.25
def test_simulation_sessions_scope_machine_counts_and_preserve_history(monkeypatch):
    import app.services.telemetry_service as telemetry_module

    class SessionSimulator:
        def __init__(self, config):
            self.config = config
            self.machines = [type("Machine", (), {"machine_id": f"SIM-MACHINE-{index + 1:03d}"})()
                             for index in range(config.machine_count)]
            self.tick = 0

        def generate_events(self):
            self.tick += 1
            return [event(
                machine.machine_id,
                f"2026-10-11T10:{self.tick:02d}:{index:02d}Z",
            ) | {"session_id": self.config.session_id}
                for index, machine in enumerate(self.machines, start=1)]

    monkeypatch.setattr(telemetry_module, "SyntheticSensorSimulator", SessionSimulator)
    client, _, telemetry = make_client(telemetry=TelemetryService(history_limit=100))
    with client:
        with client.websocket_connect("/ws/telemetry") as websocket:
            assert websocket.receive_json()["event_type"] == "session.snapshot"
            first = client.post("/api/simulator/start", json={"machine_count": 10, "interval_seconds": 60})
            assert first.status_code == 202
            assert websocket.receive_json()["event_type"] == "session.snapshot"
            first_events = [websocket.receive_json() for _ in range(10)]
            first_session = first.json()["session_id"]
            assert {item["session_id"] for item in first_events} == {first_session}
            assert first.json()["machine_count"] == 10
            assert first.json()["active_machine_count"] == 10
            assert client.post("/api/simulator/stop").json()["running"] is False
            assert websocket.receive_json()["event_type"] == "session.snapshot"

            second = client.post("/api/simulator/start", json={"machine_count": 3, "interval_seconds": 60})
            assert second.status_code == 202
            assert websocket.receive_json()["event_type"] == "session.snapshot"
            second_events = [websocket.receive_json() for _ in range(3)]
            second_session = second.json()["session_id"]
            assert second_session != first_session
            assert {item["session_id"] for item in second_events} == {second_session}
            assert second.json()["machine_count"] == 3
            assert second.json()["machine_ids"] == [f"SIM-MACHINE-{i:03d}" for i in range(1, 4)]

            machines = client.get("/api/machines").json()
            assert machines["session_id"] == second_session
            assert machines["machine_count"] == 3
            assert [machine["machine_id"] for machine in machines["machines"]] == second.json()["machine_ids"]
            history = client.get("/api/events?limit=100").json()
            assert history["event_count"] == 13
            assert {item["session_id"] for item in history["events"]} == {first_session, second_session}
            assert second.json()["historical_machine_count"] == 10
            assert asyncio.run(telemetry.ingest(first_events[0])) is False
            assert client.post("/api/simulator/stop").json()["active_machine_count"] == 0


def test_simulator_error_is_reported(monkeypatch):
    import app.services.telemetry_service as telemetry_module

    class BrokenSimulator:
        def __init__(self, config):
            self.config = config

        def generate_events(self):
            raise RuntimeError("synthetic inference failed")

    monkeypatch.setattr(telemetry_module, "SyntheticSensorSimulator", BrokenSimulator)
    client, _, _ = make_client()
    assert client.post("/api/simulator/start", json={"machine_count": 0}).status_code == 422
    assert client.post("/api/simulator/start", json={}).status_code == 202
    deadline = time.monotonic() + 3
    status = None
    while time.monotonic() < deadline:
        status = client.get("/api/simulator/status").json()
        if status["error"]:
            break
        time.sleep(0.02)
    assert status["running"] is False
    assert status["error"] == "synthetic inference failed"
