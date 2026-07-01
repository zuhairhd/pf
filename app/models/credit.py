from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class CreditProfile(Base, TimestampMixin, TenantMixin):
    """User's credit score and history."""
    __tablename__ = "credit_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    score = Column(Integer, nullable=True)
    score_date = Column(Date, nullable=True)
    score_provider = Column(String(50), nullable=True)  # experian, equifax, transunion
    factors = Column(Text, nullable=True)  # JSON array of factor descriptions
    
    # AI analysis
    ai_trend = Column(String(20), nullable=True)  # improving, stable, declining
    ai_recommendation = Column(Text, nullable=True)


class CreditScoreHistory(Base, TimestampMixin):
    """Historical credit score records."""
    __tablename__ = "credit_score_history"
    
    id = Column(Integer, primary_key=True, index=True)
    credit_profile_id = Column(Integer, ForeignKey("credit_profiles.id"), nullable=False)
    score = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)
    change = Column(Integer, nullable=True)  # Change from previous
