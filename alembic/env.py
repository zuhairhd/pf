import asyncio
from logging.config import fileConfig
import os
import sys

from sqlalchemy import create_engine, pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import context

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load settings from .env directly (avoid importing app package which triggers async engine creation)
from dotenv import load_dotenv
load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/pf_ai")
# Convert async URL to sync URL for Alembic
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")

# Import Base and all models directly
from app.models.database import Base

# Import all models to register them with metadata
from app.models.tenant import Organization, TenantSubscription
from app.models.user import User, FamilyMember
from app.models.auth import RefreshToken, EmailVerification, PasswordReset
from app.models.accounting import Account, JournalEntry, JournalLine, RecurringTransaction
from app.models.budget import Budget, BudgetCategory, BudgetAlert
from app.models.goal import Goal, GoalContribution
from app.models.loan import Loan, LoanPayment
from app.models.subscription import Subscription, Bill
from app.models.notification import Notification, NotificationSetting
from app.models.ai import AIInsight, AIReport, AIChatSession, AIChatMessage
from app.models.audit import AuditLog, SystemEvent
from app.models.analytics import UserActivity, FeatureUsage, AITokenUsage
from app.models.asset import Asset, Investment
from app.models.credit import CreditProfile, CreditScoreHistory
from app.models.document import Document, DocumentType
from app.models.tax import TaxProfile, TaxPayment

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target_metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=SYNC_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using sync engine."""
    connectable = create_engine(
        SYNC_DATABASE_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
