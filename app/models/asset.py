from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class Asset(Base, TimestampMixin, TenantMixin):
    """A real-world asset (real estate, vehicle, valuables)."""
    __tablename__ = "assets"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    asset_type = Column(String(50), nullable=False)  # real_estate, vehicle, electronics, jewelry, other
    purchase_date = Column(Date, nullable=True)
    purchase_price = Column(Numeric(15, 3), nullable=True)
    current_value = Column(Numeric(15, 3), nullable=False)
    depreciation_rate = Column(Numeric(5, 4), nullable=True)  # Annual rate
    appreciation_rate = Column(Numeric(5, 4), nullable=True)  # Annual rate
    description = Column(Text, nullable=True)
    documents = Column(Text, nullable=True)  # JSON array of document IDs


class Investment(Base, TimestampMixin, TenantMixin):
    """An investment holding (stock, bond, crypto, etc.)."""
    __tablename__ = "investments"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    asset_class = Column(String(50), nullable=False)  # stock, bond, etf, crypto, mutual_fund, reit
    quantity = Column(Numeric(15, 6), nullable=False)
    cost_basis = Column(Numeric(15, 3), nullable=False)
    current_price = Column(Numeric(15, 3), nullable=True)
    unrealized_gain_loss = Column(Numeric(15, 3), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    
    # AI fields
    ai_recommendation = Column(Text, nullable=True)
    risk_score = Column(Numeric(5, 2), nullable=True)
