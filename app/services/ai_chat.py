from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime
from typing import Optional, List

from app.ai_cfo.confidence import ConfidenceScorer
from app.ai_cfo.llm.client import LLMClient, LLMError
from app.ai_cfo.llm.cost_control import CostController
from app.ai_cfo.llm.prompts import chat_prompt
from app.ai_cfo.llm.safety import SafetyFilter
from app.models.ai import AIChatSession, AIChatMessage
from app.schemas.ai import ChatRequest, ChatResponse
from app.services.ai_memory_service import AIMemoryService, MemorySafetyError
from app.config import get_settings

settings = get_settings()


class AIChatService:
    """AI conversational chat service with session history and context."""

    def __init__(self, db: AsyncSession, tenant_id: int, user_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def list_sessions(self, limit: int = 20, offset: int = 0) -> List[AIChatSession]:
        """List chat sessions for the current tenant/user."""
        query = (
            select(AIChatSession)
            .options(selectinload(AIChatSession.messages))
            .where(AIChatSession.tenant_id == self.tenant_id)
            .order_by(AIChatSession.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if self.user_id is not None:
            query = query.where(AIChatSession.user_id == self.user_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_session(self, session_id: int) -> Optional[AIChatSession]:
        """Get a single session scoped to tenant/user."""
        query = (
            select(AIChatSession)
            .where(AIChatSession.id == session_id)
            .where(AIChatSession.tenant_id == self.tenant_id)
        )
        if self.user_id is not None:
            query = query.where(AIChatSession.user_id == self.user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_chat_history(self, session_id: int, limit: int = 100) -> List[AIChatMessage]:
        """Get chat history for a session scoped to tenant/user."""
        session = await self.get_session(session_id)
        if session is None:
            return []
        result = await self.db.execute(
            select(AIChatMessage)
            .where(AIChatMessage.session_id == session_id)
            .order_by(AIChatMessage.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_session(self, session_id: int) -> bool:
        """Delete a chat session and its messages."""
        session = await self.get_session(session_id)
        if session is None:
            return False
        await self.db.delete(session)
        await self.db.commit()
        return True

    async def chat(self, message: str, session_id: Optional[int] = None) -> ChatResponse:
        """Process a chat message and return AI response, maintaining session context."""
        session = await self._get_or_create_session(message, session_id)

        # Store user message
        user_message = AIChatMessage(
            session_id=session.id,
            role="user",
            content=message,
        )
        self.db.add(user_message)
        await self.db.flush()

        # Handle explicit memory commands before invoking the LLM.
        memory_service = AIMemoryService(self.db, self.tenant_id, self.user_id)
        cmd = memory_service.extract_memory_command(message)

        if cmd["command"] == "remember":
            response = await self._handle_remember_command(cmd["content"], memory_service)
        elif cmd["command"] == "forget":
            response = await self._handle_forget_command(cmd["content"], memory_service)
        elif cmd["command"] == "query":
            response = await self._handle_memory_query(memory_service)
        else:
            # Generate AI response using LLM with rule-based fallback.
            response = await self._generate_response(message, session)

        # Store AI response
        ai_message = AIChatMessage(
            session_id=session.id,
            role="assistant",
            content=response.answer,
            tokens_used=response.tokens_used,
            cost=response.estimated_cost,
            model=settings.OPENAI_MODEL if response.tokens_used else None,
        )
        self.db.add(ai_message)

        # Update session timestamp/title on first message
        session.updated_at = datetime.utcnow()
        if not session.title:
            session.title = self._generate_title(message)

        await self.db.commit()

        # Include session_id in response for client state
        response.session_id = session.id
        return response

    async def _handle_remember_command(
        self, content: str, memory_service: AIMemoryService
    ) -> ChatResponse:
        """Save an explicit user statement as memory and return confirmation."""
        safety = SafetyFilter()
        try:
            memory = await memory_service.create_memory_from_explicit_statement(content)
            answer = f"Got it. I'll remember that: {memory.summary or memory.value}"
            confidence = (
                ConfidenceScorer()
                .add("deterministic_calculation")
                .add("no_llm_dependency")
                .add("user_confirmed_memory")
                .build()
            )
        except MemorySafetyError as exc:
            answer = (
                "I can't save that as a memory because it may contain sensitive information. "
                f"{exc.message}"
            )
            confidence = (
                ConfidenceScorer()
                .add("deterministic_calculation")
                .add("no_llm_dependency")
                .build()
            )
        return ChatResponse(
            answer=safety.add_disclaimer(answer),
            confidence=100,
            tokens_used=0,
            estimated_cost=0.0,
            disclaimer=safety.disclaimer,
            **confidence.to_dict(),
        )

    async def _handle_forget_command(
        self, content: str, memory_service: AIMemoryService
    ) -> ChatResponse:
        """Deactivate memories matching the user's request."""
        safety = SafetyFilter()
        count = await memory_service.forget_by_query(content)
        if count:
            answer = f"I've forgotten {count} memory item(s) matching '{content}'."
        else:
            answer = f"I couldn't find any memory matching '{content}'."
        confidence = (
            ConfidenceScorer()
            .add("deterministic_calculation")
            .add("no_llm_dependency")
            .build()
        )
        return ChatResponse(
            answer=safety.add_disclaimer(answer),
            confidence=100,
            tokens_used=0,
            estimated_cost=0.0,
            disclaimer=safety.disclaimer,
            **confidence.to_dict(),
        )

    async def _handle_memory_query(
        self, memory_service: AIMemoryService
    ) -> ChatResponse:
        """Return a safe summary of active memories."""
        safety = SafetyFilter()
        summary = await memory_service.get_memory_summary()
        confidence = (
            ConfidenceScorer()
            .add("deterministic_calculation")
            .add("no_llm_dependency")
            .add("user_confirmed_memory")
            .build()
        )
        return ChatResponse(
            answer=safety.add_disclaimer(summary),
            confidence=100,
            tokens_used=0,
            estimated_cost=0.0,
            disclaimer=safety.disclaimer,
            **confidence.to_dict(),
        )

    async def _get_or_create_session(
        self, message: str, session_id: Optional[int] = None
    ) -> AIChatSession:
        """Fetch existing session or create a new one."""
        if session_id:
            session = await self.get_session(session_id)
            if session:
                return session

        session = AIChatSession(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            title=self._generate_title(message),
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    @staticmethod
    def _generate_title(message: str) -> str:
        """Generate a short title from the first user message."""
        clean = message.strip().replace("\n", " ")
        if len(clean) > 50:
            return clean[:47] + "..."
        return clean

    async def _generate_response(self, message: str, session: AIChatSession) -> ChatResponse:
        """Generate AI response using LLM, with rule-based fallback."""
        safety = SafetyFilter()
        deterministic_confidence = (
            ConfidenceScorer()
            .add("deterministic_calculation")
            .add("no_llm_dependency")
            .build()
        )

        input_check = safety.check_input(message)
        if not input_check["allowed"]:
            return ChatResponse(
                answer=input_check["warning"],
                confidence=100,
                disclaimer=safety.disclaimer,
                tokens_used=0,
                estimated_cost=0.0,
                **deterministic_confidence.to_dict(),
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
                **deterministic_confidence.to_dict(),
            )

        # Build conversation history from recent messages.
        history = await self._build_history(session.id)

        # Load durable memory context for the prompt.
        memory_service = AIMemoryService(self.db, self.tenant_id, self.user_id)
        memory_context = await memory_service.get_prompt_context()

        client = LLMClient()
        if client.is_configured():
            try:
                context = {"currency": settings.CURRENCY_DEFAULT}
                if memory_context:
                    context["memory_summary"] = memory_context
                llm_response = await client.complete(
                    messages=chat_prompt(message, context=context, history=history),
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
                # An LLM narrative does not, by itself, raise numeric confidence;
                # only confirmed memory usage adds a small personalization boost.
                llm_confidence = (
                    ConfidenceScorer()
                    .add_if(bool(memory_context), "user_confirmed_memory")
                    .build()
                )
                return ChatResponse(
                    answer=answer,
                    confidence=85,
                    tokens_used=llm_response.total_tokens,
                    estimated_cost=llm_response.cost_usd,
                    disclaimer=safety.disclaimer,
                    **llm_confidence.to_dict(),
                )
            except LLMError:
                # Fall through to rule-based fallback.
                pass

        return await self._rule_based_response(message)

    async def _build_history(self, session_id: int, max_messages: int = 10) -> list[dict[str, str]]:
        """Build a message history list for the LLM prompt."""
        messages = await self.get_chat_history(session_id, limit=max_messages)
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
            if msg.role in ("user", "assistant")
        ]

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
        # This path runs because the LLM was unavailable/unconfigured or failed.
        fallback_confidence = (
            ConfidenceScorer()
            .add("no_llm_dependency")
            .add("llm_fallback")
            .build()
        )
        return ChatResponse(
            answer=answer,
            confidence=85,
            actions=[
                {"type": "view_budget", "label": "View Budget", "url": "/budgets/"},
                {"type": "view_goals", "label": "View Goals", "url": "/goals/"},
            ],
            follow_up_questions=await self._suggested_questions(message),
            disclaimer=safety.disclaimer,
            tokens_used=0,
            estimated_cost=0.0,
            **fallback_confidence.to_dict(),
        )

    async def get_suggested_questions(self, session_id: int) -> List[str]:
        """Return suggested follow-up questions for a session."""
        session = await self.get_session(session_id)
        if session is None:
            return []
        history = await self.get_chat_history(session_id, limit=20)
        return self._suggested_questions_from_history(history)

    async def _suggested_questions(self, message: str) -> List[str]:
        """Return suggested questions based on the current message."""
        lower_msg = message.lower()
        if "budget" in lower_msg:
            return [
                "How can I reduce my discretionary spending?",
                "Which category am I overspending on?",
                "Can you help me build a monthly budget?",
            ]
        if "goal" in lower_msg or "save" in lower_msg:
            return [
                "How much should I save each month?",
                "When will I reach my savings goal?",
                "Should I open a separate savings account?",
            ]
        if "debt" in lower_msg or "loan" in lower_msg:
            return [
                "Which loan should I pay off first?",
                "How much interest will I pay?",
                "Can I afford to pay extra toward my debt?",
            ]
        if "invest" in lower_msg:
            return [
                "What is a good starter investment?",
                "How do I diversify my portfolio?",
                "What is the difference between stocks and bonds?",
            ]
        return [
            "How can I improve my savings rate?",
            "Which loan should I pay off first?",
            "Am I on track for my financial goals?",
        ]

    @staticmethod
    def _suggested_questions_from_history(history: List[AIChatMessage]) -> List[str]:
        """Return context-aware suggested questions from chat history."""
        if not history:
            return [
                "How can I improve my savings rate?",
                "Which loan should I pay off first?",
                "Am I on track for my financial goals?",
            ]

        # Use recent user messages to infer topic.
        recent_user_text = " ".join(
            msg.content for msg in history[-6:] if msg.role == "user"
        ).lower()

        if "budget" in recent_user_text:
            return [
                "How can I reduce my discretionary spending?",
                "Which category am I overspending on?",
                "Can you help me build a monthly budget?",
            ]
        if "goal" in recent_user_text or "save" in recent_user_text:
            return [
                "How much should I save each month?",
                "When will I reach my savings goal?",
                "Should I open a separate savings account?",
            ]
        if "debt" in recent_user_text or "loan" in recent_user_text:
            return [
                "Which loan should I pay off first?",
                "How much interest will I pay?",
                "Can I afford to pay extra toward my debt?",
            ]
        if "invest" in recent_user_text:
            return [
                "What is a good starter investment?",
                "How do I diversify my portfolio?",
                "What is the difference between stocks and bonds?",
            ]
        return [
            "How can I improve my savings rate?",
            "Which loan should I pay off first?",
            "Am I on track for my financial goals?",
        ]
