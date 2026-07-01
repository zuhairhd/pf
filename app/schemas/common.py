from pydantic import BaseModel
from typing import Optional, List


class PaginatedResponse(BaseModel):
    items: List
    total: int
    page: int
    per_page: int
    total_pages: int


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[List[dict]] = None
