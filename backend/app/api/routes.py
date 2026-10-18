"""REST and WebSocket endpoints for model prediction and synthetic telemetry."""

import asyncio

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect

from ..schemas import (
    AlertListResponse,
    AuthUserResponse,
    EventListResponse,
    HealthResponse,
    MachineListResponse,
    MachineSummary,
    PredictionRequest,
    PredictionResponse,
    LoginRequest,
    RegisterRequest,
    SimulatorStartRequest,
    SimulatorStatus,
)
from ..services.inference_service import InferenceService
from ..services.telemetry_service import TelemetryService
from ..config import allowed_origins, auth_cookie_secure, session_cookie_name
from ..services.auth_service import AuthUser, DuplicateUsernameError

router = APIRouter()


def get_services(request: Request):
    return request.app.state.inference_service, request.app.state.telemetry_service


def require_user(request: Request, session_cookie: str | None = Cookie(default=None, alias=session_cookie_name())) -> AuthUser:
    auth = request.app.state.auth_service
    if auth is None:
        raise HTTPException(status_code=503, detail="Authentication is not configured on this backend.")
    user = auth.get_user(session_cookie)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def validate_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in allowed_origins():
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")


@router.post("/api/auth/login", response_model=AuthUserResponse)
async def login(body: LoginRequest, request: Request, response: Response) -> AuthUserResponse:
    validate_origin(request)
    auth = request.app.state.auth_service
    if auth is None:
        raise HTTPException(status_code=503, detail="Authentication is not configured on this backend.")
    user = auth.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token, max_age = auth.create_session(user)
    response.set_cookie(session_cookie_name(), token, max_age=max_age, httponly=True, secure=auth_cookie_secure(), samesite="lax", path="/")
    return AuthUserResponse(authenticated=True, username=user.username)


@router.post("/api/auth/register", response_model=AuthUserResponse, status_code=201)
async def register(body: RegisterRequest, request: Request, response: Response) -> AuthUserResponse:
    validate_origin(request)
    auth = request.app.state.auth_service
    if auth is None:
        raise HTTPException(status_code=503, detail="Authentication is not configured on this backend.")
    try:
        user = auth.register(body.username, body.password)
    except DuplicateUsernameError as error:
        raise HTTPException(status_code=409, detail="That username is already registered.") from error
    token, max_age = auth.create_session(user)
    response.set_cookie(session_cookie_name(), token, max_age=max_age, httponly=True, secure=auth_cookie_secure(), samesite="lax", path="/")
    return AuthUserResponse(authenticated=True, username=user.username)


@router.get("/api/auth/session", response_model=AuthUserResponse)
async def current_session(request: Request, session_cookie: str | None = Cookie(default=None, alias=session_cookie_name())) -> AuthUserResponse:
    auth = request.app.state.auth_service
    user = auth.get_user(session_cookie) if auth else None
    return AuthUserResponse(authenticated=user is not None, username=user.username if user else None)


@router.post("/api/auth/logout", response_model=AuthUserResponse)
async def logout(request: Request, response: Response, session_cookie: str | None = Cookie(default=None, alias=session_cookie_name())) -> AuthUserResponse:
    validate_origin(request)
    auth = request.app.state.auth_service
    if auth:
        auth.revoke(session_cookie)
    response.delete_cookie(session_cookie_name(), httponly=True, secure=auth_cookie_secure(), samesite="lax", path="/")
    return AuthUserResponse(authenticated=False)


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    inference, _ = get_services(request)
    available, model_name, detail = inference.availability()
    return HealthResponse(
        status="ok" if available else "degraded",
        model_available=available,
        recommended_model=model_name,
        detail=detail,
    )


