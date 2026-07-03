from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional

import json
import re

from app.ai_cfo.llm.client import LLMClient, LLMError
from app.ai_cfo.llm.cost_control import CostController
from app.ai_cfo.llm.prompts import daily_brief_prompt, insight_prompt
from app.ai_cfo.llm.safety import SafetyFilter
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

        # Calculate health score
        from app.services.health_score_service import HealthScoreService
        health_service = HealthScoreService(self.db, self.tenant_id)
        health_score = await health_service.calculate_score()

        # Generate content (LLM-augmented with fallback)
        content = await self._generate_daily_brief_content(financial_data, health_score)

        # Create report
        report = AIReport(
            tenant_id=self.tenant_id,
            report_type="daily",
            period_start=date.today(),
            period_end=date.today(),
            title=f"Daily Brief - {date.today().strftime('%B %d, %Y')}",
            content=content,
            summary=health_score['insights'][0]['message'] if health_score.get('insights') else "No significant changes today.",
            health_score=health_score['overall_score'],
            metrics_json=str(health_score['dimensions']),
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)
        return report

    async def _generate_daily_brief_content(
        self, financial_data: dict, health_score: dict
    ) -> str:
        """Generate daily brief content using LLM with rule-based fallback."""
        cost_controller = CostController(self.db, self.tenant_id)
        allowed, _, _ = await cost_controller.check_limit()
        client = LLMClient()

        if allowed and client.is_configured():
            try:
                response = await client.complete(
                    messages=daily_brief_prompt(financial_data, health_score),
                    temperature=0.7,
                    max_tokens=800,
                )
                await cost_controller.record_usage(
                    model=response.model,
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    total_tokens=response.total_tokens,
                    cost_usd=response.cost_usd,
                    request_type="report",
                )
                safety = SafetyFilter()
                return safety.sanitize(response.content)
            except LLMError:
                pass

        return self._format_daily_brief([], health_score)
    
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
        """Generate insights from financial data, LLM-augmented with rule-based fallback."""
        cost_controller = CostController(self.db, self.tenant_id)
        allowed, _, _ = await cost_controller.check_limit()
        client = LLMClient()

        if allowed and client.is_configured():
            try:
                response = await client.complete(
                    messages=insight_prompt(data),
                    temperature=0.6,
                    max_tokens=1000,
                )
                llm_insights = self._parse_llm_insights(response.content)
                if llm_insights:
                    await cost_controller.record_usage(
                        model=response.model,
                        prompt_tokens=response.prompt_tokens,
                        completion_tokens=response.completion_tokens,
                        total_tokens=response.total_tokens,
                        cost_usd=response.cost_usd,
                        request_type="insight",
                    )
                    return llm_insights
            except LLMError:
                pass

        return self._rule_based_insights(data)

    def _parse_llm_insights(self, content: str) -> List[Dict]:
        """Parse JSON insight list from LLM output."""
        # Some models wrap JSON in markdown code fences.
        match = re.search(r"```(?:json)?\s*(\[.*\])\s*```", content, re.DOTALL)
        if match:
            content = match.group(1)

        try:
            raw_insights = json.loads(content)
        except json.JSONDecodeError:
            return []

        insights = []
        for item in raw_insights:
            if not isinstance(item, dict):
                continue
            insight_type = item.get("type", "general").lower()
            priority = item.get("priority", "medium").lower()
            insights.append({
                "type": self._map_insight_type(insight_type),
                "priority": self._map_insight_priority(priority),
                "title": item.get("title", "Insight"),
                "message": item.get("message", ""),
                "confidence": min(100, max(0, int(item.get("confidence", 80)))),
                "featured": False,
            })
        return insights

    def _map_insight_type(self, value: str) -> AIInsightType:
        """Map a string type to the AIInsightType enum."""
        mapping = {
            "cash_flow": AIInsightType.CASH_FLOW,
            "expense": AIInsightType.EXPENSE,
            "income": AIInsightType.INCOME,
            "debt": AIInsightType.DEBT,
            "budget": AIInsightType.BUDGET,
            "savings": AIInsightType.SAVINGS,
            "emergency_fund": AIInsightType.EMERGENCY_FUND,
            "investment": AIInsightType.INVESTMENT,
            "retirement": AIInsightType.RETIREMENT,
            "goal": AIInsightType.GOAL,
            "risk": AIInsightType.RISK,
            "subscription": AIInsightType.SUBSCRIPTION,
        }
        return mapping.get(value, AIInsightType.GENERAL)

    def _map_insight_priority(self, value: str) -> AIInsightPriority:
        """Map a string priority to the AIInsightPriority enum."""
        mapping = {
            "critical": AIInsightPriority.CRITICAL,
            "high": AIInsightPriority.HIGH,
            "medium": AIInsightPriority.MEDIUM,
            "low": AIInsightPriority.LOW,
        }
        return mapping.get(value, AIInsightPriority.MEDIUM)

    def _rule_based_insights(self, data: Dict) -> List[Dict]:
        """Generate rule-based insights when LLM is unavailable."""
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
