from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, between
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from app.models import (
    Account, JournalEntry, JournalLine, Budget, BudgetCategory,
    Goal, Loan, Subscription, Bill, Organization, User
)
from app.models.ai import AIInsight, AIInsightType, AIInsightPriority


class HealthScoreService:
    """Calculates the Financial Health Score (0-100) across 5 dimensions."""
    
    DIMENSIONS = {
        "cash_flow": {"weight": 0.25, "name": "Cash Flow"},
        "debt_management": {"weight": 0.20, "name": "Debt Management"},
        "savings": {"weight": 0.20, "name": "Savings"},
        "budget_discipline": {"weight": 0.20, "name": "Budget Discipline"},
        "emergency_fund": {"weight": 0.15, "name": "Emergency Fund"},
    }
    
    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    async def calculate_score(self) -> Dict:
        """Calculate the overall financial health score."""
        scores = {}
        
        # Calculate each dimension
        scores["cash_flow"] = await self._calculate_cash_flow_score()
        scores["debt_management"] = await self._calculate_debt_score()
        scores["savings"] = await self._calculate_savings_score()
        scores["budget_discipline"] = await self._calculate_budget_score()
        scores["emergency_fund"] = await self._calculate_emergency_fund_score()
        
        # Calculate weighted total
        total_score = sum(
            scores[d]["score"] * self.DIMENSIONS[d]["weight"]
            for d in self.DIMENSIONS
        )
        
        # Generate insights
        insights = await self._generate_health_insights(scores)
        
        return {
            "overall_score": round(total_score),
            "max_score": 100,
            "dimensions": {
                d: {
                    "score": scores[d]["score"],
                    "weight": self.DIMENSIONS[d]["weight"],
                    "name": self.DIMENSIONS[d]["name"],
                    "status": self._get_status(scores[d]["score"]),
                    "details": scores[d]["details"],
                }
                for d in self.DIMENSIONS
            },
            "insights": insights,
            "trend": "stable",  # TODO: Compare with previous month
            "calculated_at": datetime.utcnow().isoformat(),
        }
    
    def _get_status(self, score: int) -> str:
        if score >= 80:
            return "excellent"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "fair"
        elif score >= 20:
            return "poor"
        return "critical"
    
    async def _calculate_cash_flow_score(self) -> Dict:
        """Calculate cash flow score (income vs expenses)."""
        # Get last 3 months of income and expenses
        three_months_ago = date.today() - timedelta(days=90)
        
        result = await self.db.execute(
            select(
                Account.account_type,
                func.coalesce(func.sum(JournalLine.debit), Decimal('0')),
                func.coalesce(func.sum(JournalLine.credit), Decimal('0'))
            )
            .join(JournalLine, Account.id == JournalLine.account_id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(JournalEntry.date >= three_months_ago)
            .where(Account.account_type.in_(["Income", "Expense"]))
            .group_by(Account.account_type)
        )
        rows = result.all()
        
        total_income = Decimal('0')
        total_expenses = Decimal('0')
        
        for row in rows:
            account_type, debit, credit = row
            if account_type == "Income":
                # Income: credit increases, debit decreases
                total_income += credit - debit
            elif account_type == "Expense":
                # Expense: debit increases, credit decreases
                total_expenses += debit - credit
        
        total_income = float(total_income)
        total_expenses = float(total_expenses)
        
        if total_income <= 0:
            score = 0
            details = {"income": 0, "expenses": total_expenses, "surplus": -total_expenses}
        else:
            savings_rate = (total_income - total_expenses) / total_income
            score = min(100, max(0, int(savings_rate * 100)))
            details = {
                "income": total_income,
                "expenses": total_expenses,
                "surplus": total_income - total_expenses,
                "savings_rate": round(savings_rate * 100, 1),
            }
        
        return {"score": score, "details": details}
    
    async def _calculate_debt_score(self) -> Dict:
        """Calculate debt management score."""
        result = await self.db.execute(
            select(Loan).where(Loan.tenant_id == self.tenant_id).where(Loan.is_active == True)
        )
        loans = result.scalars().all()
        
        if not loans:
            return {"score": 100, "details": {"message": "No active debt", "total_debt": 0, "debt_to_income": 0}}
        
        total_debt = sum(float(l.current_balance) for l in loans)
        total_min_payments = sum(float(l.minimum_payment or 0) for l in loans)
        avg_interest_rate = sum(float(l.interest_rate) for l in loans) / len(loans) if loans else 0
        
        # Get monthly income
        result = await self.db.execute(
            select(func.coalesce(func.sum(JournalLine.credit), Decimal('0')))
            .join(Account, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Income")
            .where(JournalEntry.date >= date.today() - timedelta(days=30))
        )
        monthly_income = float(result.scalar() or 0)
        
        debt_to_income = (total_min_payments / monthly_income * 100) if monthly_income > 0 else 0
        
        # Score: lower debt-to-income is better
        if debt_to_income <= 10:
            score = 100
        elif debt_to_income <= 20:
            score = 80
        elif debt_to_income <= 30:
            score = 60
        elif debt_to_income <= 40:
            score = 40
        else:
            score = 20
        
        return {
            "score": score,
            "details": {
                "total_debt": total_debt,
                "total_min_payments": total_min_payments,
                "debt_to_income": round(debt_to_income, 1),
                "avg_interest_rate": round(avg_interest_rate * 100, 2),
                "loan_count": len(loans),
            }
        }
    
    async def _calculate_savings_score(self) -> Dict:
        """Calculate savings score."""
        # Get savings account balance
        result = await self.db.execute(
            select(func.coalesce(func.sum(Account.current_balance), Decimal('0')))
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Asset")
            .where(Account.is_active == True)
        )
        total_assets = float(result.scalar() or 0)
        
        # Get goal progress
        result = await self.db.execute(
            select(Goal).where(Goal.tenant_id == self.tenant_id).where(Goal.status == "active")
        )
        goals = result.scalars().all()
        
        total_goal_target = sum(float(g.target_amount) for g in goals)
        total_goal_current = sum(float(g.current_amount) for g in goals)
        
        goal_progress = (total_goal_current / total_goal_target * 100) if total_goal_target > 0 else 0
        
        # Score based on assets and goal progress
        score = min(100, int((goal_progress * 0.6) + (min(total_assets / 10000, 1) * 40)))
        
        return {
            "score": score,
            "details": {
                "total_assets": total_assets,
                "active_goals": len(goals),
                "goal_progress": round(goal_progress, 1),
                "total_goal_target": total_goal_target,
                "total_goal_current": total_goal_current,
            }
        }
    
    async def _calculate_budget_score(self) -> Dict:
        """Calculate budget discipline score."""
        result = await self.db.execute(
            select(Budget).where(Budget.tenant_id == self.tenant_id).where(Budget.is_active == True)
        )
        budgets = result.scalars().all()
        
        if not budgets:
            return {"score": 50, "details": {"message": "No active budgets", "budget_count": 0}}
        
        total_budgeted = sum(float(b.total_budgeted) for b in budgets)
        total_actual = sum(float(b.total_actual) for b in budgets)
        
        variance = ((total_actual - total_budgeted) / total_budgeted * 100) if total_budgeted > 0 else 0
        
        # Score: closer to 0% variance is better
        if variance <= 0:
            score = 100  # Under budget
        elif variance <= 5:
            score = 90
        elif variance <= 10:
            score = 80
        elif variance <= 20:
            score = 60
        elif variance <= 30:
            score = 40
        else:
            score = 20
        
        return {
            "score": score,
            "details": {
                "budget_count": len(budgets),
                "total_budgeted": total_budgeted,
                "total_actual": total_actual,
                "variance": round(variance, 1),
                "status": "under" if variance <= 0 else "over",
            }
        }
    
    async def _calculate_emergency_fund_score(self) -> Dict:
        """Calculate emergency fund score."""
        # Get essential monthly expenses (last 3 months average)
        three_months_ago = date.today() - timedelta(days=90)
        
        result = await self.db.execute(
            select(func.coalesce(func.sum(JournalLine.debit), Decimal('0')))
            .join(Account, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Expense")
            .where(JournalEntry.date >= three_months_ago)
        )
        total_expenses = float(result.scalar() or 0)
        monthly_expenses = total_expenses / 3
        
        # Get liquid assets (cash + bank accounts)
        result = await self.db.execute(
            select(func.coalesce(func.sum(Account.current_balance), Decimal('0')))
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Asset")
            .where(Account.is_active == True)
            .where(Account.is_bank_account == True or Account.is_cash_account == True)
        )
        liquid_assets = float(result.scalar() or 0)
        
        # Months of expenses covered
        months_covered = (liquid_assets / monthly_expenses) if monthly_expenses > 0 else 0
        
        # Target: 3-6 months
        if months_covered >= 6:
            score = 100
        elif months_covered >= 3:
            score = int(60 + (months_covered - 3) / 3 * 40)
        else:
            score = int(months_covered / 3 * 60)
        
        return {
            "score": score,
            "details": {
                "liquid_assets": liquid_assets,
                "monthly_expenses": round(monthly_expenses, 2),
                "months_covered": round(months_covered, 1),
                "target_months": 6,
                "gap": round(max(0, 6 - months_covered) * monthly_expenses, 2),
            }
        }
    
    async def _generate_health_insights(self, scores: Dict) -> List[Dict]:
        """Generate AI-style insights based on health scores."""
        insights = []
        
        # Find lowest scoring dimension
        lowest = min(scores.items(), key=lambda x: x[1]["score"])
        dimension, data = lowest
        
        if data["score"] < 40:
            insights.append({
                "type": "warning",
                "title": f"{self.DIMENSIONS[dimension]['name']} Needs Attention",
                "message": f"Your {self.DIMENSIONS[dimension]['name'].lower()} score is {data['score']}/100. This is your biggest opportunity for improvement.",
                "priority": "high",
            })
        
        # Check for positive trends
        highest = max(scores.items(), key=lambda x: x[1]["score"])
        if highest[1]["score"] >= 80:
            insights.append({
                "type": "positive",
                "title": f"Strong {self.DIMENSIONS[highest[0]]['name']}",
                "message": f"Great job! Your {self.DIMENSIONS[highest[0]]['name'].lower()} is in excellent shape.",
                "priority": "low",
            })
        
        # Add specific recommendations
        if scores["cash_flow"]["score"] < 60:
            insights.append({
                "type": "recommendation",
                "title": "Increase Your Savings Rate",
                "message": "Try to save at least 20% of your income. Consider reducing discretionary expenses.",
                "priority": "high",
            })
        
        if scores["emergency_fund"]["score"] < 50:
            insights.append({
                "type": "recommendation",
                "title": "Build Your Emergency Fund",
                "message": f"Aim for 3-6 months of expenses. Current gap: {scores['emergency_fund']['details'].get('gap', 0)}",
                "priority": "critical",
            })
        
        return insights
