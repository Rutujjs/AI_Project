"""FastAPI dependencies for Member 5: Authentication, RBAC, and Tenant Isolation."""

from __future__ import annotations

import hashlib
from typing import Callable
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.platform.models import Organization, RevokedToken, User, UserRole
from app.platform.security import decode_access_token

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate the JWT Bearer token, returning the authenticated User.

    Raises:
        HTTPException 401 if missing, invalid, or expired.
        HTTPException 403 if the user account is deactivated.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check server-side token revocation (logout)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    is_revoked = db.query(RevokedToken).filter(RevokedToken.token_hash == token_hash).first()
    if is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    username = payload.get("sub")
    if user_id is None and username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing user identification.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    query = db.query(User)
    if user_id is not None:
        user = query.filter(User.id == user_id).first()
    else:
        user = query.filter(User.username == username).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this token no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    if user.organization_id is not None:
        org = db.query(Organization).filter(Organization.id == user.organization_id).first()
        if org and not org.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization account is deactivated.",
            )

    return user


def require_roles(*allowed_roles: str | UserRole) -> Callable[[User], User]:
    """Dependency factory enforcing Role-Based Access Control (RBAC).

    Usage:
        @router.post("/items", dependencies=[Depends(require_roles("admin", "auditor"))])
    """
    normalized = {r.value if isinstance(r, UserRole) else str(r).lower() for r in allowed_roles}

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        user_role = (current_user.role or "").lower()
        if user_role not in normalized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: role '{user_role}' lacks required permissions. Allowed roles: {list(normalized)}",
            )
        return current_user

    return role_checker


def get_current_organization(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Organization:
    """Retrieve the active tenant organization for the authenticated user, enforcing multi-tenant boundary."""
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization associated with this account was not found.",
        )
    if not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization account is deactivated.",
        )
    return org

