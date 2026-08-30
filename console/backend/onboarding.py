"""Onboarding + roster endpoints.

v1 scope: add a person (name, role, Slack handle, the products they work on) and record them as
a ClickUp task in the employees list — ClickUp is the source of truth (ADR-0001, all access via
`clickup/client.py`). A small in-memory cache backs the roster view until reads are wired
straight to ClickUp (see Track C plan).

RBAC (ADR-0003):
- POST /onboarding   — admin / team_lead / hr only.
- GET  /roster       — all authenticated users; developers receive a redacted view
                       (no email / ClickUp URL for other people's rows).
- GET  /roster/me    — always returns the caller's own full row (any role).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from clickup.client import ClickUpClient
from console.backend.auth import CurrentUser, get_current_user
from console.backend.config import Settings, get_settings
from console.backend.rbac import ONBOARD_ROLES, is_privileged, require_role


class OrgRole(StrEnum):
    """The person's organisational role (display label, not the access-control role)."""
    ADMIN = "admin"
    TEAM_LEAD = "team_lead"
    DEVELOPER = "developer"
    INTERN = "intern"
    GTM = "gtm"
    SALES = "sales"
    HR = "hr"


# Keep the old name as an alias so existing code / tests that import `Role` still work.
Role = OrgRole


class Product(StrEnum):
    # Placeholder keys — Fenil to supply the real product → competitor mapping (Track C plan).
    PRODUCT_ONE = "product_one"
    PRODUCT_TWO = "product_two"
    PRODUCT_THREE = "product_three"


class OnboardRequest(BaseModel):
    name: str
    email: str
    role: OrgRole
    slack_handle: str
    products: list[Product]


class OnboardedPerson(BaseModel):
    name: str
    email: str
    role: OrgRole
    slack_handle: str
    products: list[Product]
    clickup_task_id: str
    clickup_url: str


class RosterEntry(BaseModel):
    """A roster row — sensitive fields are None when the viewer is not privileged."""
    name: str
    email: str | None = None
    role: OrgRole
    slack_handle: str
    products: list[Product]
    clickup_task_id: str | None = None
    clickup_url: str | None = None
    is_own: bool = False


# Router: require auth on every route via the router-level dependency.
router = APIRouter(tags=["onboarding"], dependencies=[Depends(get_current_user)])

SettingsDep = Annotated[Settings, Depends(get_settings)]

# v1 in-memory cache; replaced by direct ClickUp reads (Track C plan).
_roster: list[OnboardedPerson] = []


def get_clickup_client(settings: SettingsDep) -> ClickUpClient:
    """Provide a configured ClickUp client or fail clearly. Overridden in tests."""
    if not settings.clickup_token or not settings.clickup_employees_list_id:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ClickUp is not configured (CLICKUP_TOKEN / CLICKUP_EMPLOYEES_LIST_ID).",
        )
    return ClickUpClient(token=settings.clickup_token)


ClickUpDep = Annotated[ClickUpClient, Depends(get_clickup_client)]


def _description(req: OnboardRequest) -> str:
    products = ", ".join(p.value for p in req.products) or "—"
    return (
        f"**Role:** {req.role.value}\n"
        f"**Slack:** {req.slack_handle}\n"
        f"**Email:** {req.email}\n"
        f"**Products:** {products}"
    )


@router.post(
    "/onboarding",
    response_model=OnboardedPerson,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_role(*ONBOARD_ROLES)],
)
def onboard(req: OnboardRequest, settings: SettingsDep, client: ClickUpDep) -> OnboardedPerson:
    """Create an onboarding record in ClickUp. Requires admin / team_lead / hr."""
    assert settings.clickup_employees_list_id is not None  # guaranteed by get_clickup_client
    ref = client.create_task(
        list_id=settings.clickup_employees_list_id,
        name=req.name,
        description=_description(req),
    )
    person = OnboardedPerson(
        name=req.name,
        email=req.email,
        role=req.role,
        slack_handle=req.slack_handle,
        products=req.products,
        clickup_task_id=ref.id,
        clickup_url=ref.url,
    )
    _roster.append(person)
    return person


@router.get("/roster/me", response_model=RosterEntry)
def roster_me(user: CurrentUser) -> RosterEntry:
    """Return the caller's own roster entry in full (any role)."""
    match = next((p for p in _roster if p.email == user.email), None)
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Your profile is not in the roster yet.")
    return RosterEntry(**match.model_dump(), is_own=True)


@router.get("/roster", response_model=list[RosterEntry])
def roster(user: CurrentUser) -> list[RosterEntry]:
    """Return the team roster.

    - Privileged roles (admin / team_lead / hr): full rows for everyone.
    - Developers: own row in full; peers' rows with email / ClickUp fields redacted.
    """
    result: list[RosterEntry] = []
    for p in _roster:
        own = p.email.lower() == user.email.lower()
        if own or is_privileged(user):
            result.append(RosterEntry(**p.model_dump(), is_own=own))
        else:
            result.append(
                RosterEntry(
                    name=p.name,
                    role=p.role,
                    slack_handle=p.slack_handle,
                    products=p.products,
                    # email, clickup_task_id, clickup_url intentionally omitted (Law 2)
                )
            )
    return result
