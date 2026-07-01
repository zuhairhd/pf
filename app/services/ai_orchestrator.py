from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional

from app.models import (
    Account, JournalEntry, JournalLine, Budget, Goal, Loan,
    Subscription, Bill, Organization
)
from app.models.ai import AIInsight, AIReport, AIInsightType, AIInsightPriority


class AIOrchestrator:
    """Main AI orchestrator that coordinates all AI services."""
    
    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    async def generate_daily_brief(self) -> AIReport:
        """Generate the daily AI brief for the tenant."""
        # Gather financial data
        financial_data = await self._gather_financial_data()
        
        # Generate insights
        insights = await self._generate_insights(financial_data)
        
        # Calculate health score
        from app.services.health_score_service import HealthScoreService
        health_service = HealthScoreService(self.db, self.tenant_id)
        health_score = await health_service.calculate_score()
        
        # Create report
        report = AIReport(
            tenant_id=self.tenant_id,
            report_type="daily",
            period_start=date.today(),
            period_end=date.today(),
            title=f"Daily Brief - {date.today().strftime('%B %d, %Y')}",
            content=self._format_daily_brief(insights, health_score),
            summary=insights[0]['message'] if insights else "No significant changes today.",
            health_score=health_score['overall_score'],
            metrics_json=str(health_score['dimensions']),
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)
        return report
    
    async def generate_insights(self) -> List[AIInsight]:
        """Generate AI insights for the tenant."""
        financial_data = await self._gather_financial_data()
        insights_data = await self._generate_insights(financial_data)
        
        insights = []
        for insight_data in insights_data:
            insight = AIInsight(
                tenant_id=self.tenant_id,
                insight_type=insight_data['type'],
                priority=insight_data['priority'],
                title=insight_data['title'],
                message=insight_data['message'],
                confidence=insight_data.get('confidence', 80),
                is_featured=insight_data.get('featured', False),
            )
            self.db.add(insight)
            insights.append(insight)
        
        await self.db.commit()
        return insights
    
    async def _gather_financial_data(self) -> Dict:
        """Gather all relevant financial data for AI analysis."""
        # Get account balances
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).where(Account.is_active == True)
        )
        accounts = result.scalars().all()
        
        total_assets = sum(float(a.current_balance) for a in accounts if a.account_type == 'Asset')
        total_liabilities = sum(float(a.current_balance) for a in accounts if a.account_type == 'Liability')
        
        # Get recent transactions (last 30 days)
        thirty_days_ago = date.today() - timedelta(days=30)
        result = await self.db.execute(
            select(JournalEntry)
            .where(JournalEntry.tenant_id == self.tenant_id)
            .where(JournalEntry.date >= thirty_days_ago)
            .order_by(JournalEntry.date.desc())
        )
        recent_entries = result.scalars().all()
        
        # Get active budgets
        result = await self.db.execute(
            select(Budget).where(Budget.tenant_id == self.tenant_id).where(Budget.is_active == True)
        )
        budgets = result.scalars().all()
        
        # Get active goals
        result = await self.db.execute(
            select(Goal).where(Goal.tenant_id == self.tenant_id).where(Goal.status == "active")
        )
        goals = result.scalars().all()
        
        # Get active loans
        result = await self.db.execute(
            select(Loan).where(Loan.tenant_id == self.tenant_id).where(Loan.is_active == True)
        )
        loans = result.scalars().all()
        
        return {
            'accounts': accounts,
            'total_assets': total_assets,
            'total_liabilities': total_liabilities,
            'net_worth': total_assets - total_liabilities,
            'recent_entries': recent_entries,
            'budgets': budgets,
            'goals': goals,
            'loans': loans,
        }
    
    async def _generate_insights(self, data: Dict) -> List[Dict]:
        """Generate insights from financial data (rule-based for now)."""
        insights = []
        
        # Cash flow insight
        if data['net_worth'] < 0:
            insights.append({
                'type': AIInsightType.CASH_FLOW,
                'priority': AIInsightPriority.CRITICAL,
                'title': 'Negative Net Worth Alert',
                'message': f"Your net worth is negative ({data['net_worth']:.2f}). Focus on reducing debt and increasing savings.",
                'confidence': 95,
                'featured': True,
            })
        
        # Budget insights
        for budget in data['budgets']:
            if budget.total_actual > budget.total_budgeted:
                insights.append({
                    'type': AIInsightType.BUDGET,
                    'priority': AIInsightPriority.HIGH,
                    'title': f'Budget Exceeded: {budget.name}',
                    'message': f"You've exceeded your {budget.name} budget by {float(budget.total_actual - budget.total_budgeted):.2f}.",
                    'confidence': 100,
                })
        
        # Goal insights
        for goal in data['goals']:
            progress = float(goal.current_amount) / float(goal.target_amount) * 100 if goal.target_amount > 0 else 0
            if progress < 20 and goal.target_date and goal.target_date < date.today() + timedelta(days=90):
                insights.append({
                    'type': AIInsightType.GOAL,
                    'priority': AIInsightPriority.MEDIUM,
                    'title': f'Goal Behind Schedule: {goal.name}',
                    'message': f"Your {goal.name} goal is only {progress:.1f}% complete with the deadline approaching.",
                    'confidence': 85,
                })
        
        # Loan insights
        total_debt = sum(float(l.current_balance) for l in data['loans'])
        if total_debt > 0:
            highest_rate_loan = max(data['loans'], key=lambda l: float(l.interest_rate), default=None)
            if highest_rate_loan and float(highest_rate_loan.interest_rate) > 0.15:
                insights.append({
                    'type': AIInsightType.DEBT,
                    'priority': AIInsightPriority.HIGH,
                    'title': 'High Interest Debt Detected',
                    'message': f"Your {highest_rate_loan.name} has a high interest rate ({float(highest_rate_loan.interest_rate)*100:.1f}%). Consider prioritizing repayment.",
                    'confidence': 90,
                })
        
        # If no insights, add a positive one
        if not insights:
            insights.append({
                'type': AIInsightType.GENERAL,
                'priority': AIInsightPriority.LOW,
                'title': 'Finances Look Stable',
                'message': "Your finances appear to be on track. Keep up the good work!",
                'confidence': 70,
            })
        
        return insights
    
    def _format_daily_brief(self, insights: List[Dict], health_score: Dict) -> str:
        """Format the daily brief content."""
        lines = [
            f"## Financial Health Score: {health_score['overall_score']}/100",
            "",
            "### Key Insights:",
        ]
        
        for insight in insights[:3]:
            lines.append(f"- **{insight['title']}**: {insight['message']}")
        
        lines.extend([
            "",
            "### Recommendations:",
            "1. Review your budget categories for potential savings",
            "2. Check if you're on track with your financial goals",
            "3. Consider optimizing your debt repayment strategy",
        ])
        
        return "\n".join(lines)
