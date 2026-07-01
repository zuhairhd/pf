from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
import enum

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class LoanType(str, enum.Enum):
    PERSONAL = "personal"
    CREDIT_CARD = "credit_card"
    MORTGAGE = "mortgage"
    AUTO = "auto"
    STUDENT = "student"
    FAMILY = "family"
    OTHER = "other"


class RepaymentStrategy(str, enum.Enum):
    SNOWBALL = "snowball"
    AVALANCHE = "avalanche"
    CUSTOM = "custom"


class Loan(Base, TimestampMixin, TenantMixin):
    """A loan or debt account."""
    __tablename__ = "loans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    lender = Column(String(200), nullable=False)
    loan_type = Column(SQLEnum(LoanType), default=LoanType.PERSONAL, nullable=False)
    
    # Terms
    original_principal = Column(Numeric(15, 3), nullable=False)
    current_balance = Column(Numeric(15, 3), nullable=False)
    interest_rate = Column(Numeric(5, 4), nullable=False)  # Annual rate, e.g., 0.0525 for 5.25%
    term_months = Column(Integer, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    minimum_payment = Column(Numeric(15, 3), nullable=True)
    
    # Strategy
    repayment_strategy = Column(SQLEnum(RepaymentStrategy), default=RepaymentStrategy.AVALANCHE, nullable=False)
    extra_payment = Column(Numeric(15, 3), default=Decimal('0'), nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_paid_off = Column(Boolean, default=False, nullable=False)
    paid_off_date = Column(Date, nullable=True)
    
    # Linked account
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    
    # Relationships
    payments = relationship("LoanPayment", back_populates="loan", cascade="all, delete-orphan")


class LoanPayment(Base, TimestampMixin):
    """A payment made toward a loan."""
    __tablename__ = "loan_payments"
    
    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False)
    payment_date = Column(Date, nullable=False)
    total_payment = Column(Numeric(15, 3), nullable=False)
    principal_paid = Column(Numeric(15, 3), nullable=False)
    interest_paid = Column(Numeric(15, 3), nullable=False)
    remaining_balance = Column(Numeric(15, 3), nullable=False)
    is_scheduled = Column(Boolean, default=False, nullable=False)
    
    loan = relationship("Loan", back_populates="payments")
