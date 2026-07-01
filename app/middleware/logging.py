import time
import json
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("pf_ai")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Structured request/response logging middleware."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log request
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }))
        
        response = await call_next(request)
        
        # Log response
        duration = time.time() - start_time
        logger.info(json.dumps({
            "event": "response",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration * 1000, 2),
        }))
        
        return response
