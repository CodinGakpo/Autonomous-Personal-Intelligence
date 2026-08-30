"""Integration-health endpoint.

For v1 this reports configuration status (is each integration's secret present?). A later
iteration upgrades each check to a real liveness probe (e.g. ClickUp `GET /user`) — see the
Track C plan. The route MUST go through the typed clients, never raw third-party HTTP.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from console.backend.config import Settings, get_settings

router = APIRouter(tags=["health"])

SettingsDep = Annotated[Settings, Depends(get_settings)]

Status = Literal["configured", "not_configured"]


class IntegrationHealth(BaseModel):
    name: str
    status: Status


class HealthReport(BaseModel):
    ok: bool
    integrations: list[IntegrationHealth]


def _status(secret: str | None) -> Status:
    return "configured" if secret else "not_configured"


@router.get("/health", response_model=HealthReport)
def health(settings: SettingsDep) -> HealthReport:
    integrations = [
        IntegrationHealth(name="clickup", status=_status(settings.clickup_token)),
        IntegrationHealth(name="slack", status=_status(settings.slack_bot_token)),
        IntegrationHealth(name="fathom", status=_status(settings.fathom_api_key)),
    ]
    ok = all(i.status == "configured" for i in integrations)
    return HealthReport(ok=ok, integrations=integrations)
