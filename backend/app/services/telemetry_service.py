"""Bounded event history, latest-machine aggregation, WebSocket fanout, and simulator control."""

import asyncio
import sys
from uuid import uuid4
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder

from ..config import PROJECT_ROOT
from ..schemas import ManagedAlert, SimulatorStartRequest, TelemetryEvent

SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from simulator import SimulatorConfig, SyntheticSensorSimulator  # noqa: E402


class TelemetryService:
    """In-memory store that resets on process restart and deduplicates events."""

    def __init__(
        self,
        history_limit: int = 1000,
        alert_activation_threshold: int = 2,
        alert_recovery_threshold: int = 3,
        alert_limit: int = 1000,
    ):
        limits = (history_limit, alert_activation_threshold, alert_recovery_threshold, alert_limit)
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in limits):
            raise ValueError("Event and alert limits and thresholds must be positive integers.")
        self.history_limit = history_limit
        self.alert_activation_threshold = alert_activation_threshold
        self.alert_recovery_threshold = alert_recovery_threshold
        self.alert_limit = alert_limit
        self._events: OrderedDict[tuple[str, str, str], TelemetryEvent] = OrderedDict()
        self._seen_event_ids: OrderedDict[tuple[str, str, str], None] = OrderedDict()
        self._alerts: OrderedDict[str, ManagedAlert] = OrderedDict()
        self._active_alert_ids: dict[tuple[str, str, str], str] = {}
        self._episode_numbers: dict[tuple[str, str, str], int] = {}
        self._failure_streaks: dict[str, int] = {}
        self._pending_first_seen: dict[str, str] = {}
        self._recovery_streaks: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._clients: set[WebSocket] = set()
        self._simulator_task: asyncio.Task[None] | None = None
        self._simulator_config: SimulatorConfig | None = None
        self._simulator_error: str | None = None
        self._current_session_id: str | None = None
        self._session_machine_ids: list[str] = []
        self._session_config: SimulatorConfig | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        await websocket.send_json({"event_type": "session.snapshot", "status": self.simulator_status()})

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def ingest(self, value: dict[str, Any]) -> bool:
        """Retain every unique telemetry event and advance its managed alert episode."""
        event = TelemetryEvent.model_validate(value)
        identity = (event.session_id, event.machine_id, event.timestamp)
        async with self._lock:
            if self._current_session_id is not None and event.session_id != self._current_session_id:
                return False
            if identity in self._seen_event_ids:
                return False
            self._seen_event_ids[identity] = None
            while len(self._seen_event_ids) > self.history_limit * 2:
                self._seen_event_ids.popitem(last=False)
            self._events[identity] = event
            while len(self._events) > self.history_limit:
                self._events.popitem(last=False)
            alert_message = self._advance_alert_lifecycle(event)
        await self.broadcast(event)
        if alert_message is not None:
            await self.broadcast_alert(alert_message)
        return True

    def _advance_alert_lifecycle(self, event: TelemetryEvent) -> dict[str, Any] | None:
        machine_id = event.machine_id
        streak_key = f"{event.session_id}\u0000{machine_id}"
        condition_key = (event.session_id, machine_id, "failure_associated_prediction")
        active_alert_id = self._active_alert_ids.get(condition_key)

        if event.predicted_class == 1:
            self._failure_streaks[streak_key] = self._failure_streaks.get(streak_key, 0) + 1
            self._recovery_streaks[streak_key] = 0
            if active_alert_id is not None:
                current = self._alerts[active_alert_id]
                updated = current.model_copy(update={
                    "last_seen": self._event_datetime(event.timestamp),
                    "updated_at": self._event_datetime(event.timestamp),
                    "occurrence_count": current.occurrence_count + 1,
                    "simulation_mode": event.simulation_mode,
                    "latest_event": event,
                })
                self._alerts[active_alert_id] = updated
                return self._alert_message("alert.updated", updated)

            if self._failure_streaks[streak_key] == 1:
                self._pending_first_seen[streak_key] = event.timestamp
            if self._failure_streaks[streak_key] < self.alert_activation_threshold:
                return None

            episode = self._episode_numbers.get(condition_key, 0) + 1
            self._episode_numbers[condition_key] = episode
            alert_id = f"{event.session_id}:{machine_id}:failure_associated_prediction:{episode}"
            alert = ManagedAlert(
                alert_id=alert_id,
                session_id=event.session_id,
                machine_id=machine_id,
                condition="failure_associated_prediction",
                simulation_mode=event.simulation_mode,
                first_seen=self._event_datetime(self._pending_first_seen.get(streak_key, event.timestamp)),
                created_at=self._event_datetime(event.timestamp),
                last_seen=self._event_datetime(event.timestamp),
                updated_at=self._event_datetime(event.timestamp),
                occurrence_count=self._failure_streaks[streak_key],
                status="active",
                latest_event=event,
            )
            self._alerts[alert_id] = alert
            self._active_alert_ids[condition_key] = alert_id
            self._trim_alert_history()
            return self._alert_message("alert.created", alert)

        # A class-0 result breaks a pending activation streak.
        self._failure_streaks[streak_key] = 0
        self._pending_first_seen.pop(streak_key, None)
        if active_alert_id is None:
            self._recovery_streaks[streak_key] = 0
            return None

        self._recovery_streaks[streak_key] = self._recovery_streaks.get(streak_key, 0) + 1
        current = self._alerts[active_alert_id]
        recovery_confirmed = self._recovery_streaks[streak_key] >= self.alert_recovery_threshold
        updated = current.model_copy(update={
            "updated_at": self._event_datetime(event.timestamp),
            "latest_event": event,
            "status": "resolved" if recovery_confirmed else "active",
            "resolved_at": self._event_datetime(event.timestamp) if recovery_confirmed else None,
        })
        self._alerts[active_alert_id] = updated
        if recovery_confirmed:
            self._active_alert_ids.pop(condition_key, None)
            self._recovery_streaks[streak_key] = 0
            return self._alert_message("alert.resolved", updated)
        return self._alert_message("alert.updated", updated)

    @staticmethod
    def _alert_message(event_type: str, alert: ManagedAlert) -> dict[str, Any]:
        return {"event_type": event_type, "alert": jsonable_encoder(alert.model_dump(by_alias=True))}

    @staticmethod
    def _event_datetime(timestamp: str) -> datetime:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    def _trim_alert_history(self) -> None:
        while len(self._alerts) > self.alert_limit:
            removable = next((
                alert_id for alert_id, alert in self._alerts.items()
                if alert.status == "resolved"
            ), None)
            if removable is None:
                return  # Never evict an active alert merely to meet the soft cap.
            self._alerts.pop(removable)

    async def alert_snapshot(self) -> dict[str, Any]:
        async with self._lock:
            alerts = sorted(self._alerts.values(), key=lambda alert: alert.created_at, reverse=True)
            active_count = sum(
                alert.status == "active" and (self._current_session_id is None or alert.session_id == self._current_session_id)
                for alert in alerts
            )
            return {
                "active_count": active_count,
                "resolved_count": sum(alert.status == "resolved" for alert in alerts),
                "activation_threshold": self.alert_activation_threshold,
                "recovery_threshold": self.alert_recovery_threshold,
                "alerts": alerts,
            }

    async def broadcast(self, event: TelemetryEvent) -> None:
        stale_clients: list[WebSocket] = []
        for client in tuple(self._clients):
            try:
                await client.send_json(event.model_dump(by_alias=True))
            except Exception:
                stale_clients.append(client)
        for client in stale_clients:
            self.disconnect(client)

    async def broadcast_alert(self, message: dict[str, Any]) -> None:
        stale_clients: list[WebSocket] = []
        for client in tuple(self._clients):
            try:
                await client.send_json(message)
            except Exception:
                stale_clients.append(client)
        for client in stale_clients:
            self.disconnect(client)

    async def broadcast_session_snapshot(self) -> None:
        stale_clients: list[WebSocket] = []
        message = {"event_type": "session.snapshot", "status": self.simulator_status()}
        for client in tuple(self._clients):
            try:
                await client.send_json(message)
            except Exception:
                stale_clients.append(client)
        for client in stale_clients:
            self.disconnect(client)

    async def recent_events(self, limit: int = 100) -> list[TelemetryEvent]:
        async with self._lock:
            return sorted(self._events.values(), key=lambda event: event.timestamp, reverse=True)[:limit]

    async def latest_by_machine(self, session_id: str | None = None) -> list[TelemetryEvent]:
        async with self._lock:
            latest: dict[str, TelemetryEvent] = {}
            selected_session = self._current_session_id if session_id is None else session_id
            for event in self._events.values():
                if selected_session is not None and event.session_id != selected_session:
                    continue
                previous = latest.get(event.machine_id)
                if previous is None or event.timestamp > previous.timestamp:
                    latest[event.machine_id] = event
            return [latest[key] for key in sorted(latest)]

    async def latest_for_machine(self, machine_id: str, session_id: str | None = None) -> TelemetryEvent | None:
        latest = await self.latest_by_machine(session_id)
        return next((event for event in latest if event.machine_id == machine_id), None)

    def simulator_status(self) -> dict[str, Any]:
        task = self._simulator_task
        running = task is not None and not task.done()
        config = self._simulator_config
        return {
            "running": running,
            "mode": self._session_config.mode if self._session_config else None,
            "machine_count": len(self._session_machine_ids),
            "session_id": self._current_session_id,
            "machine_ids": list(self._session_machine_ids),
            "active_machine_count": len(self._session_machine_ids) if running else 0,
            "session_event_count": sum(event.session_id == self._current_session_id for event in self._events.values()),
            "historical_machine_count": len({
                (event.session_id, event.machine_id) for event in self._events.values()
                if event.session_id != self._current_session_id
            }),
            "interval_seconds": self._session_config.interval_seconds if self._session_config else None,
            "error": self._simulator_error,
        }

    async def start_simulator(self, request: SimulatorStartRequest) -> None:
        if self._simulator_task is not None and not self._simulator_task.done():
            raise RuntimeError("The simulator is already running.")
        session_id = str(uuid4())
        config = SimulatorConfig(
            session_id=session_id,
            machine_count=request.machine_count,
            interval_seconds=request.interval_seconds,
            mode=request.mode,
            machine_modes=tuple(request.machine_modes) if request.machine_modes is not None else None,
            seed=request.seed,
            wear_min=request.wear_min,
            wear_max=request.wear_max,
            wear_increment=request.wear_increment,
        )
        # Construction validates saved Type mapping and model metadata before
        # advertising a running service; generation and prediction stay in src/.
        simulator = SyntheticSensorSimulator(config)
        self._simulator_config = config
        self._session_config = config
        self._current_session_id = session_id
        simulator_machines = getattr(simulator, "machines", None)
        self._session_machine_ids = (
            [machine.machine_id for machine in simulator_machines]
            if simulator_machines is not None
            else [f"SIM-MACHINE-{index + 1:03d}" for index in range(request.machine_count)]
        )
        self._failure_streaks.clear()
        self._pending_first_seen.clear()
        self._recovery_streaks.clear()
        self._active_alert_ids.clear()
        self._simulator_error = None
        await self.broadcast_session_snapshot()
        self._simulator_task = asyncio.create_task(self._run_simulator(simulator), name="synthetic-telemetry")

    async def _run_simulator(self, simulator: SyntheticSensorSimulator) -> None:
        try:
            while True:
                batch = await asyncio.to_thread(simulator.generate_events)
                if simulator.config.session_id != self._current_session_id:
                    return
                for event in batch:
                    if event.get("session_id") in (None, "unassigned"):
                        event["session_id"] = simulator.config.session_id
                    await self.ingest(event)
                await asyncio.sleep(simulator.config.interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._simulator_error = str(error)

    async def stop_simulator(self) -> bool:
        task = self._simulator_task
        if task is None or task.done():
            self._simulator_task = None
            self._simulator_config = None
            await self.broadcast_session_snapshot()
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._simulator_task = None
        self._simulator_config = None
        await self.broadcast_session_snapshot()
        return True
