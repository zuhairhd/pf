from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional

from app.models import Goal, GoalContribution
from app.schemas.goal import GoalCreate, GoalUpdate, GoalContributionCreate


class GoalService:
    """Financial goal tracking and planning service."""
    
    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    async def create_goal(self, goal_data: GoalCreate) -> Goal:
        """Create a new financial goal."""
        goal = Goal(
            tenant_id=self.tenant_id,
            name=goal_data.name,
            goal_type=goal_data.goal_type,
            target_amount=goal_data.target_amount,
            target_date=goal_data.target_date,
            monthly_contribution=goal_data.monthly_contribution,
            description=goal_data.description,
            priority=goal_data.priority,
        )
        self.db.add(goal)
        await self.db.commit()
        await self.db.refresh(goal)
        return goal
    
    async def add_contribution(self, goal_id: int, contribution_data: GoalContributionCreate) -> GoalContribution:
        """Add a contribution to a goal."""
        result = await self.db.execute(
            select(Goal).where(Goal.id == goal_id).where(Goal.tenant_id == self.tenant_id)
        )
        goal = result.scalar_one_or_none()
        if not goal:
            raise ValueError("Goal not found")
        
        contribution = GoalContribution(
            goal_id=goal_id,
            amount=contribution_data.amount,
            date=contribution_data.date,
            description=contribution_data.description,
        )
        self.db.add(contribution)
        
        # Update goal current amount
        goal.current_amount += contribution_data.amount
        
        # Check if goal is completed
        if goal.current_amount >= goal.target_amount:
            goal.status = "completed"
        
        await self.db.commit()
        await self.db.refresh(contribution)
        return contribution
    
    async def get_goal_progress(self, goal_id: int) -> Dict:
        """Get detailed progress for a goal."""
        result = await self.db.execute(
            select(Goal).where(Goal.id == goal_id).where(Goal.tenant_id == self.tenant_id)
        )
        goal = result.scalar_one_or_none()
        if not goal:
            return {}
        
        target = float(goal.target_amount)
        current = float(goal.current_amount)
        progress = (current / target * 100) if target > 0 else 0
        remaining = target - current
        
        # Calculate months to completion
        monthly = float(goal.monthly_contribution)
        if monthly > 0:
            months_to_completion = remaining / monthly
            estimated_completion = date.today() + timedelta(days=int(months_to_completion * 30))
        else:
            months_to_completion = None
            estimated_completion = None
        
        # Get contribution history
        result = await self.db.execute(
            select(GoalContribution)
            .where(GoalContribution.goal_id == goal_id)
            .order_by(GoalContribution.date.desc())
        )
        contributions = result.scalars().all()
        
        return {
            'goal': goal,
            'target': target,
            'current': current,
            'remaining': remaining,
            'progress_percentage': round(progress, 1),
            'monthly_contribution': monthly,
            'months_to_completion': months_to_completion,
            'estimated_completion': estimated_completion,
            'contributions': contributions,
            'is_on_track': estimated_completion is None or (goal.target_date and estimated_completion <= goal.target_date),
        }
    
    async def calculate_optimal_contribution(self, goal_id: int) -> Dict:
        """Calculate optimal monthly contribution to reach goal on time."""
        result = await self.db.execute(
            select(Goal).where(Goal.id == goal_id).where(Goal.tenant_id == self.tenant_id)
        )
        goal = result.scalar_one_or_none()
        if not goal or not goal.target_date:
            return {}
        
        target = float(goal.target_amount)
        current = float(goal.current_amount)
        remaining = target - current
        
        months_remaining = (goal.target_date - date.today()).days / 30
        if months_remaining <= 0:
            return {'status': 'overdue', 'message': 'Goal date has passed'}
        
        optimal_monthly = remaining / months_remaining
        
        return {
            'remaining_amount': remaining,
            'months_remaining': round(months_remaining, 1),
            'optimal_monthly': round(optimal_monthly, 2),
            'current_monthly': float(goal.monthly_contribution),
            'gap': round(optimal_monthly - float(goal.monthly_contribution), 2),
            'recommendation': f"Increase monthly contribution to {optimal_monthly:.2f} to reach your goal on time.",
        }
    
    async def get_all_goals_summary(self) -> Dict:
        """Get summary of all active goals."""
        result = await self.db.execute(
            select(Goal).where(Goal.tenant_id == self.tenant_id).where(Goal.status == "active")
        )
        goals = result.scalars().all()
        
        total_target = sum(float(g.target_amount) for g in goals)
        total_current = sum(float(g.current_amount) for g in goals)
        total_monthly = sum(float(g.monthly_contribution) for g in goals)
        
        return {
            'goals': goals,
            'total_goals': len(goals),
            'total_target': total_target,
            'total_current': total_current,
            'overall_progress': round((total_current / total_target * 100), 1) if total_target > 0 else 0,
            'total_monthly_contribution': total_monthly,
        }
