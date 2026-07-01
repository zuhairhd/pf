from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional

from app.models import Budget, BudgetCategory, BudgetAlert, Account, JournalEntry, JournalLine
from app.schemas.budget import BudgetCreate, BudgetUpdate


class BudgetService:
    """Budget management and tracking service."""
    
    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    async def create_budget(self, budget_data: BudgetCreate) -> Budget:
        """Create a new budget with categories."""
        # Calculate total budgeted
        total_budgeted = sum(cat.budgeted_amount for cat in budget_data.categories)
        
        budget = Budget(
            tenant_id=self.tenant_id,
            name=budget_data.name,
            period=budget_data.period,
            start_date=budget_data.start_date,
            end_date=budget_data.end_date,
            total_budgeted=total_budgeted,
        )
        self.db.add(budget)
        await self.db.flush()
        
        # Add categories
        for cat_data in budget_data.categories:
            category = BudgetCategory(
                budget_id=budget.id,
                name=cat_data.name,
                account_id=cat_data.account_id,
                budgeted_amount=cat_data.budgeted_amount,
                alert_threshold=cat_data.alert_threshold,
            )
            self.db.add(category)
        
        await self.db.commit()
        await self.db.refresh(budget)
        return budget
    
    async def get_budget_vs_actual(self, budget_id: int) -> Dict:
        """Compare budgeted vs actual spending."""
        result = await self.db.execute(
            select(Budget).where(Budget.id == budget_id).where(Budget.tenant_id == self.tenant_id)
        )
        budget = result.scalar_one_or_none()
        if not budget:
            return {}
        
        # Get actual spending for each category
        category_data = []
        total_actual = Decimal('0')
        
        for category in budget.categories:
            actual = await self._get_category_actual(
                category.account_id, budget.start_date, budget.end_date
            )
            variance = category.budgeted_amount - actual
            percentage = (actual / category.budgeted_amount * 100) if category.budgeted_amount > 0 else 0
            
            category_data.append({
                'category': category,
                'budgeted': category.budgeted_amount,
                'actual': actual,
                'variance': variance,
                'percentage': percentage,
                'status': 'under' if variance >= 0 else 'over',
            })
            total_actual += actual
        
        # Update budget totals
        budget.total_actual = total_actual
        await self.db.commit()
        
        return {
            'budget': budget,
            'categories': category_data,
            'total_budgeted': budget.total_budgeted,
            'total_actual': total_actual,
            'total_variance': budget.total_budgeted - total_actual,
        }
    
    async def check_budget_alerts(self, budget_id: int) -> List[Dict]:
        """Check for budget overspending alerts."""
        vs_actual = await self.get_budget_vs_actual(budget_id)
        alerts = []
        
        for cat_data in vs_actual.get('categories', []):
            percentage = cat_data['percentage']
            threshold = float(cat_data['category'].alert_threshold)
            
            if percentage >= 100:
                alerts.append({
                    'type': 'budget_depleted',
                    'category': cat_data['category'].name,
                    'message': f"Budget depleted for {cat_data['category'].name}. Spent {percentage:.1f}% of budget.",
                    'priority': 'high',
                })
            elif percentage >= threshold:
                alerts.append({
                    'type': 'threshold_exceeded',
                    'category': cat_data['category'].name,
                    'message': f"You've used {percentage:.1f}% of your {cat_data['category'].name} budget (alert at {threshold}%).",
                    'priority': 'medium',
                })
        
        return alerts
    
    async def _get_category_actual(self, account_id: Optional[int], start_date: date, end_date: date) -> Decimal:
        """Get actual spending for a category (account) in a date range."""
        if not account_id:
            return Decimal('0')
        
        result = await self.db.execute(
            select(func.coalesce(func.sum(JournalLine.debit), Decimal('0')))
            .join(JournalEntry)
            .where(JournalLine.account_id == account_id)
            .where(JournalEntry.date >= start_date)
            .where(JournalEntry.date <= end_date)
        )
        return result.scalar() or Decimal('0')
    
    async def forecast_remaining_budget(self, budget_id: int) -> Dict:
        """Forecast remaining budget for the period."""
        vs_actual = await self.get_budget_vs_actual(budget_id)
        budget = vs_actual['budget']
        
        total_budgeted = float(budget.total_budgeted)
        total_actual = float(vs_actual['total_actual'])
        
        # Days elapsed vs total days
        today = date.today()
        total_days = (budget.end_date - budget.start_date).days
        days_elapsed = (today - budget.start_date).days
        days_remaining = total_days - days_elapsed
        
        if days_elapsed <= 0 or total_days <= 0:
            return {'status': 'just_started', 'message': 'Budget period just started'}
        
        # Current spending rate
        daily_rate = total_actual / days_elapsed
        projected_total = daily_rate * total_days
        
        # Remaining budget
        remaining = total_budgeted - total_actual
        projected_remaining = total_budgeted - projected_total
        
        return {
            'total_budgeted': total_budgeted,
            'total_actual': total_actual,
            'remaining': remaining,
            'days_elapsed': days_elapsed,
            'days_remaining': days_remaining,
            'daily_spending_rate': daily_rate,
            'projected_total': projected_total,
            'projected_remaining': projected_remaining,
            'status': 'on_track' if projected_remaining >= 0 else 'over_budget',
            'message': f"At current rate, you'll {'have' if projected_remaining >= 0 else 'exceed by'} {abs(projected_remaining):.2f} remaining",
        }
