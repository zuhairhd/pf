"""Cost control and tenant-limit enforcement for LLM usage.

Tracks token usage per tenant, enforces daily request limits based on the
tenant's plan, and records usage to the `AITokenUsage` model.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Organization
from app.models.analytics import AITokenUsage


class CostController:
    """Enforce per-tenant LLM usage limits and record token usage."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.settings = get_settings()

    async def get_daily_usage(self, request_date: Optional[date] = None) -> int:
        """Return the number of LLM requests made by this tenant today."""
        request_date = request_date or date.today()
        start = datetime.combine(request_date, datetime.min.time())
        end = start + timedelta(days=1)

        result = await self.db.execute(
            select(func.count(AITokenUsage.id))
            .where(AITokenUsage.tenant_id == self.tenant_id)
            .where(AITokenUsage.created_at >= start)
            .where(AITokenUsage.created_at < end)
        )
        return result.scalar() or 0

    async def get_daily_limit(self) -> int:
        """Return the daily LLM request limit for this tenant's plan."""
        result = await self.db.execute(
            select(Organization.plan).where(Organization.id == self.tenant_id)
        )
        plan = (result.scalar_one_or_none() or "free").lower()

        if plan in ("premium", "family", "professional"):
            return self.settings.AI_MAX_REQUESTS_PER_DAY_PREMIUM
        return self.settings.AI_MAX_REQUESTS_PER_DAY_FREE

    async def check_limit(self) -> tuple[bool, int, int]:
        """Check whether the tenant has remaining daily LLM quota.

        Returns:
            (allowed, used, limit)
        """
        used = await self.get_daily_usage()
        limit = await self.get_daily_limit()
        return used < limit, used, limit

    async def record_usage(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_usd: float,
        request_type: str,
        user_id: Optional[int] = None,
    ) -> AITokenUsage:
        """Record LLM token usage for the tenant."""
        usage = AITokenUsage(
            tenant_id=self.tenant_id,
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=Decimal(str(cost_usd)),
            request_type=request_type,
        )
        self.db.add(usage)
        await self.db.flush()
        await self.db.refresh(usage)
        return usage
