from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from app.config import get_settings
from app.models.database import init_db, close_db
from app.middleware.tenant_scoping import TenantScopingMiddleware
from app.middleware.logging import LoggingMiddleware
from app.middleware.error_handling import setup_error_handlers
from app.routers import auth, dashboard, accounts, transactions, budgets, goals, loans, ai as ai_router, notifications, documents, profile, admin

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered personal finance SaaS platform",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Middleware
app.add_middleware(LoggingMiddleware)
app.add_middleware(TenantScopingMiddleware)

# Error handlers
setup_error_handlers(app)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(accounts.router, prefix="/accounts", tags=["Accounts"])
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
app.include_router(budgets.router, prefix="/budgets", tags=["Budgets"])
app.include_router(goals.router, prefix="/goals", tags=["Goals"])
app.include_router(loans.router, prefix="/loans", tags=["Loans"])
app.include_router(ai_router.router, prefix="/ai", tags=["AI Coach"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(profile.router, prefix="/profile", tags=["Profile"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])


@app.get("/")
async def root(request: Request):
    """Redirect to dashboard or login."""
    return templates.TemplateResponse("dashboard/index.html", {"request": request})


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok", "service": settings.APP_NAME}
