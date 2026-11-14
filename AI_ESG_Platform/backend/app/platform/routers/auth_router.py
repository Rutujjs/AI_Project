"""Authentication & User Management Router for Member 5."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.platform.dependencies import get_current_user, require_roles, security
from app.platform.models import Organization, RevokedToken, User, UserRole
from app.platform.schemas import LoginRequest, TokenResponse, UserCreateRequest, UserResponse
from app.platform.security import create_access_token, decode_access_token, hash_password, verify_password
from app.platform.services.audit_service import record_audit_event

router = APIRouter(prefix="/api/auth", tags=["Platform Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with username/email and password, returning a signed JWT access token."""
    identifier = payload.username.strip().lower()
    user = (
        db.query(User)
        .filter((func.lower(User.username) == identifier) | (func.lower(User.email) == identifier))
        .first()
    )

    if not user or not verify_password(payload.password, user.hashed_password):
        record_audit_event(
            db,
            action="LOGIN_FAILURE",
            resource_type="USER",
            resource_id=user.id if user else None,
            user_id=user.id if user else None,
            organization_id=user.organization_id if user else None,
            username=user.username if user else identifier,
            user_role=user.role if user else None,
            status="FAILURE",
            details={"reason": "Incorrect username or password", "identifier": identifier},
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        record_audit_event(
            db,
            action="LOGIN_FAILURE",
            resource_type="USER",
            resource_id=user.id,
            user=user,
            status="FAILURE",
            details={"reason": "Account is inactive", "identifier": identifier},
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )

    if user.organization_id is not None:
        org = db.query(Organization).filter(Organization.id == user.organization_id).first()
        if org and not org.is_active:
            record_audit_event(
                db,
                action="LOGIN_FAILURE",
                resource_type="USER",
                resource_id=user.id,
                user=user,
                organization_id=org.id,
                status="FAILURE",
                details={"reason": "Organization is inactive", "identifier": identifier},
                commit=True,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization account is deactivated.",
            )

    token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "org_id": user.organization_id,
            "role": user.role,
        }
    )

    record_audit_event(
        db,
        action="LOGIN_SUCCESS",
        resource_type="USER",
        resource_id=user.id,
        user=user,
        status="SUCCESS",
        commit=True,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Retrieve details for the currently authenticated user."""
    return UserResponse.model_validate(current_user)


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invalidate current JWT access token via server-side revocation list."""
    if credentials and credentials.credentials:
        token = credentials.credentials
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        try:
            payload = decode_access_token(token)
            exp_ts = payload.get("exp")
            expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else (datetime.now(timezone.utc) + timedelta(days=1))
        except Exception:
            expires_at = datetime.now(timezone.utc) + timedelta(days=1)

        existing = db.query(RevokedToken).filter(RevokedToken.token_hash == token_hash).first()
        if not existing:
            revoked = RevokedToken(
                token_hash=token_hash,
                user_id=current_user.id,
                expires_at=expires_at,
            )
            db.add(revoked)
            db.commit()

    record_audit_event(
        db,
        action="LOGOUT",
        resource_type="USER",
        resource_id=current_user.id,
        user=current_user,
        status="SUCCESS",
        commit=True,
    )

    return {"message": f"User '{current_user.username}' logged out successfully. Session invalidated."}


@router.get("/users", response_model=list[UserResponse])
def list_organization_users(
    current_user: User = Depends(require_roles(UserRole.ADMIN.value)),
    db: Session = Depends(get_db),
):
    """List all user accounts in the current tenant organization (Admin only)."""
    users = (
        db.query(User)
        .filter(User.organization_id == current_user.organization_id)
        .order_by(User.created_at.asc())
        .all()
    )
    return [UserResponse.model_validate(u) for u in users]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_organization_user(
    req: UserCreateRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN.value)),
    db: Session = Depends(get_db),
):
    """Create a new user account inside the current tenant organization (Admin only)."""
    clean_username = req.username.strip().lower()
    clean_email = req.email.strip().lower()

    # Check duplicate username (case-insensitive)
    if db.query(User).filter(func.lower(User.username) == clean_username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{req.username}' is already taken.",
        )

    # Check duplicate email (case-insensitive)
    if db.query(User).filter(func.lower(User.email) == clean_email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email '{req.email}' is already registered.",
        )

    new_user = User(
        organization_id=current_user.organization_id,
        username=clean_username,
        email=clean_email,
        full_name=req.full_name,
        role=req.role.lower(),
        hashed_password=hash_password(req.password),
        is_active=True,
    )
    db.add(new_user)
    db.flush()

    record_audit_event(
        db,
        action="USER_CREATED",
        resource_type="USER",
        resource_id=new_user.id,
        user=current_user,
        status="SUCCESS",
        details={"new_username": new_user.username, "new_user_role": new_user.role},
        commit=False,
    )

    db.commit()
    db.refresh(new_user)

    return UserResponse.model_validate(new_user)

