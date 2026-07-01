import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from app.config import get_settings

settings = get_settings()


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    """Hash a token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_verification_token() -> str:
    """Generate email verification token."""
    return generate_secure_token(32)


def generate_password_reset_token() -> str:
    """Generate password reset token."""
    return generate_secure_token(48)


def generate_api_key() -> str:
    """Generate API key."""
    prefix = "pf_"
    return prefix + generate_secure_token(32)


def mask_email(email: str) -> str:
    """Mask an email address for display."""
    if "@" not in email:
        return email
    
    local, domain = email.split("@")
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    
    return f"{masked_local}@{domain}"


def mask_card_number(card_number: str) -> str:
    """Mask a credit card number."""
    if len(card_number) < 4:
        return "****"
    return "*" * (len(card_number) - 4) + card_number[-4:]
