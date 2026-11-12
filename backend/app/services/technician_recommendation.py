from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AssignmentStatus, UserRole
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User

ACTIVE_ASSIGNMENT_STATUSES = (
    AssignmentStatus.OFFERED,
    AssignmentStatus.ACCEPTED,
)

AVAILABILITY_UNAVAILABLE = "unavailable"
AVAILABILITY_UNKNOWN = "unknown"

NO_CALENDAR_WARNING = (
    "Technician availability is represented only by the general "
    "is_available flag. No calendar or time-slot data is modelled, so "
    "availability for this specific job remains unknown and must be "
    "confirmed before dispatch."
)

_SKILL_KEYS = (
    "equipment_types",
    "certifications",
    "specializations",
    "skills",
)


@dataclass(frozen=True)
class TechnicianRecommendation:
    technician_id: uuid.UUID
    full_name: str
    eligible: bool
    matching_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    active_workload: int
    availability_status: str
    reasons: tuple[str, ...]
    rank: int


@dataclass(frozen=True)
class TechnicianRecommendationResult:
    required_skills: tuple[str, ...]
    recommendations: tuple[TechnicianRecommendation, ...]
    warnings: tuple[str, ...]


def _skill_values(skills: Any) -> list[str]:
    """Return only skills actually recorded on the technician profile."""

    if not isinstance(skills, dict):
        return []

    values: list[str] = []
    for key in _SKILL_KEYS:
        raw = skills.get(key)
        if isinstance(raw, str):
            candidate = raw.strip()
            if candidate:
                values.append(candidate)
        elif isinstance(raw, (list, tuple)):
            for item in raw:
                if not isinstance(item, str):
                    continue
                candidate = item.strip()
                if candidate:
                    values.append(candidate)
    return values


