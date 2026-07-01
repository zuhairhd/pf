from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models import User, Organization
from app.schemas.user import UserUpdate, UserPreferenceUpdate
from app.services.auth_service import AuthService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def profile_page(request: Request, db: AsyncSession = Depends(get_db)):
    """User profile page."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    return templates.TemplateResponse("profile/index.html", {
        "request": request,
        "user": user,
    })


@router.post("/update")
async def update_profile(update: UserUpdate, db: AsyncSession = Depends(get_db)):
    """Update user profile."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    auth_service = AuthService(db)
    user = await auth_service.update_user(user_id, update)
    
    return user


@router.post("/change-password")
async def change_password(current_password: str, new_password: str, db: AsyncSession = Depends(get_db)):
    """Change user password."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    auth_service = AuthService(db)
    success = await auth_service.change_password(user_id, current_password, new_password)
    
    if not success:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    return {"message": "Password changed successfully"}
