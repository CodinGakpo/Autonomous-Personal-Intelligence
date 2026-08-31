"""Résumé endpoints — serve pre-parsed résumé JSON files for roster members.

Storage: parsed résumé JSON files live in ``_samples/resume_{slug}.json`` where
``slug`` is the local part of the employee's email (e.g. ``jane`` for
``jane@agent-os.local``).  In production, point RESUME_DIR at a proper directory.

RBAC (ADR-0003, Law 1):
  - Developers may only retrieve their own résumé.
  - admin / team_lead / hr may retrieve any résumé.

The endpoint is intentionally read-only and side-effect-free (ADR-0001).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from console.backend.auth import get_current_user
from console.backend.models import User
from console.backend.rbac import assert_self_or_privileged

# Résumé files are stored as  _samples/resume_<slug>.json  at the project root.
# The project root is three levels above this file:  console/backend/resume.py → console/ → project root
_DEFAULT_RESUME_DIR = Path(__file__).parents[3] / "_samples"

router = APIRouter(tags=["resume"], dependencies=[Depends(get_current_user)])


def _resume_path(email: str, resume_dir: Path = _DEFAULT_RESUME_DIR) -> Path:
    """Derive the résumé file path from an employee email address."""
    slug = email.split("@")[0].lower().replace(".", "_").replace("-", "_")
    return resume_dir / f"resume_{slug}.json"


@router.get("/resume")
def get_resume(
    email: str,  # query param: ?email=jane@agent-os.local
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Return the parsed résumé JSON for *email*.

    - Developers: own résumé only (403 for others).
    - Privileged roles: any résumé.
    """
    assert_self_or_privileged(user, email)

    path = _resume_path(email)
    if not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No résumé on file for {email!r}. "
            f"Expected file: {path.name}",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Résumé file for {email!r} is not valid JSON: {exc}",
        ) from exc
