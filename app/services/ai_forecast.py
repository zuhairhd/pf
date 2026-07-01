from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from app.models import Account, JournalEntry, JournalLine, Goal, Loan
from app.schemas.ai import WhatIfRequest, WhatIfResponse


class AIForecastService:
    """Financial forecasting and what-if scenario service."""
    
    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    async def simulate_scenario(self, scenario: str) -> WhatIfResponse:
        """Run a what-if scenario simulation."""
        scenario_lower = scenario.lower()
        
        if "save" in scenario_lower or "saving" in scenario_lower:
            return await self._simulate_savings_increase(scenario)
        elif "car" in scenario_lower or "house" in scenario_lower or "purchase" in scenario_lower:
            return await self._simulate_major_purchase(scenario)
        elif "salary" in scenario_lower or "income" in scenario_lower:
            return await self._simulate_income_change(scenario)
        elif "debt" in scenario_lower or "pay off" in scenario_lower:
            return await self._simulate_debt_payoff(scenario)
        else:
            return WhatIfResponse(
                scenario=scenario,
                impact_summary="I can help you analyze various financial scenarios. Try asking about: increasing savings, making a major purchase, changing your income, or paying off debt.",
                recommendations=[
                    "Be specific about amounts and timeframes for better analysis",
                    "Consider both short-term and long-term impacts",
                ],
                confidence=60,
            )
    
    async def _simulate_savings_increase(self, scenario: str) -> WhatIfResponse:
        """Simulate impact of increasing monthly savings."""
        # Extract amount from scenario (simplified parsing)
        import re
        amount_match = re.search(r'(\d+(?:\.\d+)?)', scenario)
        extra_savings = float(amount_match.group(1)) if amount_match else 100
        
        # Get current financial data
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).where(Account.account_type == "Asset")
        )
        assets = result.scalars().all()
        current_savings = sum(float(a.current_balance) for a in assets)
        
        # Get active goals
        result = await self.db.execute(
            select(Goal).where(Goal.tenant_id == self.tenant_id).where(Goal.status == "active")
        )
        goals = result.scalars().all()
        
        # Calculate impact over 1 year
        yearly_extra = extra_savings * 12
        projected_savings = current_savings + yearly_extra
        
        # Impact on goals
        goal_impacts = []
        for goal in goals:
            remaining = float(goal.target_amount) - float(goal.current_amount)
            current_monthly = float(goal.monthly_contribution)
            new_monthly = current_monthly + extra_savings
            
            if new_monthly > 0:
                months_to_goal = remaining / new_monthly
                goal_impacts.append({
                    'goal': goal.name,
                    'current_months': remaining / current_monthly if current_monthly > 0 else None,
                    'new_months': months_to_goal,
                    'months_saved': (remaining / current_monthly - months_to_goal) if current_monthly > 0 else None,
                })
        
        return WhatIfResponse(
            scenario=scenario,
            impact_summary=f"Saving an extra {extra_savings}/month would add {yearly_extra:.2f} to your savings in one year.",
            projected_changes=[
                {'metric': 'Annual Savings', 'current': current_savings, 'projected': projected_savings, 'change': yearly_extra},
            ],
            recommendations=[
                f"Set up an automatic transfer of {extra_savings} to your savings account",
                "Review your budget to find areas where you can reduce spending",
                "Consider prioritizing goals with the highest interest rates or earliest deadlines",
            ],
            confidence=85,
        )
    
    async def _simulate_major_purchase(self, scenario: str) -> WhatIfResponse:
        """Simulate impact of a major purchase."""
        import re
        amount_match = re.search(r'(\d+(?:\.\d+)?)', scenario)
        purchase_amount = float(amount_match.group(1)) if amount_match else 10000
        
        # Get current assets
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).where(Account.account_type == "Asset")
        )
        assets = result.scalars().all()
        current_assets = sum(float(a.current_balance) for a in assets)
        
        remaining_after = current_assets - purchase_amount
        
        return WhatIfResponse(
            scenario=scenario,
            impact_summary=f"A purchase of {purchase_amount:.2f} would reduce your liquid assets from {current_assets:.2f} to {remaining_after:.2f}.",
            projected_changes=[
                {'metric': 'Liquid Assets', 'current': current_assets, 'projected': remaining_after, 'change': -purchase_amount},
            ],
            recommendations=[
                f"Ensure you still have 3-6 months of expenses in emergency savings after this purchase",
                "Consider the total cost of ownership (maintenance, insurance, etc.)",
                "If financing, compare interest rates and terms from multiple lenders",
            ],
            confidence=80,
        )
    
    async def _simulate_income_change(self, scenario: str) -> WhatIfResponse:
        """Simulate impact of income change."""
        import re
        percent_match = re.search(r'(\d+(?:\.\d+)?)\s*%', scenario)
        percent_change = float(percent_match.group(1)) if percent_match else 10
        
        # Get current income
        result = await self.db.execute(
            select(func.coalesce(func.sum(JournalLine.credit), Decimal('0')))
            .join(Account, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Income")
            .where(JournalEntry.date >= date.today() - timedelta(days=30))
        )
        monthly_income = float(result.scalar() or 0)
        
        income_change = monthly_income * (percent_change / 100)
        new_monthly = monthly_income + income_change
        yearly_change = income_change * 12
        
        return WhatIfResponse(
            scenario=scenario,
            impact_summary=f"A {percent_change}% increase in income would add {income_change:.2f}/month ({yearly_change:.2f}/year) to your finances.",
            projected_changes=[
                {'metric': 'Monthly Income', 'current': monthly_income, 'projected': new_monthly, 'change': income_change},
                {'metric': 'Annual Income', 'current': monthly_income * 12, 'projected': new_monthly * 12, 'change': yearly_change},
            ],
            recommendations=[
                "Allocate 50% of the increase to savings/debt repayment",
                "Consider increasing retirement contributions",
                "Review and potentially accelerate your financial goals",
            ],
            confidence=90,
        )
    
    async def _simulate_debt_payoff(self, scenario: str) -> WhatIfResponse:
        """Simulate impact of extra debt payments."""
        import re
        amount_match = re.search(r'(\d+(?:\.\d+)?)', scenario)
        extra_payment = float(amount_match.group(1)) if amount_match else 100
        
        # Get active loans
        result = await self.db.execute(
            select(Loan).where(Loan.tenant_id == self.tenant_id).where(Loan.is_active == True)
        )
        loans = result.scalars().all()
        
        total_current_balance = sum(float(l.current_balance) for l in loans)
        total_interest = sum(float(l.interest_rate) * float(l.current_balance) for l in loans)
        
        return WhatIfResponse(
            scenario=scenario,
            impact_summary=f"Adding {extra_payment}/month to debt payments would accelerate your payoff and reduce total interest paid.",
            projected_changes=[
                {'metric': 'Total Debt', 'current': total_current_balance, 'projected': total_current_balance - extra_payment * 12, 'change': -extra_payment * 12},
            ],
            recommendations=[
                "Focus extra payments on the highest interest rate debt first (avalanche method)",
                "Consider consolidating high-interest debts",
                "Set up automatic extra payments to ensure consistency",
            ],
            confidence=85,
        )
    
    async def forecast_cash_flow(self, months: int = 12) -> Dict:
        """Forecast cash flow for the next N months."""
        # Get historical monthly income and expenses
        result = await self.db.execute(
            select(func.coalesce(func.sum(JournalLine.credit), Decimal('0')))
            .join(Account, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Income")
            .where(JournalEntry.date >= date.today() - timedelta(days=90))
        )
        avg_monthly_income = float(result.scalar() or 0) / 3
        
        result = await self.db.execute(
            select(func.coalesce(func.sum(JournalLine.debit), Decimal('0')))
            .join(Account, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Expense")
            .where(JournalEntry.date >= date.today() - timedelta(days=90))
        )
        avg_monthly_expenses = float(result.scalar() or 0) / 3
        
        forecast = []
        for month in range(1, months + 1):
            forecast_date = date.today() + timedelta(days=30 * month)
            forecast.append({
                'month': forecast_date.strftime('%Y-%m'),
                'projected_income': avg_monthly_income,
                'projected_expenses': avg_monthly_expenses,
                'projected_savings': avg_monthly_income - avg_monthly_expenses,
            })
        
        return {
            'forecast': forecast,
            'avg_monthly_income': avg_monthly_income,
            'avg_monthly_expenses': avg_monthly_expenses,
            'avg_monthly_savings': avg_monthly_income - avg_monthly_expenses,
        }
