"""Schemas for the AI-centric Dashboard v2 "Today" payload (AI-1223)."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel

from app.schemas.ai import ConfidenceFields


class DashboardAlertItem(BaseModel):
    alert_type: str
    severity: str
    title: str
    message: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    confidence_score: Optional[float] = None
    confidence_label: Optional[str] = None


class DashboardInsightItem(BaseModel):
    type: str
    title: str
    message: str
    confidence_score: Optional[float] = None
    confidence_label: Optional[str] = None
    link: Optional[str] = None


class DashboardCommitmentsSummary(BaseModel):
    upcoming_bills_count: int
    upcoming_bills_total: str
    overdue_bills_count: int
    overdue_bills_total: str
    upcoming_renewals_count: int
    upcoming_renewals_total: str
    monthly_subscription_total: str
    total_fixed_commitments_this_month: str
    currency: str


class DashboardGoalsSummary(BaseModel):
    active_goals_count: int
    total_target: float
    total_current: float
    remaining: float
    overall_progress: float
    currency: str


class DashboardQuickAction(BaseModel):
    label: str
    description: str
    url: str
    icon: str


class DashboardToday(ConfidenceFields):
    greeting: str
    today: str
    summary: str
    disclaimer: str
    health_score: Optional[dict[str, Any]] = None
    alerts: List[DashboardAlertItem] = []
    commitments: DashboardCommitmentsSummary
    goals: DashboardGoalsSummary
    insights: List[DashboardInsightItem] = []
    suggested_actions: List[str] = []
    suggested_questions: List[str] = []
    quick_actions: List[DashboardQuickAction] = []
    currency: str