def _deduplicate(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return tuple(result)


def _matching_skills(
    recorded: list[str],
    required: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    recorded_by_key = {value.casefold(): value for value in recorded}
    matching: list[str] = []
    missing: list[str] = []
    for skill in required:
        key = skill.strip().casefold()
        if key in recorded_by_key:
            matching.append(recorded_by_key[key])
        else:
            missing.append(skill)
    return _deduplicate(matching), _deduplicate(missing)


def _evaluate(
    *,
    technician: Technician,
    user: User,
    required_skills: tuple[str, ...],
    active_workload: int,
) -> TechnicianRecommendation:
    reasons: list[str] = []
    eligible = True

    if user.role is not UserRole.TECHNICIAN:
        eligible = False
        reasons.append("User does not have the technician role.")
    if not user.is_active:
        eligible = False
        reasons.append("Technician account is inactive.")
    if not technician.is_available:
        eligible = False
        reasons.append("Technician is marked unavailable.")

    recorded = _skill_values(technician.skills)
    matching, missing = _matching_skills(recorded, required_skills)

    if required_skills:
        if matching:
            reasons.append(
                "Recorded skills match: " + ", ".join(matching) + "."
            )
        else:
            reasons.append(
                "No recorded skill matches the required equipment type; "
                "this is a ranking signal, not an automatic exclusion."
            )
    else:
        reasons.append(
            "No equipment-specific skill requirement was derived from the "
            "authorized complaint data."
        )

    if active_workload:
        reasons.append(
            f"Technician currently has {active_workload} active "
            "assignment(s); this affects ranking but is not a capacity "
            "limit."
        )
    else:
        reasons.append("Technician currently has no active assignments.")

    if eligible:
        availability_status = AVAILABILITY_UNKNOWN
        reasons.append(
            "General availability is enabled, but no calendar is modelled; "
            "availability for this job is unknown."
        )
    else:
        availability_status = AVAILABILITY_UNAVAILABLE

    return TechnicianRecommendation(
        technician_id=technician.id,
        full_name=user.full_name,
        eligible=eligible,
        matching_skills=matching,
        missing_skills=missing,
        active_workload=active_workload,
        availability_status=availability_status,
        reasons=tuple(reasons),
        rank=0,
    )


def _sort_key(
    recommendation: TechnicianRecommendation,
) -> tuple[int, int, int, str, str]:
    return (
        0 if recommendation.eligible else 1,
        -len(recommendation.matching_skills),
        recommendation.active_workload,
        recommendation.full_name.casefold(),
        str(recommendation.technician_id),
    )


def _with_ranks(
    recommendations: list[TechnicianRecommendation],
) -> tuple[TechnicianRecommendation, ...]:
    ordered = sorted(recommendations, key=_sort_key)
    return tuple(
        TechnicianRecommendation(
            technician_id=item.technician_id,
            full_name=item.full_name,
            eligible=item.eligible,
            matching_skills=item.matching_skills,
            missing_skills=item.missing_skills,
            active_workload=item.active_workload,
            availability_status=item.availability_status,
            reasons=item.reasons,
            rank=index + 1,
        )
        for index, item in enumerate(ordered)
    )


def _active_workload_subquery():
    return (
        select(
            TechnicianAssignment.technician_id.label("technician_id"),
            func.count().label("active_workload"),
        )
        .where(
            TechnicianAssignment.assignment_status.in_(
                ACTIVE_ASSIGNMENT_STATUSES
            )
        )
        .group_by(TechnicianAssignment.technician_id)
        .subquery()
    )


async def _candidate_rows(
    session: AsyncSession,
) -> list[tuple[Technician, User, int]]:
    workload = _active_workload_subquery()
    statement = (
        select(
            Technician,
            User,
            func.coalesce(workload.c.active_workload, 0),
        )
        .join(User, Technician.user_id == User.id)
        .outerjoin(
            workload,
            workload.c.technician_id == Technician.id,
        )
        .where(User.role == UserRole.TECHNICIAN)
    )
    result = await session.execute(statement)
    return [
        (technician, user, int(active_workload or 0))
        for technician, user, active_workload in result.all()
    ]


def _prepare(
    rows: list[tuple[Technician, User, int]],
    required_skills: tuple[str, ...],
) -> list[TechnicianRecommendation]:
    return [
        _evaluate(
            technician=technician,
            user=user,
            required_skills=required_skills,
            active_workload=active_workload,
        )
        for technician, user, active_workload in rows
    ]


def required_skills_for_equipment(equipment: Any | None) -> tuple[str, ...]:
    """Derive the only equipment skill the current schema can support.

    ``Equipment.equipment_type`` is the recorded specialization signal; the
    technician model has no structured manufacturer/model skill column, so the
    service does not invent one.
    """

    if equipment is None:
        return ()
    equipment_type = getattr(equipment, "equipment_type", None)
    if not isinstance(equipment_type, str):
        return ()
    normalized = equipment_type.strip()
    return (normalized,) if normalized else ()


async def recommend_technicians(
    session: AsyncSession,
    *,
    required_skills: tuple[str, ...],
    limit: int,
) -> TechnicianRecommendationResult:
    """Rank technician profiles deterministically from database facts.

    Eligibility mirrors the existing assignment service: an active user with
    the technician role and an available technician profile. Skills and active
    workload only affect ordering. Availability is reported as ``unknown`` for
    eligible technicians because the schema has no calendar.
    """

    normalized_required = _deduplicate(list(required_skills))
    rows = await _candidate_rows(session)
    ranked = _with_ranks(_prepare(rows, normalized_required))

    warnings: list[str] = [NO_CALENDAR_WARNING]
    if not rows:
        warnings.append(
            "No technician profiles are registered in the database."
        )

    bounded_limit = max(1, min(limit, 100))
    if len(ranked) > bounded_limit:
        warnings.append(
            f"Only the top {bounded_limit} technician candidate(s) are shown; "
            "the ranking is deterministic for the same database state."
        )

    return TechnicianRecommendationResult(
        required_skills=normalized_required,
        recommendations=ranked[:bounded_limit],
        warnings=tuple(warnings),
    )


async def evaluate_technician(
    session: AsyncSession,
    *,
    technician_id: uuid.UUID,
    required_skills: tuple[str, ...],
) -> TechnicianRecommendation | None:
    """Re-evaluate one technician against current database state."""

    workload = _active_workload_subquery()
    statement = (
        select(
            Technician,
            User,
            func.coalesce(workload.c.active_workload, 0),
        )
        .join(User, Technician.user_id == User.id)
        .outerjoin(
            workload,
            workload.c.technician_id == Technician.id,
        )
        .where(
            Technician.id == technician_id,
            User.role == UserRole.TECHNICIAN,
        )
    )
    row = (await session.execute(statement)).first()
    if row is None:
        return None

    technician, user, active_workload = row
    evaluation = _evaluate(
        technician=technician,
        user=user,
        required_skills=_deduplicate(list(required_skills)),
        active_workload=int(active_workload or 0),
    )
    return TechnicianRecommendation(
        technician_id=evaluation.technician_id,
        full_name=evaluation.full_name,
        eligible=evaluation.eligible,
        matching_skills=evaluation.matching_skills,
        missing_skills=evaluation.missing_skills,
        active_workload=evaluation.active_workload,
        availability_status=evaluation.availability_status,
        reasons=evaluation.reasons,
        rank=1,
    )


def recommendation_to_dict(
    recommendation: TechnicianRecommendation,
) -> dict[str, Any]:
    return {
        "technician_id": str(recommendation.technician_id),
        "full_name": recommendation.full_name,
        "eligible": recommendation.eligible,
        "matching_skills": list(recommendation.matching_skills),
        "missing_skills": list(recommendation.missing_skills),
        "active_workload": recommendation.active_workload,
        "availability_status": recommendation.availability_status,
        "reasons": list(recommendation.reasons),
        "rank": recommendation.rank,
    }


def recommendation_snapshot(
    result: TechnicianRecommendationResult,
) -> list[dict[str, Any]]:
    return [
        recommendation_to_dict(item) for item in result.recommendations
    ]


def recommendation_ids(
    stored: Any,
) -> dict[uuid.UUID, dict[str, Any]]:
    """Index stored recommendation dictionaries by technician id."""

    indexed: dict[uuid.UUID, dict[str, Any]] = {}
    if not isinstance(stored, list):
        return indexed
    for item in stored:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("technician_id")
        try:
            technician_id = uuid.UUID(str(raw_id))
        except (TypeError, ValueError):
            continue
        indexed[technician_id] = item
    return indexed
