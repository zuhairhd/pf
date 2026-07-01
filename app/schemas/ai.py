from pydantic import BaseModel, Field
from typing import Optional, List


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    confidence: Optional[int] = None
    actions: Optional[List[dict]] = None
    follow_up_questions: Optional[List[str]] = None
    related_insights: Optional[List[str]] = None
    disclaimer: Optional[str] = None
    tokens_used: Optional[int] = None
    estimated_cost: Optional[float] = None


class WhatIfRequest(BaseModel):
    scenario: str = Field(..., min_length=1, max_length=500)


class WhatIfResponse(BaseModel):
    scenario: str
    impact_summary: str
    projected_changes: Optional[List[dict]] = None
    recommendations: Optional[List[str]] = None
    confidence: Optional[int] = None
