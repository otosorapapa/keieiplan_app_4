"""Database models and persistence helpers for plan storage."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///keieiplan.db")

_SQLITE_PREFIX = "sqlite:///"
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith(_SQLITE_PREFIX) else {}
engine: Engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True)
    email: str = Column(String(255), unique=True, nullable=False, index=True)
    display_name: str = Column(String(255), nullable=False)
    hashed_password: str = Column(String(255), nullable=False)
    role: str = Column(String(50), default="member", nullable=False)
    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)

    plans = relationship("Plan", back_populates="owner", cascade="all, delete-orphan")


class Plan(Base):
    __tablename__ = "plans"

    id: int = Column(Integer, primary_key=True)
    user_id: int = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: str = Column(String(255), nullable=False)
    description: str = Column(Text, default="", nullable=False)
    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="plans")
    versions = relationship(
        "PlanVersion",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PlanVersion.version",
    )

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_plan_user_name"),)


class PlanVersion(Base):
    __tablename__ = "plan_versions"

    id: int = Column(Integer, primary_key=True)
    plan_id: int = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    version: int = Column(Integer, nullable=False)
    note: str = Column(Text, default="", nullable=False)
    data_json: str = Column(Text, nullable=False)
    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by: str = Column(String(255), nullable=False)

    plan = relationship("Plan", back_populates="versions")

    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_plan_version"),)


@dataclass(frozen=True)
class PlanSummary:
    name: str
    plan_id: int
    latest_version: int
    updated_at: datetime


@dataclass(frozen=True)
class PlanVersionSummary:
    id: int
    plan_id: int
    plan_name: str
    version: int
    created_at: datetime
    note: str
    created_by: str


def init_db() -> None:
    """Create all tables if they don't exist."""

    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""

    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    raise TypeError(f"Type {type(value)!r} is not JSON serialisable")


def _ensure_plan(session: Session, user_id: int, name: str, description: str = "") -> Plan:
    stmt = select(Plan).where(Plan.user_id == user_id, Plan.name == name)
    plan = session.execute(stmt).scalar_one_or_none()
    if plan is None:
        plan = Plan(user_id=user_id, name=name, description=description or "")
        session.add(plan)
        session.flush()
    return plan


def create_user(session: Session, *, email: str, hashed_password: str, display_name: str, role: str = "member") -> User:
    """Create a new user. Raises :class:`IntegrityError` if the email is taken."""

    user = User(email=email.lower(), hashed_password=hashed_password, display_name=display_name, role=role)
    session.add(user)
    session.flush()
    return user


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    stmt = select(User).where(User.email == email.lower())
    return session.execute(stmt).scalar_one_or_none()


def list_user_plans(session: Session, user_id: int) -> List[PlanSummary]:
    stmt = (
        select(
            Plan.id,
            Plan.name,
            func.max(PlanVersion.version).label("latest_version"),
            func.max(PlanVersion.created_at).label("updated_at"),
        )
        .join(PlanVersion, PlanVersion.plan_id == Plan.id, isouter=True)
        .where(Plan.user_id == user_id)
        .group_by(Plan.id, Plan.name)
        .order_by(Plan.name.asc())
    )
    summaries: List[PlanSummary] = []
    for row in session.execute(stmt):
        latest_version = int(row.latest_version or 0)
        updated_at: datetime = row.updated_at or row._mapping[Plan.created_at]
        summaries.append(PlanSummary(name=row.name, plan_id=row.id, latest_version=latest_version, updated_at=updated_at))
    return summaries


def list_plan_versions(session: Session, plan_id: int) -> List[PlanVersionSummary]:
    stmt = (
        select(PlanVersion.id, PlanVersion.version, PlanVersion.created_at, PlanVersion.note, PlanVersion.created_by)
        .where(PlanVersion.plan_id == plan_id)
        .order_by(PlanVersion.version.desc())
    )
    plan = session.get(Plan, plan_id)
    if plan is None:
        return []
    return [
        PlanVersionSummary(
            id=row.id,
            plan_id=plan_id,
            plan_name=plan.name,
            version=row.version,
            created_at=row.created_at,
            note=row.note,
            created_by=row.created_by,
        )
        for row in session.execute(stmt)
    ]