@router.post("/api/predict", response_model=PredictionResponse)
async def predict(body: PredictionRequest, request: Request, user: AuthUser = Depends(require_user)) -> PredictionResponse:
    inference, _ = get_services(request)
    available, _, detail = inference.availability()
    if not available:
        raise HTTPException(status_code=503, detail=detail)
    try:
        result = await asyncio.to_thread(inference.predict, body.inference_values())
        return PredictionResponse.model_validate(result)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Model inference failed: {error}") from error


@router.get("/api/machines", response_model=MachineListResponse)
async def list_machines(request: Request, user: AuthUser = Depends(require_user)) -> MachineListResponse:
    _, telemetry = get_services(request)
    events = await telemetry.latest_by_machine()
    status = telemetry.simulator_status()
    latest_by_id = {event.machine_id: event for event in events}
    machine_ids = status["machine_ids"] or sorted(latest_by_id)
    machines = [
        MachineSummary(machine_id=machine_id, latest_event=latest_by_id.get(machine_id))
        for machine_id in machine_ids
    ]
    return MachineListResponse(
        machine_count=len(machines),
        session_id=status["session_id"],
        machines_with_readings=sum(machine.latest_event is not None for machine in machines),
        machines=machines,
    )


@router.get("/api/machines/{machine_id}", response_model=MachineSummary)
async def get_machine(machine_id: str, request: Request, user: AuthUser = Depends(require_user)) -> MachineSummary:
    _, telemetry = get_services(request)
    event = await telemetry.latest_for_machine(machine_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"No telemetry found for machine {machine_id!r}.")
    return MachineSummary(machine_id=machine_id, latest_event=event)


@router.get("/api/events", response_model=EventListResponse)
async def list_events(request: Request, limit: int = Query(default=100, ge=1, le=500), user: AuthUser = Depends(require_user)) -> EventListResponse:
    _, telemetry = get_services(request)
    events = await telemetry.recent_events(limit)
    return EventListResponse(event_count=len(events), events=events)


@router.get("/api/alerts", response_model=AlertListResponse)
async def list_alerts(request: Request, user: AuthUser = Depends(require_user)) -> AlertListResponse:
    """Return retained managed alert episodes and current active totals."""
    _, telemetry = get_services(request)
    return AlertListResponse.model_validate(await telemetry.alert_snapshot())


@router.get("/api/simulator/status", response_model=SimulatorStatus)
async def simulator_status(request: Request, user: AuthUser = Depends(require_user)) -> SimulatorStatus:
    _, telemetry = get_services(request)
    return SimulatorStatus(**telemetry.simulator_status())


@router.post("/api/simulator/start", response_model=SimulatorStatus, status_code=202)
async def start_simulator(body: SimulatorStartRequest, request: Request, user: AuthUser = Depends(require_user)) -> SimulatorStatus:
    _, telemetry = get_services(request)
    try:
        await telemetry.start_simulator(body)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=503, detail=f"Simulator could not start: {error}") from error
    return SimulatorStatus(**telemetry.simulator_status())


@router.post("/api/simulator/stop", response_model=SimulatorStatus)
async def stop_simulator(request: Request, user: AuthUser = Depends(require_user)) -> SimulatorStatus:
    _, telemetry = get_services(request)
    await telemetry.stop_simulator()
    return SimulatorStatus(**telemetry.simulator_status())


@router.websocket("/ws/telemetry")
async def telemetry_socket(websocket: WebSocket) -> None:
    telemetry: TelemetryService = websocket.app.state.telemetry_service
    auth = websocket.app.state.auth_service
    origin = websocket.headers.get("origin")
    token = websocket.cookies.get(session_cookie_name())
    if auth is None or auth.get_user(token) is None or (origin and origin.rstrip("/") not in allowed_origins()):
        await websocket.close(code=1008)
        return
    await telemetry.connect(websocket)
    try:
        # This endpoint is server-to-client. Waiting for disconnect avoids
        # inventing client commands or buffering old events for new subscribers.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        telemetry.disconnect(websocket)
    except Exception:
        telemetry.disconnect(websocket)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
