from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from typing import Optional, List

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
        
        # Generate AI response (placeholder - will integrate with OpenAI)
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
        """Generate AI response using OpenAI API (placeholder implementation)."""
        # TODO: Integrate with OpenAI API
        # For now, return a helpful placeholder response
        
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
            disclaimer="This is educational guidance only. Not financial advice.",
            tokens_used=150,
            estimated_cost=0.002,
        )
    
    async def get_chat_history(self, session_id: int) -> List[AIChatMessage]:
        """Get chat history for a session."""
        result = await self.db.execute(
            select(AIChatMessage)
            .where(AIChatMessage.session_id == session_id)
            .order_by(AIChatMessage.created_at)
        )
        return result.scalars().all()
