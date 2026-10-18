"""Backend paths and environment-based runtime settings."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def allowed_origins() -> list[str]:
    """Read explicit comma-separated browser origins from the environment."""
    value = os.getenv("BACKEND_CORS_ORIGINS")
    if not value:
        return list(DEFAULT_ORIGINS)
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


def auth_cookie_secure() -> bool:
    return os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes"}


def session_cookie_name() -> str:
    return "industrial_session"


def auth_database_path() -> Path:
    """Return the local SQLite path used for registered accounts."""
    configured = os.getenv("AUTH_DATABASE_PATH", "").strip()
    return Path(configured) if configured else PROJECT_ROOT / "backend" / "instance" / "users.sqlite3"


def event_history_limit() -> int:
    try:
        limit = int(os.getenv("BACKEND_EVENT_HISTORY_LIMIT", "1000"))
    except ValueError as error:
        raise ValueError("BACKEND_EVENT_HISTORY_LIMIT must be a positive integer.") from error
    if limit < 1:
        raise ValueError("BACKEND_EVENT_HISTORY_LIMIT must be a positive integer.")
    return limit


def _positive_environment_integer(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer.") from error
    if value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def alert_activation_threshold() -> int:
    """Class-1 streak needed before opening a managed alert."""
    return _positive_environment_integer("BACKEND_ALERT_ACTIVATION_THRESHOLD", 2)


def alert_recovery_threshold() -> int:
    """Consecutive class-0 streak needed to resolve an active alert."""
    return _positive_environment_integer("BACKEND_ALERT_RECOVERY_THRESHOLD", 3)


def managed_alert_limit() -> int:
    """Maximum retained alert episodes; active episodes are never evicted."""
    return _positive_environment_integer("BACKEND_ALERT_HISTORY_LIMIT", 1000)