def save_plan_version(
    user_id: int,
    *,
    plan_name: str,
    payload: Dict[str, Any],
    note: str,
    actor_email: str,
    description: str = "",
) -> PlanVersionSummary:
    """Persist a new version of a plan and return the stored metadata."""

    init_db()
    with get_session() as session:
        plan = _ensure_plan(session, user_id, plan_name, description=description)
        latest_version_stmt = select(func.max(PlanVersion.version)).where(PlanVersion.plan_id == plan.id)
        next_version = int((session.execute(latest_version_stmt).scalar() or 0) + 1)
        data_json = json.dumps(payload, ensure_ascii=False, default=_json_default)
        record = PlanVersion(
            plan_id=plan.id,
            version=next_version,
            note=note or "",
            data_json=data_json,
            created_by=actor_email,
        )
        session.add(record)
        session.flush()
        summary = PlanVersionSummary(
            id=record.id,
            plan_id=plan.id,
            plan_name=plan.name,
            version=record.version,
            created_at=record.created_at,
            note=record.note,
            created_by=record.created_by,
        )
        return summary


def load_plan_payload(
    user_id: int,
    *,
    plan_name: Optional[str] = None,
    plan_id: Optional[int] = None,
    version: Optional[int] = None,
    version_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Load a stored plan payload for the given user and identifiers."""

    init_db()
    with get_session() as session:
        target_plan: Optional[Plan] = None
        if plan_id is not None:
            target_plan = session.get(Plan, plan_id)
            if target_plan is None or target_plan.user_id != user_id:
                return None
        elif plan_name is not None:
            stmt = select(Plan).where(Plan.user_id == user_id, Plan.name == plan_name)
            target_plan = session.execute(stmt).scalar_one_or_none()
        if target_plan is None:
            return None
        version_stmt = select(PlanVersion)
        version_stmt = version_stmt.where(PlanVersion.plan_id == target_plan.id)
        if version_id is not None:
            version_stmt = version_stmt.where(PlanVersion.id == version_id)
        elif version is not None:
            version_stmt = version_stmt.where(PlanVersion.version == version)
        else:
            version_stmt = version_stmt.order_by(PlanVersion.version.desc()).limit(1)
        record = session.execute(version_stmt).scalars().first()
        if record is None:
            return None
        return json.loads(record.data_json)


def plan_backup_blob(user_id: int) -> Dict[str, Any]:
    """Return a serialisable backup of all plans for the given user."""

    init_db()
    with get_session() as session:
        plans = list_user_plans(session, user_id)
        backup: Dict[str, Any] = {"generated_at": datetime.utcnow().isoformat(), "plans": []}
        for plan_summary in plans:
            versions = list_plan_versions(session, plan_summary.plan_id)
            version_payloads: List[Dict[str, Any]] = []
            for version_summary in versions:
                version_stmt = select(PlanVersion).where(PlanVersion.id == version_summary.id)
                record = session.execute(version_stmt).scalar_one()
                version_payloads.append(
                    {
                        "version": version_summary.version,
                        "note": version_summary.note,
                        "created_at": version_summary.created_at.isoformat(),
                        "created_by": version_summary.created_by,
                        "payload": json.loads(record.data_json),
                    }
                )
            backup["plans"].append(
                {
                    "name": plan_summary.name,
                    "latest_version": plan_summary.latest_version,
                    "updated_at": plan_summary.updated_at.isoformat(),
                    "versions": version_payloads,
                }
            )
        return backup


__all__ = [
    "Base",
    "User",
    "Plan",
    "PlanVersion",
    "PlanSummary",
    "PlanVersionSummary",
    "create_user",
    "engine",
    "get_session",
    "get_user_by_email",
    "init_db",
    "list_plan_versions",
    "list_user_plans",
    "load_plan_payload",
    "plan_backup_blob",
    "save_plan_version",
]
