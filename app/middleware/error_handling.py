from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


class TenantNotFoundException(Exception):
    pass


class AIErrorException(Exception):
    pass


class RateLimitException(Exception):
    pass


def setup_error_handlers(app: FastAPI):
    """Configure global exception handlers."""
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "message": exc.detail,
                "status_code": exc.status_code,
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "Request validation failed",
                "details": exc.errors(),
            }
        )
    
    @app.exception_handler(TenantNotFoundException)
    async def tenant_not_found_handler(request: Request, exc: TenantNotFoundException):
        return JSONResponse(
            status_code=403,
            content={
                "error": "tenant_not_found",
                "message": "Tenant not found or access denied",
            }
        )
    
    @app.exception_handler(AIErrorException)
    async def ai_error_handler(request: Request, exc: AIErrorException):
        return JSONResponse(
            status_code=503,
            content={
                "error": "ai_service_unavailable",
                "message": "The AI service is temporarily unavailable. Please try again later.",
            }
        )
    
    @app.exception_handler(RateLimitException)
    async def rate_limit_handler(request: Request, exc: RateLimitException):
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": "Rate limit exceeded. Please try again later.",
            }
        )
    
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred. Please try again later.",
            }
        )
