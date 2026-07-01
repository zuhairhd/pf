import os
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from typing import Optional, Union

from app.config import get_settings

settings = get_settings()


def format_currency(value: Union[Decimal, float, int, str, None], currency: Optional[str] = None) -> str:
    """Format a value as currency with proper decimals."""
    if value is None:
        return f"0.000 {currency or settings.CURRENCY_DEFAULT}"
    
    try:
        if isinstance(value, str):
            value = Decimal(value.replace(',', ''))
        elif isinstance(value, (int, float)):
            value = Decimal(str(value))
        
        currency = currency or settings.CURRENCY_DEFAULT
        decimals = settings.CURRENCY_DECIMALS
        
        return f"{float(value):,.{decimals}f} {currency}"
    except (InvalidOperation, ValueError, TypeError):
        return f"0.000 {currency or settings.CURRENCY_DEFAULT}"


def parse_amount(value: Union[str, int, float, None]) -> Optional[Decimal]:
    """Parse a string/number into a Decimal amount."""
    if value is None or value == '':
        return Decimal('0')
    
    try:
        if isinstance(value, str):
            # Remove commas and whitespace
            cleaned = value.replace(',', '').strip()
            if cleaned == '':
                return Decimal('0')
            result = Decimal(cleaned)
            return result if result >= 0 else None
        elif isinstance(value, (int, float)):
            return Decimal(str(value)) if value >= 0 else None
    except (InvalidOperation, ValueError):
        pass
    
    return None


def format_date(value: Optional[Union[date, datetime, str]]) -> str:
    """Format a date/datetime for display."""
    if value is None:
        return ''
    
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return value
    
    if isinstance(value, datetime):
        return value.strftime('%d %b %Y %H:%M')
    
    return value.strftime('%d %b %Y')


def format_relative_date(value: Optional[date]) -> str:
    """Format a date as relative (Today, Yesterday, etc.)."""
    if value is None:
        return ''
    
    today = date.today()
    delta = (value - today).days
    
    if delta == 0:
        return 'Today'
    elif delta == -1:
        return 'Yesterday'
    elif delta == 1:
        return 'Tomorrow'
    elif delta > 1 and delta <= 7:
        return f'In {delta} days'
    elif delta < -1 and delta >= -7:
        return f'{abs(delta)} days ago'
    else:
        return value.strftime('%d %b %Y')


def truncate_text(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """Truncate text to a maximum length."""
    if not text or len(text) <= max_length:
        return text or ''
    return text[:max_length - len(suffix)] + suffix


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text[:100]


def generate_reference(prefix: str = 'REF', length: int = 4) -> str:
    """Generate a unique reference number."""
    timestamp = datetime.utcnow()
    return f"{prefix}-{timestamp.strftime('%Y%m%d')}-{timestamp.strftime('%H%M%S')[length:]}"


def calculate_percentage_change(current: Decimal, previous: Decimal) -> Optional[float]:
    """Calculate percentage change between two values."""
    if previous == 0:
        return None if current == 0 else float('inf') if current > 0 else float('-inf')
    return float((current - previous) / previous * 100)


def safe_divide(numerator: Union[Decimal, float, int], denominator: Union[Decimal, float, int], default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero."""
    try:
        result = float(numerator) / float(denominator)
        return result
    except (ZeroDivisionError, ValueError, TypeError):
        return default
