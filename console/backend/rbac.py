"""Role-Based Access Control helpers — the single source of truth for all RBAC decisions.

Role taxonomy (documented in docs/adr/0003-rbac-policy.md):

    admin      — unrestricted; can create auth accounts, onboard, read everything.
    team_lead  — can onboard + read all résumés / profiles; cannot create auth accounts.
    hr         — same privilege level as team_lead; separate role for Phase-2 divergence.
    developer  — individual contributor; sees own data only.

Laws enforced here:
    1. Developers cannot read another employee's résumé.
    2. Developers see a redacted roster (no email / ClickUp fields for peers).
    3. Only admin / team_lead / hr can onboard new people.
    4. Only admin can create auth accounts  (enforced in auth.py, uses require_role here).
    5. All authenticated users can read health / applications.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from console.backend.models import User

# Roles that can see all employee data (résumés, full roster rows, etc.).
PRIVILEGED_ROLES: frozenset[str] = frozenset({"admin", "team_lead", "hr"})

# Roles that can onboard new people.
ONBOARD_ROLES: frozenset[str] = frozenset({"admin", "team_lead", "hr"})

# All valid role strings.
ALL_ROLES: frozenset[str] = frozenset({"admin", "team_lead", "developer", "hr"})


def is_privileged(user: User) -> bool:
    """Return True if the user holds a role that can see all employee data."""
    return user.role in PRIVILEGED_ROLES


def require_role(*allowed: str):
    """FastAPI dependency factory — raises 403 unless the user holds one of *allowed* roles.

    Usage::

        @router.post("/onboarding", dependencies=[require_role("admin", "team_lead", "hr")])
        def onboard(...): ...

    or as a typed dep::

        PrivilegedUser = Annotated[User, require_role("admin", "team_lead", "hr")]
    """
    # Import here to avoid circular import at module load time.
    from console.backend.auth import get_current_user  # noqa: PLC0415

    allowed_set = frozenset(allowed)

    def _check(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed_set:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{user.role}' is not authorised for this action. "
                f"Required: {sorted(allowed_set)}",
            )
        return user

    return Depends(_check)


def assert_self_or_privileged(user: User, target_email: str) -> None:
    """Raise 403 if *user* is a developer trying to access another person's data.

    Privileged roles pass through unconditionally.  Developers are allowed access
    only when *target_email* matches their own login email.
    """
    if is_privileged(user):
        return
    if user.email.lower() != target_email.lower():
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Developers may only access their own data. "
            f"You ({user.email!r}) cannot access data for {target_email!r}.",
        )
