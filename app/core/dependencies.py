from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator

from app.models.database import get_db
from app.core.rls import set_tenant_context_async, clear_tenant_context_async


async def get_db_with_tenant(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AsyncSession:
    """Database dependency that sets PostgreSQL RLS tenant context.
    
    This dependency wraps the standard get_db() and sets the tenant_id
    in the PostgreSQL session using SET LOCAL, so RLS policies can filter
    rows at the database level.
    
    Usage in routes:
        @router.get("/items")
        async def list_items(
            db: AsyncSession = Depends(get_db_with_tenant),
        ):
            # db session already has RLS context set
            ...
    
    Args:
        request: The FastAPI request object (injected automatically).
        db: The database session from get_db().
    
    Returns:
        The database session with RLS tenant context set.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    if tenant_id is not None:
        await set_tenant_context_async(db, tenant_id)
    else:
        # Clear any existing tenant context to prevent cross-tenant leakage
        await clear_tenant_context_async(db)
    
    return db
