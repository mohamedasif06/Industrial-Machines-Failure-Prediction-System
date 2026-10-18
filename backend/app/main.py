"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import (
    alert_activation_threshold,
    alert_recovery_threshold,
    allowed_origins,
    event_history_limit,
    managed_alert_limit,
)
from .services.auth_service import AuthConfigurationError, AuthService
from .services.inference_service import InferenceService
from .services.telemetry_service import TelemetryService


def create_app(
    inference_service: InferenceService | None = None,
    telemetry_service: TelemetryService | None = None,
    auth_service: AuthService | None = None,
) -> FastAPI:
    """Create an app, optionally injecting services for isolated tests."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        await application.state.telemetry_service.stop_simulator()

    application = FastAPI(
        title="Industrial Machine Failure Forecasting API",
        version="1.0.0",
        description=(
            "Model inference and synthetic telemetry. Predictions are model estimates; "
            "no physical machine confirmation data is available."
        ),
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.state.inference_service = inference_service or InferenceService()
    if auth_service is not None:
        application.state.auth_service = auth_service
    else:
        try:
            application.state.auth_service = AuthService.from_environment()
        except AuthConfigurationError:
            # The server can still expose public health/configuration diagnostics;
            # all protected routes reject access until auth is configured.
            application.state.auth_service = None
    application.state.telemetry_service = telemetry_service or TelemetryService(
        history_limit=event_history_limit(),
        alert_activation_threshold=alert_activation_threshold(),
        alert_recovery_threshold=alert_recovery_threshold(),
        alert_limit=managed_alert_limit(),
    )
    application.include_router(router)
    return application


app = create_app()
