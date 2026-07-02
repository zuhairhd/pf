from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models import User, Organization, SubscriptionPlan
from app.schemas.auth import (
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    UserCreate,
    UserLogin,
    TokenResponse,
)
from app.services.auth_service import AuthService
from app.config import get_settings

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Registration page."""
    return templates.TemplateResponse("auth/register.html", {"request": request})


@router.post("/register")
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user and create their organization."""
    auth_service = AuthService(db)

    # Normalize email and check for duplicates.
    normalized_email = user_data.email.strip().lower()
    existing = await db.execute(select(User).where(User.email == normalized_email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user and organization
    user = await auth_service.create_user(user_data)

    # Send verification email (or log dev link)
    await auth_service.send_verification_email(user)

    return {
        "message": "Registration successful. Please check your email to verify your account.",
        "user_id": user.id,
    }


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT tokens."""
    auth_service = AuthService(db)

    user = await auth_service.authenticate(credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your email.",
        )

    tokens = await auth_service.create_tokens(user)
    return tokens


@router.get("/verify-email/{token}")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """Verify email address."""
    auth_service = AuthService(db)
    success = await auth_service.verify_email(token)

    if not success:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    return {"message": "Email verified successfully. You can now log in."}


@router.post("/forgot-password")
async def forgot_password(payload: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    """Request password reset email.

    Always returns the same message to prevent account enumeration.
    """
    auth_service = AuthService(db)
    await auth_service.send_password_reset(payload.email)

    return {"message": "If an account exists with this email, a password reset link has been sent."}


@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str):
    """Password reset page."""
    return templates.TemplateResponse("auth/reset_password.html", {
        "request": request,
        "token": token,
    })


@router.post("/reset-password")
async def reset_password(payload: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    """Reset password with token."""
    auth_service = AuthService(db)
    success = await auth_service.reset_password(payload.token, payload.new_password)

    if not success:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    return {"message": "Password reset successfully. You can now log in."}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new access/refresh token pair."""
    auth_service = AuthService(db)
    tokens = await auth_service.refresh_access_token(payload.refresh_token)

    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tokens


@router.post("/logout")
async def logout(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Logout by revoking the supplied refresh token."""
    auth_service = AuthService(db)
    revoked = await auth_service.revoke_refresh_token(payload.refresh_token)

    if not revoked:
        raise HTTPException(status_code=400, detail="Invalid refresh token")

    return {"message": "Logged out successfully"}
