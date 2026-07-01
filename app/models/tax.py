from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class TaxProfile(Base, TimestampMixin, TenantMixin):
    """User's tax profile and estimates."""
    __tablename__ = "tax_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    country = Column(String(50), nullable=False)
    state = Column(String(50), nullable=True)
    filing_status = Column(String(50), nullable=True)  # single, married, etc.
    dependents = Column(Integer, default=0, nullable=False)
    estimated_annual_income = Column(Numeric(15, 3), nullable=True)
    tax_bracket = Column(Numeric(5, 4), nullable=True)
    estimated_tax_liability = Column(Numeric(15, 3), nullable=True)
    
    # AI fields
    ai_quarterly_estimate = Column(Numeric(15, 3), nullable=True)
    ai_recommendation = Column(Text, nullable=True)


class TaxPayment(Base, TimestampMixin, TenantMixin):
    """Estimated or actual tax payments."""
    __tablename__ = "tax_payments"
    
    id = Column(Integer, primary_key=True, index=True)
    tax_profile_id = Column(Integer, ForeignKey("tax_profiles.id"), nullable=False)
    tax_year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=True)  # 1-4 for quarterly estimates
    amount = Column(Numeric(15, 3), nullable=False)
    due_date = Column(Date, nullable=False)
    is_paid = Column(Boolean, default=False, nullable=False)
    paid_date = Column(Date, nullable=True)
