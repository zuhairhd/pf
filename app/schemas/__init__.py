# Schemas package
from app.schemas.auth import UserCreate, UserLogin, TokenResponse, UserUpdate
from app.schemas.accounting import AccountCreate, AccountUpdate, JournalEntryCreate, TransferCreate
from app.schemas.budget import BudgetCreate, BudgetUpdate
from app.schemas.goal import (
    GoalCreate,
    GoalUpdate,
    GoalContributionCreate,
    FamilyGoalCreate,
    FamilyGoalUpdate,
    GoalResponse,
    GoalContributionResponse,
    GoalProgressResponse,
)
from app.schemas.loan import LoanCreate, LoanPaymentCreate
from app.schemas.ai import ChatRequest, ChatResponse, WhatIfRequest, WhatIfResponse
from app.schemas.notification import NotificationCreate, NotificationSettingUpdate
from app.schemas.user import UserCreate as UserProfileCreate, UserUpdate as UserProfileUpdate
from app.schemas.common import PaginatedResponse, ErrorResponse
