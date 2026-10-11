"""Request and response models for the backend API."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class PredictionRequest(BaseModel):
    """Exactly the six original model inputs; aliases preserve dataset names."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    machine_type: Literal["L", "M", "H"] = Field(alias="Type")
    air_temperature: FiniteFloat = Field(alias="Air temperature [K]")
    process_temperature: FiniteFloat = Field(alias="Process temperature [K]")
    rotational_speed: FiniteFloat = Field(alias="Rotational speed [rpm]")
    torque: FiniteFloat = Field(alias="Torque [Nm]")
    tool_wear: FiniteFloat = Field(alias="Tool wear [min]")

    def inference_values(self) -> dict[str, str | float]:
        return {
            "Type": self.machine_type,
            "Air temperature [K]": self.air_temperature,
            "Process temperature [K]": self.process_temperature,
            "Rotational speed [rpm]": self.rotational_speed,
            "Torque [Nm]": self.torque,
            "Tool wear [min]": self.tool_wear,
        }


class PredictionResponse(BaseModel):
    predicted_class: Literal[0, 1]
    predicted_label: str
    model_name: str
    probability_note: str
    estimated_failure_probability: float | None = None


class TelemetryEvent(BaseModel):
    """Synthetic simulator event; additional physical/label fields are rejected."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    timestamp: str
    session_id: str = "unassigned"
    machine_id: str = Field(min_length=1)
    simulation_mode: Literal["normal", "fault_scenario"]
    simulated: Literal[True]
    machine_type: Literal["L", "M", "H"] = Field(alias="Type")
    air_temperature: FiniteFloat = Field(alias="Air temperature [K]")
    process_temperature: FiniteFloat = Field(alias="Process temperature [K]")
    rotational_speed: FiniteFloat = Field(alias="Rotational speed [rpm]")
    torque: FiniteFloat = Field(alias="Torque [Nm]")
    tool_wear: FiniteFloat = Field(alias="Tool wear [min]")
    predicted_class: Literal[0, 1]
    predicted_label: str
    model_name: str
    estimated_failure_probability: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_iso8601(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("timestamp must be an ISO 8601 datetime.") from error
        return value


class ManagedAlert(BaseModel):
    """One backend-managed episode of repeated failure-associated predictions."""

    alert_id: str
    session_id: str = "unassigned"
    machine_id: str
    condition: Literal["failure_associated_prediction"]
    simulation_mode: Literal["normal", "fault_scenario"]
    first_seen: datetime
    created_at: datetime
    last_seen: datetime
    updated_at: datetime
    occurrence_count: int = Field(ge=1)
    status: Literal["active", "resolved"]
    resolved_at: datetime | None = None
    latest_event: TelemetryEvent


class AlertListResponse(BaseModel):
    active_count: int
    resolved_count: int
    activation_threshold: int
    recovery_threshold: int
    alerts: list[ManagedAlert]


class MachineSummary(BaseModel):
    machine_id: str
    latest_event: TelemetryEvent | None = None


class MachineListResponse(BaseModel):
    machine_count: int
    session_id: str | None = None
    machines_with_readings: int = 0
    machines: list[MachineSummary]


class EventListResponse(BaseModel):
    event_count: int
    events: list[TelemetryEvent]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    model_available: bool
    recommended_model: str | None
    detail: str


class SimulatorStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_count: int = Field(default=3, ge=1, le=100)
    interval_seconds: float = Field(default=2.0, gt=0, le=3600, allow_inf_nan=False)
    mode: Literal["normal", "fault_scenario", "mixed"] = "normal"
    machine_modes: list[Literal["normal", "fault_scenario"]] | None = None
    seed: int | None = None
    wear_min: float = Field(default=0, ge=0, allow_inf_nan=False)
    wear_max: float = Field(default=253, gt=0, le=253, allow_inf_nan=False)
    wear_increment: float = Field(default=0.01, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_mode_assignment(self):
        if self.mode != "mixed" and self.machine_modes is not None:
            raise ValueError("machine_modes may only be provided when mode='mixed'.")
        if self.mode == "mixed":
            if self.machine_count < 2:
                raise ValueError("Mixed mode requires at least two machines.")
            if self.machine_modes is not None:
                if len(self.machine_modes) != self.machine_count:
                    raise ValueError("machine_modes must contain exactly one mode per machine.")
                if len(set(self.machine_modes)) < 2:
                    raise ValueError("Mixed mode must assign both normal and fault_scenario to its machines.")
        return self


class SimulatorStatus(BaseModel):
    running: bool
    mode: Literal["normal", "fault_scenario", "mixed"] | None = None
    machine_count: int
    session_id: str | None = None
    machine_ids: list[str] = Field(default_factory=list)
    active_machine_count: int = 0
    session_event_count: int = 0
    historical_machine_count: int = 0
    interval_seconds: float | None = None
    error: str | None = None
