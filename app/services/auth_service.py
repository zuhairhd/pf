from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models import User, Organization, SubscriptionPlan, RefreshToken, EmailVerification, PasswordReset
from app.schemas.auth import UserCreate, TokenResponse
from app.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Authentication and user management service."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)
    
    def create_access_token(self, user: User) -> str:
        """Create JWT access token."""
        expires = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
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
        """Create JWT refresh token."""
        expires = datetime.utcnow() + timedelta(days=30)
        payload = {
            "sub": str(user.id),
            "exp": expires,
            "type": "refresh",
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    
    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user and their organization."""
        # Create organization
        org = Organization(
            name=f"{user_data.first_name}'s Finances",
            slug=f"{user_data.email.split('@')[0]}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            plan=SubscriptionPlan.FREE,
        )
        self.db.add(org)
        await self.db.flush()
        
        # Create user
        user = User(
            email=user_data.email,
            hashed_password=self.hash_password(user_data.password),
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            organization_id=org.id,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        return user
    
    async def authenticate(self, email: str, password: str) -> User | None:
        """Authenticate a user."""
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if not user or not self.verify_password(password, user.hashed_password):
            return None
        
        # Update last login
        user.last_login_at = datetime.utcnow()
        await self.db.commit()
        
        return user
    
    async def create_tokens(self, user: User) -> TokenResponse:
        """Create access and refresh tokens."""
        access_token = self.create_access_token(user)
        refresh_token = self.create_refresh_token(user)
        
        # Store refresh token
        token = RefreshToken(
            user_id=user.id,
            token=refresh_token,
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(token)
        await self.db.commit()
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )
    
    async def verify_email(self, token: str) -> bool:
        """Verify email with token."""
        result = await self.db.execute(
            select(EmailVerification)
            .where(EmailVerification.token == token)
            .where(EmailVerification.is_used == False)
            .where(EmailVerification.expires_at > datetime.utcnow())
        )
        verification = result.scalar_one_or_none()
        
        if not verification:
            return False
        
        # Mark as used
        verification.is_used = True
        
        # Update user
        result = await self.db.execute(select(User).where(User.id == verification.user_id))
        user = result.scalar_one()
        user.is_email_verified = True
        user.email_verified_at = datetime.utcnow()
        
        await self.db.commit()
        return True
    
    async def send_verification_email(self, user: User):
        """Send verification email (placeholder)."""
        # TODO: Implement email sending
        pass
    
    async def send_password_reset(self, email: str):
        """Send password reset email (placeholder)."""
        # TODO: Implement email sending
        pass
    
    async def reset_password(self, token: str, new_password: str) -> bool:
        """Reset password with token."""
        result = await self.db.execute(
            select(PasswordReset)
            .where(PasswordReset.token == token)
            .where(PasswordReset.is_used == False)
            .where(PasswordReset.expires_at > datetime.utcnow())
        )
        reset = result.scalar_one_or_none()
        
        if not reset:
            return False
        
        # Mark as used
        reset.is_used = True
        
        # Update user password
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
