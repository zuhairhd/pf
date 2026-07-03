from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from typing import Optional, List

from app.ai_cfo.llm.client import LLMClient, LLMError
from app.ai_cfo.llm.cost_control import CostController
from app.ai_cfo.llm.prompts import chat_prompt
from app.ai_cfo.llm.safety import SafetyFilter
from app.models.ai import AIChatSession, AIChatMessage
from app.schemas.ai import ChatRequest, ChatResponse
from app.config import get_settings

settings = get_settings()


class AIChatService:
    """AI conversational chat service."""
    
    def __init__(self, db: AsyncSession, tenant_id: int, user_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
    
    async def chat(self, message: str, session_id: Optional[int] = None) -> ChatResponse:
        """Process a chat message and return AI response."""
        # Get or create session
        if session_id:
            result = await self.db.execute(
                select(AIChatSession).where(AIChatSession.id == session_id)
            )
            session = result.scalar_one_or_none()
        else:
            session = None

        if not session:
            session = AIChatSession(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                title=message[:50] + "..." if len(message) > 50 else message,
            )
            self.db.add(session)
            await self.db.flush()

        # Store user message
        user_message = AIChatMessage(
            session_id=session.id,
            role="user",
            content=message,
        )
        self.db.add(user_message)

        # Generate AI response using LLM with rule-based fallback.
        response = await self._generate_response(message, session.id)

        # Store AI response
        ai_message = AIChatMessage(
            session_id=session.id,
            role="assistant",
            content=response.answer,
            tokens_used=response.tokens_used,
            cost=response.estimated_cost,
            model=settings.OPENAI_MODEL,
        )
        self.db.add(ai_message)
        await self.db.commit()

        return response

    async def _generate_response(self, message: str, session_id: int) -> ChatResponse:
        """Generate AI response using LLM, with rule-based fallback."""
        safety = SafetyFilter()
        input_check = safety.check_input(message)
        if not input_check["allowed"]:
            return ChatResponse(
                answer=input_check["warning"],
                confidence=100,
                disclaimer=safety.disclaimer,
                tokens_used=0,
                estimated_cost=0.0,
            )

        # Enforce tenant daily limit before calling the LLM.
        cost_controller = CostController(self.db, self.tenant_id)
        allowed, used, limit = await cost_controller.check_limit()
        if not allowed:
            return ChatResponse(
                answer=(
                    f"You've reached your daily AI usage limit ({limit} requests). "
                    "Please try again tomorrow or upgrade your plan."
                ),
                confidence=100,
                disclaimer=safety.disclaimer,
                tokens_used=0,
                estimated_cost=0.0,
            )

        client = LLMClient()
        if client.is_configured():
            try:
                context = {"currency": settings.CURRENCY_DEFAULT}
                llm_response = await client.complete(
                    messages=chat_prompt(message, context=context),
                    temperature=0.7,
                    max_tokens=800,
                )

                await cost_controller.record_usage(
                    model=llm_response.model,
                    prompt_tokens=llm_response.prompt_tokens,
                    completion_tokens=llm_response.completion_tokens,
                    total_tokens=llm_response.total_tokens,
                    cost_usd=llm_response.cost_usd,
                    request_type="chat",
                    user_id=self.user_id,
                )

                answer = safety.sanitize(llm_response.content)
                return ChatResponse(
                    answer=answer,
                    confidence=85,
                    tokens_used=llm_response.total_tokens,
                    estimated_cost=llm_response.cost_usd,
                    disclaimer=safety.disclaimer,
                )
            except LLMError:
                # Fall through to rule-based fallback.
                pass

        return await self._rule_based_response(message)

    async def _rule_based_response(self, message: str) -> ChatResponse:
        """Return a helpful rule-based response when the LLM is unavailable."""
        safety = SafetyFilter()
        lower_msg = message.lower()

        if "budget" in lower_msg:
            answer = "I can help you analyze your budget. Based on your current spending patterns, I recommend reviewing your discretionary expenses. Would you like me to show you a detailed breakdown?"
        elif "goal" in lower_msg or "save" in lower_msg:
            answer = "Setting financial goals is great! I can help you create a savings plan and track your progress. What are you saving for?"
        elif "debt" in lower_msg or "loan" in lower_msg:
            answer = "I can analyze your debt situation and recommend the best repayment strategy (snowball vs avalanche). Would you like to see your current debt overview?"
        elif "invest" in lower_msg:
            answer = "I can provide educational guidance on investment diversification and asset allocation. Remember, I'm not a licensed financial advisor, but I can help you understand the basics."
        elif "can i afford" in lower_msg:
            answer = "To determine if you can afford something, I need to analyze your cash flow, existing commitments, and financial goals. Let me check your current financial position."
        elif "net worth" in lower_msg:
            answer = "Your net worth is the total of your assets minus your liabilities. I can track this over time and show you trends. Would you like to see your net worth timeline?"
        else:
            answer = "I'm your AI Financial Coach. I can help you with budgeting, goal planning, debt optimization, spending analysis, and financial forecasting. What specific area would you like to explore?"

        answer = safety.add_disclaimer(answer)
        return ChatResponse(
            answer=answer,
            confidence=85,
            actions=[
                {"type": "view_budget", "label": "View Budget", "url": "/budgets/"},
                {"type": "view_goals", "label": "View Goals", "url": "/goals/"},
            ],
            follow_up_questions=[
                "How can I improve my savings rate?",
                "Which loan should I pay off first?",
                "Am I on track for retirement?",
            ],
            disclaimer=safety.disclaimer,
            tokens_used=0,
            estimated_cost=0.0,
        )
    
    async def get_chat_history(self, session_id: int) -> List[AIChatMessage]:
        """Get chat history for a session."""
        result = await self.db.execute(
            select(AIChatMessage)
            .where(AIChatMessage.session_id == session_id)
            .order_by(AIChatMessage.created_at)
        )
        return result.scalars().all()
