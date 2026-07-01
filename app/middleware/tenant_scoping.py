from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from app.config import get_settings

settings = get_settings()


class TenantScopingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts tenant_id from the authenticated user
    and sets it in the request state for downstream use.
    
    Also stores the raw JWT payload for RLS context setting.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Extract tenant_id from JWT token or session
        tenant_id = None
        user_id = None
        
        # Try to get from Authorization header (JWT)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
            try:
                from jose import jwt
                payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
                tenant_id = payload.get("tenant_id")
                user_id = payload.get("sub")
            except Exception:
                pass
        
        # Set tenant_id and user_id in request state
        request.state.tenant_id = tenant_id
        request.state.user_id = user_id
        
        response = await call_next(request)
        return response
