"""User authentication helpers and Streamlit session integration."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import streamlit as st
from passlib.context import CryptContext

from . import database
from .database import PlanSummary, PlanVersionSummary


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
AUTH_SESSION_KEY = "auth_user"


class AuthError(Exception):
    """Raised when authentication or registration fails."""


@dataclass(frozen=True)
class AuthUser:
    id: int
    email: str
    display_name: str
    role: str = "member"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(password, hashed)
    except Exception:
        return False


def register_user(*, email: str, password: str, display_name: str) -> AuthUser:
    """Register a new account and return the created user."""

    email_normalised = email.strip().lower()
    with database.get_session() as session:
        existing = database.get_user_by_email(session, email_normalised)
        if existing is not None:
            raise AuthError("このメールアドレスは既に登録されています。")
        hashed_password = hash_password(password)
        user = database.create_user(
            session,
            email=email_normalised,
            hashed_password=hashed_password,
            display_name=display_name.strip() or email_normalised,
        )
        return AuthUser(id=user.id, email=user.email, display_name=user.display_name, role=user.role)


def authenticate(email: str, password: str) -> AuthUser:
    """Validate credentials and return the authenticated user."""

    email_normalised = email.strip().lower()
    with database.get_session() as session:
        user = database.get_user_by_email(session, email_normalised)
        if user is None or not verify_password(password, user.hashed_password):
            raise AuthError("メールアドレスまたはパスワードが正しくありません。")
        return AuthUser(id=user.id, email=user.email, display_name=user.display_name, role=user.role)


def _store_user(user: AuthUser) -> None:
    st.session_state[AUTH_SESSION_KEY] = asdict(user)


def login_user(email: str, password: str) -> AuthUser:
    """Authenticate and persist the user into the Streamlit session."""

    user = authenticate(email, password)
    _store_user(user)
    return user


def login_via_token(user: AuthUser) -> None:
    """Store the provided user object directly in session state."""

    _store_user(user)


def logout_user() -> None:
    """Clear the authenticated user from the session."""

    if AUTH_SESSION_KEY in st.session_state:
        del st.session_state[AUTH_SESSION_KEY]


def get_current_user() -> Optional[AuthUser]:
    """Return the authenticated user, if any."""

    data = st.session_state.get(AUTH_SESSION_KEY)
    if isinstance(data, dict) and {"id", "email", "display_name", "role"}.issubset(data.keys()):
        return AuthUser(**data)
    return None


def is_authenticated() -> bool:
    return get_current_user() is not None


def require_role(role: str) -> bool:
    """Return ``True`` if the current user has at least the requested role."""

    user = get_current_user()
    if user is None:
        return False
    if role == "member":
        return True
    return user.role == role


def available_plan_summaries() -> List[PlanSummary]:
    user = get_current_user()
    if user is None:
        return []
    with database.get_session() as session:
        return database.list_user_plans(session, user.id)


def available_versions(plan_id: int) -> List[PlanVersionSummary]:
    user = get_current_user()
    if user is None:
        return []
    with database.get_session() as session:
        plan = session.get(database.Plan, plan_id)
        if plan is None or plan.user_id != user.id:
            return []
        return database.list_plan_versions(session, plan_id)


def save_snapshot(*, plan_name: str, payload: Dict[str, object], note: str = "", description: str = "") -> PlanVersionSummary:
    user = get_current_user()
    if user is None:
        raise AuthError("ログイン後に保存できます。")
    return database.save_plan_version(
        user.id,
        plan_name=plan_name,
        payload=payload,
        note=note,
        actor_email=user.email,
        description=description,
    )


def load_snapshot(*, plan_name: Optional[str] = None, plan_id: Optional[int] = None, version: Optional[int] = None, version_id: Optional[int] = None) -> Optional[Dict[str, object]]:
    user = get_current_user()
    if user is None:
        return None
    return database.load_plan_payload(
        user.id,
        plan_name=plan_name,
        plan_id=plan_id,
        version=version,
        version_id=version_id,
    )


def export_backup() -> Optional[Dict[str, object]]:
    user = get_current_user()
    if user is None:
        return None
    return database.plan_backup_blob(user.id)


__all__ = [
    "AuthError",
    "AuthUser",
    "available_plan_summaries",
    "available_versions",
    "authenticate",
    "export_backup",
    "get_current_user",
    "is_authenticated",
    "load_snapshot",
    "login_user",
    "login_via_token",
    "logout_user",
    "register_user",
    "require_role",
    "save_snapshot",
]
