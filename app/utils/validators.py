from pydantic import BaseModel, validator
from typing import Optional
import re


class Validators:
    """Custom validation utilities."""
    
    @staticmethod
    def validate_password(password: str) -> tuple[bool, Optional[str]]:
        """Validate password strength."""
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        
        if not re.search(r'\d', password):
            return False, "Password must contain at least one digit"
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"
        
        return True, None
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Validate phone number format."""
        # Allow international format: +1234567890
        pattern = r'^\+?[\d\s-]{10,20}$'
        return bool(re.match(pattern, phone))
    
    @staticmethod
    def validate_currency_code(code: str) -> bool:
        """Validate ISO 4217 currency code."""
        return len(code) == 3 and code.isalpha() and code.isupper()
    
    @staticmethod
    def validate_hex_color(color: str) -> bool:
        """Validate hex color code."""
        return bool(re.match(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$', color))


class PasswordValidator:
    """Pydantic-compatible password validator."""
    
    @classmethod
    def validate(cls, v: str) -> str:
        is_valid, error = Validators.validate_password(v)
        if not is_valid:
            raise ValueError(error)
        return v
