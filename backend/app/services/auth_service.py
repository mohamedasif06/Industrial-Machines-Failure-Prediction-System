"""SQLite-backed users and server-side sessions for the local prototype."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config import auth_database_path


class AuthConfigurationError(RuntimeError):
    """Raised when authentication storage or session settings are invalid."""


class DuplicateUsernameError(ValueError):
    """Raised when registration conflicts with the database unique constraint."""


@dataclass(frozen=True)
class AuthUser:
    username: str


class AuthService:
    """Authenticate SQLite users and keep opaque sessions in process memory."""

    def __init__(self, username: str | None = None, password_hash: str | None = None,
                 session_ttl_seconds: int = 8 * 60 * 60,
                 database_path: str | Path | None = None):
        if session_ttl_seconds < 60:
            raise AuthConfigurationError("AUTH_SESSION_TTL_SECONDS must be at least 60.")
        self.session_ttl_seconds = session_ttl_seconds
        self.database_path = Path(database_path) if database_path else None
        self._legacy_username = username
        self._legacy_password_hash = password_hash
        self._sessions: dict[str, tuple[str, float]] = {}
        if self.database_path:
            try:
                self.database_path.parent.mkdir(parents=True, exist_ok=True)
                self._initialize_database()
            except OSError as error:
                raise AuthConfigurationError(f"Could not prepare authentication database: {error}") from error
        elif not (username and password_hash):
            raise AuthConfigurationError("AUTH_DATABASE_PATH is required for registered accounts.")

    @classmethod
    def from_environment(cls) -> "AuthService":
        from os import getenv
        try:
            ttl = int(getenv("AUTH_SESSION_TTL_SECONDS", str(8 * 60 * 60)))
        except ValueError as error:
            raise AuthConfigurationError("AUTH_SESSION_TTL_SECONDS must be an integer.") from error
        return cls(session_ttl_seconds=ttl, database_path=auth_database_path())

    def _connect(self) -> sqlite3.Connection:
        if self.database_path is None:
            raise AuthConfigurationError("SQLite authentication storage is not configured.")
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def register(self, username: str, password: str) -> AuthUser:
        if self.database_path is None:
            raise AuthConfigurationError("Registration requires SQLite authentication storage.")
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, make_password_hash(password), datetime.now(UTC).isoformat()),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateUsernameError from error
        return AuthUser(username)

    def _stored_hash(self, username: str) -> str | None:
        if self.database_path is None:
            return self._legacy_password_hash if hmac.compare_digest(username, self._legacy_username or "") else None
        with self._connect() as connection:
            row = connection.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
        return str(row["password_hash"]) if row else None

    def authenticate(self, username: str, password: str) -> AuthUser | None:
        stored_hash = self._stored_hash(username)
        password_hash = stored_hash or _DUMMY_HASH
        valid = self.verify_password(password, password_hash)
        if valid and stored_hash is not None:
            return AuthUser(username)
        return None

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        try:
            prefix, n, r, p, salt_text, digest_text = password_hash.split("$", 5)
            if prefix != "scrypt":
                return False
            salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
            actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError, UnicodeError):
            return False

    def create_session(self, user: AuthUser) -> tuple[str, int]:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (user.username, time.time() + self.session_ttl_seconds)
        return token, self.session_ttl_seconds

    def get_user(self, token: str | None) -> AuthUser | None:
        if not token:
            return None
        session = self._sessions.get(token)
        if session is None:
            return None
        username, expires_at = session
        if expires_at <= time.time():
            self._sessions.pop(token, None)
            return None
        return AuthUser(username)

    def revoke(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)


def make_password_hash(password: str) -> str:
    """Create a portable scrypt hash for local setup and tests."""
    salt = secrets.token_bytes(16)
    n, r, p = 16384, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii")
    return f"scrypt${n}${r}${p}${encode(salt)}${encode(digest)}"


_DUMMY_HASH = make_password_hash("invalid-authentication-placeholder")
