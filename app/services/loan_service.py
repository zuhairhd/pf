from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional

from app.models import Loan, LoanPayment
from app.schemas.loan import LoanCreate, LoanPaymentCreate


class LoanService:
    """Loan management and repayment strategy service."""
    
    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    async def create_loan(self, loan_data: LoanCreate) -> Loan:
        """Create a new loan record."""
        loan = Loan(
            tenant_id=self.tenant_id,
            name=loan_data.name,
            lender=loan_data.lender,
            loan_type=loan_data.loan_type,
            original_principal=loan_data.original_principal,
            current_balance=loan_data.current_balance,
            interest_rate=loan_data.interest_rate,
            term_months=loan_data.term_months,
            start_date=loan_data.start_date,
            minimum_payment=loan_data.minimum_payment,
            repayment_strategy=loan_data.repayment_strategy,
            extra_payment=loan_data.extra_payment,
            account_id=loan_data.account_id,
        )
        self.db.add(loan)
        await self.db.commit()
        await self.db.refresh(loan)
        return loan
    
    async def add_payment(self, loan_id: int, payment_data: LoanPaymentCreate) -> LoanPayment:
        """Add a payment to a loan."""
        result = await self.db.execute(
            select(Loan).where(Loan.id == loan_id).where(Loan.tenant_id == self.tenant_id)
        )
        loan = result.scalar_one_or_none()
        if not loan:
            raise ValueError("Loan not found")
        
        payment = LoanPayment(
            loan_id=loan_id,
            payment_date=payment_data.payment_date,
            total_payment=payment_data.total_payment,
            principal_paid=payment_data.principal_paid,
            interest_paid=payment_data.interest_paid,
            remaining_balance=payment_data.remaining_balance,
        )
        self.db.add(payment)
        
        # Update loan balance
        loan.current_balance = payment_data.remaining_balance
        if loan.current_balance <= 0:
            loan.is_paid_off = True
            loan.paid_off_date = payment_data.payment_date
            loan.is_active = False
        
        await self.db.commit()
        await self.db.refresh(payment)
        return payment
    
    async def generate_schedule(self, loan_id: int) -> List[Dict]:
        """Generate amortization schedule for a loan."""
        result = await self.db.execute(
            select(Loan).where(Loan.id == loan_id).where(Loan.tenant_id == self.tenant_id)
        )
        loan = result.scalar_one_or_none()
        if not loan:
            return []
        
        balance = float(loan.current_balance)
        rate = float(loan.interest_rate) / 12  # Monthly rate
        min_payment = float(loan.minimum_payment or 0)
        extra = float(loan.extra_payment or 0)
        monthly_payment = min_payment + extra
        
        schedule = []
        month = 0
        payment_date = date.today()
        
        while balance > 0 and month < 360:  # Max 30 years
            month += 1
            interest = balance * rate
            principal = monthly_payment - interest
            
            if principal > balance:
                principal = balance
                monthly_payment = principal + interest
            
            balance -= principal
            
            payment_date = self._add_months(payment_date, 1)
            
            schedule.append({
                'month': month,
                'date': payment_date,
                'payment': round(monthly_payment, 2),
                'principal': round(principal, 2),
                'interest': round(interest, 2),
                'balance': round(balance, 2),
            })
        
        return schedule
    
    async def calculate_payoff_strategies(self) -> Dict:
        """Calculate snowball vs avalanche payoff strategies."""
        result = await self.db.execute(
            select(Loan).where(Loan.tenant_id == self.tenant_id).where(Loan.is_active == True)
        )
        loans = result.scalars().all()
        
        if not loans:
            return {'message': 'No active loans'}
        
        # Snowball: Sort by balance (smallest first)
        snowball_loans = sorted(loans, key=lambda l: float(l.current_balance))
        
        # Avalanche: Sort by interest rate (highest first)
        avalanche_loans = sorted(loans, key=lambda l: float(l.interest_rate), reverse=True)
        
        return {
            'snowball': {
                'order': [{'name': l.name, 'balance': float(l.current_balance)} for l in snowball_loans],
                'description': 'Pay off smallest balances first for quick wins',
            },
            'avalanche': {
                'order': [{'name': l.name, 'rate': float(l.interest_rate)} for l in avalanche_loans],
                'description': 'Pay off highest interest rates first to save the most money',
            },
        }
    
    async def simulate_extra_payment(self, loan_id: int, extra_amount: float) -> Dict:
        """Simulate impact of extra payment."""
        result = await self.db.execute(
            select(Loan).where(Loan.id == loan_id).where(Loan.tenant_id == self.tenant_id)
        )
        loan = result.scalar_one_or_none()
        if not loan:
            return {}
        
        balance = float(loan.current_balance)
        rate = float(loan.interest_rate) / 12
        min_payment = float(loan.minimum_payment or 0)
        
        # Current schedule
        current_months = 0
        current_balance = balance
        while current_balance > 0 and current_months < 360:
            current_months += 1
            interest = current_balance * rate
            principal = min_payment - interest
            current_balance -= principal
        
        # With extra payment
        new_months = 0
        new_balance = balance
        new_payment = min_payment + extra_amount
        while new_balance > 0 and new_months < 360:
            new_months += 1
            interest = new_balance * rate
            principal = new_payment - interest
            if principal > new_balance:
                principal = new_balance
            new_balance -= principal
        
        months_saved = current_months - new_months
        
        return {
            'current_months': current_months,
            'new_months': new_months,
            'months_saved': months_saved,
            'extra_payment': extra_amount,
            'message': f"Adding {extra_amount}/month will pay off your loan {months_saved} months sooner.",
        }
    
    def _add_months(self, source_date: date, months: int) -> date:
        """Add months to a date."""
        month = source_date.month - 1 + months
        year = source_date.year + month // 12
        month = month % 12 + 1
        day = min(source_date.day, [31, 29 if year % 4 == 0 and not year % 100 == 0 or year % 400 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return date(year, month, day)
