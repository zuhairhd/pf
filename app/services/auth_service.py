"""Authentication and user management service."""

import logging
import secrets
from datetime import datetime, timedelta

from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    EmailVerification,
    NotificationChannel,
    NotificationSetting,
    NotificationType,
    Organization,
    PasswordReset,
    RefreshToken,
    SubscriptionPlan,
    User,
)
from app.schemas.auth import TokenResponse, UserCreate
from app.utils.security import (
    generate_password_reset_token,
    generate_verification_token,
    hash_token,
    mask_email,
)

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)


def _normalize_email(email: str) -> str:
    """Normalize an email address for storage and lookup."""
    return email.strip().lower()


class AuthService:
    """Authentication and user management service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, user: User) -> str:
        """Create a short-lived JWT access token."""
        expires = datetime.utcnow() + timedelta(
            minutes=getattr(settings, "JWT_ACCESS_EXPIRATION_MINUTES", settings.JWT_EXPIRATION_MINUTES)
        )
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "tenant_id": user.organization_id,
            "role": user.role.value,
            "exp": expires,
            "type": "access",
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    def create_refresh_token(self, user: User) -> str:
        """Create a long-lived JWT refresh token."""
        expires = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_EXPIRATION_DAYS)
        payload = {
            "sub": str(user.id),
            "exp": expires,
            "type": "refresh",
            # Include a unique JWT ID so multiple refresh tokens for the same
            # user created within the same second do not collide in storage.
            "jti": secrets.token_urlsafe(16),
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user and their organization."""
        email = _normalize_email(user_data.email)

        # Create organization
        org = Organization(
            name=f"{user_data.first_name}'s Finances",
            slug=f"{email.split('@')[0]}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            plan=SubscriptionPlan.FREE,
            max_users=1,
            max_transactions=100,
            max_ai_requests_per_day=5,
            max_storage_mb=100,
        )
        self.db.add(org)
        await self.db.flush()

        # Create user
        user = User(
            email=email,
            hashed_password=self.hash_password(user_data.password),
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            organization_id=org.id,
            is_email_verified=False,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        # Seed default notification preferences for the new user.
        await self._create_default_notification_settings(user.id)

        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def _create_default_notification_settings(self, user_id: int) -> None:
        """Create safe default notification preferences for a user."""
        defaults = [
            (NotificationType.BUDGET_ALERT, True, False, False, False),
            (NotificationType.GOAL_MILESTONE, True, False, False, False),
            (NotificationType.BILL_DUE, True, False, False, False),
            (NotificationType.AI_INSIGHT, True, False, False, False),
            (NotificationType.AI_RECOMMENDATION, True, False, False, False),
            (NotificationType.ANOMALY_DETECTED, True, False, False, False),
            (NotificationType.SUBSCRIPTION_RENEWAL, True, False, False, False),
            (NotificationType.SYSTEM, True, False, False, False),
        ]
        for notif_type, in_app, email, push, sms in defaults:
            self.db.add(
                NotificationSetting(
                    user_id=user_id,
                    notification_type=notif_type,
                    in_app=in_app,
                    email=email,
                    push=push,
                    sms=sms,
                )
            )

    async def authenticate(self, email: str, password: str) -> User | None:
        """Authenticate a user by email and password."""
        email = _normalize_email(email)
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not self.verify_password(password, user.hashed_password):
            return None

        if not user.is_active:
            return None

        # Update last login
        user.last_login_at = datetime.utcnow()
        await self.db.commit()

        return user

    async def create_tokens(self, user: User) -> TokenResponse:
        """Create access and refresh tokens and persist the refresh token."""
        access_token = self.create_access_token(user)
        refresh_token = self.create_refresh_token(user)

        token = RefreshToken(
            user_id=user.id,
            token=refresh_token,
            expires_at=datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_EXPIRATION_DAYS),
            is_revoked=False,
        )
        self.db.add(token)
        await self.db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse | None:
        """Validate a refresh token and issue a new access/refresh pair."""
        try:
            payload = jwt.decode(
                refresh_token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except JWTError:
            return None

        if payload.get("type") != "refresh":
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        # Ensure the token exists and has not been revoked.
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token == refresh_token,
                RefreshToken.is_revoked == False,
                RefreshToken.expires_at > datetime.utcnow(),
            )
        )
        stored_token = result.scalar_one_or_none()
        if stored_token is None:
            return None

        # Load user.
        result = await self.db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            return None

        # Revoke the used refresh token and issue a new pair.
        stored_token.is_revoked = True
        await self.db.commit()

        return await self.create_tokens(user)

    async def revoke_refresh_token(self, refresh_token: str) -> bool:
        """Revoke a refresh token (logout)."""
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token == refresh_token)
        )
        token = result.scalar_one_or_none()
        if token is None:
            return False

        token.is_revoked = True
        await self.db.commit()
        return True

    async def create_email_verification(self, user: User) -> str:
        """Create an email verification token and return the raw token."""
        raw_token = generate_verification_token()
        verification = EmailVerification(
            user_id=user.id,
            token=raw_token,
            expires_at=datetime.utcnow() + timedelta(hours=24),
            is_used=False,
        )
        self.db.add(verification)
        await self.db.commit()
        return raw_token

    async def send_verification_email(self, user: User) -> None:
        """Create an email verification token and deliver or log it."""
        raw_token = await self.create_email_verification(user)
        verification_url = f"/auth/verify-email/{raw_token}"

        if settings.EMAIL_DEV_MODE:
            logger.info(
                "[DEV EMAIL] Verification for %s: %s",
                mask_email(user.email),
                verification_url,
            )
        else:
            # Production email delivery should be wired here.
            logger.info("Verification email queued for %s", mask_email(user.email))

    async def verify_email(self, token: str) -> bool:
        """Verify an email address using a token."""
        result = await self.db.execute(
            select(EmailVerification)
            .where(EmailVerification.token == token)
            .where(EmailVerification.is_used == False)
            .where(EmailVerification.expires_at > datetime.utcnow())
        )
        verification = result.scalar_one_or_none()

        if not verification:
            return False

        verification.is_used = True

        result = await self.db.execute(select(User).where(User.id == verification.user_id))
        user = result.scalar_one()
        user.is_email_verified = True
        user.email_verified_at = datetime.utcnow()

        await self.db.commit()
        return True

    async def create_password_reset(self, email: str) -> str | None:
        """Create a password reset token for the given email, if it exists.

        Returns the raw token so the caller can log or send it. Returns None if
        the user does not exist to avoid account enumeration.
        """
        email = _normalize_email(email)
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            return None

        raw_token = generate_password_reset_token()
        reset = PasswordReset(
            user_id=user.id,
            token=raw_token,
            expires_at=datetime.utcnow() + timedelta(hours=1),
            is_used=False,
        )
        self.db.add(reset)
        await self.db.commit()
        return raw_token

    async def send_password_reset(self, email: str) -> None:
        """Create a password reset token and deliver or log it."""
        raw_token = await self.create_password_reset(email)
        if raw_token is None:
            return

        reset_url = f"/auth/reset-password/{raw_token}"

        if settings.EMAIL_DEV_MODE:
            logger.info("[DEV EMAIL] Password reset for %s: %s", mask_email(email), reset_url)
        else:
            logger.info("Password reset email queued for %s", mask_email(email))

    async def reset_password(self, token: str, new_password: str) -> bool:
        """Reset a user's password using a valid reset token."""
        result = await self.db.execute(
            select(PasswordReset)
            .where(PasswordReset.token == token)
            .where(PasswordReset.is_used == False)
            .where(PasswordReset.expires_at > datetime.utcnow())
        )
        reset = result.scalar_one_or_none()

        if not reset:
            return False

        reset.is_used = True

        result = await self.db.execute(select(User).where(User.id == reset.user_id))
        user = result.scalar_one()
        user.hashed_password = self.hash_password(new_password)

        await self.db.commit()
        return True

    async def update_user(self, user_id: int, update_data) -> User:
        """Update user profile."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one()

        for field, value in update_data.dict(exclude_unset=True).items():
            setattr(user, field, value)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def change_password(self, user_id: int, current_password: str, new_password: str) -> bool:
        """Change user password."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one()

        if not self.verify_password(current_password, user.hashed_password):
            return False

        user.hashed_password = self.hash_password(new_password)
        await self.db.commit()
        return True
