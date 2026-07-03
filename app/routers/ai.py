from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.security import get_db_with_tenant_context
from app.models import AIInsight, AIReport, AIChatSession, AIChatMessage
from app.schemas.ai import ChatRequest, ChatResponse, WhatIfRequest, WhatIfResponse
from app.services.ai_orchestrator import AIOrchestrator
from app.services.ai_chat import AIChatService
from app.services.ai_forecast import AIForecastService
from app.config import get_settings

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """AI chat interface page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})

    # Get chat sessions
    result = await db.execute(
        select(AIChatSession)
        .where(AIChatSession.tenant_id == tenant_id)
        .order_by(AIChatSession.created_at.desc())
        .limit(10)
    )
    sessions = result.scalars().all()

    return templates.TemplateResponse("ai/chat.html", {
        "request": request,
        "sessions": sessions,
    })


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    chat_request: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """Chat with the AI Financial Coach."""
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)

    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    chat_service = AIChatService(db, tenant_id, user_id)
    response = await chat_service.chat(chat_request.message, chat_request.session_id)

    return response


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """AI insights page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})

    result = await db.execute(
        select(AIInsight)
        .where(AIInsight.tenant_id == tenant_id)
        .where(AIInsight.is_dismissed == False)
        .order_by(AIInsight.priority.desc(), AIInsight.created_at.desc())
    )
    insights = result.scalars().all()

    return templates.TemplateResponse("ai/insights.html", {
        "request": request,
        "insights": insights,
    })


@router.post("/what-if", response_model=WhatIfResponse)
async def what_if_scenario(
    request: WhatIfRequest,
    request_obj: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """Run a what-if scenario."""
    tenant_id = getattr(request_obj.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    forecast_service = AIForecastService(db, tenant_id)
    result = await forecast_service.simulate_scenario(request.scenario)

    return result


@router.get("/reports/daily")
async def get_daily_report(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """Get the latest daily AI report."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    result = await db.execute(
        select(AIReport)
        .where(AIReport.tenant_id == tenant_id)
        .where(AIReport.report_type == "daily")
        .order_by(AIReport.created_at.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()

    if not report:
        # Generate on demand
        orchestrator = AIOrchestrator(db, tenant_id)
        report = await orchestrator.generate_daily_brief()

    return report
