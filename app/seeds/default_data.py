"""Idempotent default seed data for development.

This module seeds:
- Global platform subscription plan configuration (code-level; no plan table exists).
- A single development tenant/organization.
- A development super-admin user (email/password from env or generated).
- A default OMR-friendly Chart of Accounts under the development tenant.
- A default monthly budget with categories linked to expense accounts.
- Default notification preferences for the development user.
- A system audit event recording the seed operation.

All tenant-scoped inserts set `app.current_tenant_id` via `SET LOCAL` so RLS
policies remain active and satisfied.
"""

from __future__ import annotations

import os
import secrets
import string
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rls import set_tenant_context_async, clear_tenant_context_async
from app.models import (
    Account,
    AuditLog,
    Budget,
    BudgetCategory,
    BudgetPeriod,
    NotificationSetting,
    NotificationType,
    Organization,
    SubscriptionPlan,
    SubscriptionStatus,
    SystemEvent,
    TenantSubscription,
    User,
    UserRole,
)
from app.services.auth_service import AuthService


# ---------------------------------------------------------------------------
# Platform plan configurations
# ---------------------------------------------------------------------------

PLAN_CONFIGS: dict[str, dict[str, Any]] = {
    SubscriptionPlan.FREE.value: {
        "max_users": 1,
        "max_transactions": 100,
        "max_ai_requests_per_day": 5,
        "max_storage_mb": 100,
    },
    SubscriptionPlan.PREMIUM.value: {
        "max_users": 2,
        "max_transactions": 1000,
        "max_ai_requests_per_day": 50,
        "max_storage_mb": 1024,
    },
    SubscriptionPlan.FAMILY.value: {
        "max_users": 6,
        "max_transactions": 2000,
        "max_ai_requests_per_day": 100,
        "max_storage_mb": 5120,
    },
    SubscriptionPlan.PROFESSIONAL.value: {
        "max_users": 10,
        "max_transactions": 10000,
        "max_ai_requests_per_day": 500,
        "max_storage_mb": 20480,
    },
}


# ---------------------------------------------------------------------------
# Chart of Accounts for personal finance (OMR-oriented)
# ---------------------------------------------------------------------------

CHART_OF_ACCOUNTS: list[dict[str, Any]] = [
    # Assets
    {"code": "1000", "name": "Cash", "account_type": "Asset", "is_cash_account": True},
    {"code": "1010", "name": "Bank Muscat", "account_type": "Asset", "is_bank_account": True},
    {"code": "1020", "name": "OAB Bank", "account_type": "Asset", "is_bank_account": True},
    {"code": "1030", "name": "Alizz Bank", "account_type": "Asset", "is_bank_account": True},
    {"code": "1040", "name": "Sohar International Bank", "account_type": "Asset", "is_bank_account": True},
    {"code": "1050", "name": "National Bank of Oman", "account_type": "Asset", "is_bank_account": True},
    {"code": "1060", "name": "Wallet", "account_type": "Asset", "is_cash_account": True},
    {"code": "1070", "name": "Savings Account", "account_type": "Asset", "is_bank_account": True},
    # Liabilities
    {"code": "2000", "name": "Credit Card", "account_type": "Liability", "is_credit_card": True},
    {"code": "2010", "name": "Personal Loan", "account_type": "Liability"},
    {"code": "2020", "name": "Family Loan", "account_type": "Liability"},
    {"code": "2030", "name": "Sister Account Liability", "account_type": "Liability"},
    # Equity
    {"code": "3000", "name": "Opening Balance", "account_type": "Equity"},
    {"code": "3010", "name": "Retained Earnings", "account_type": "Equity"},
    # Income
    {"code": "4000", "name": "Salary", "account_type": "Income"},
    {"code": "4010", "name": "Rental Income", "account_type": "Income"},
    {"code": "4020", "name": "Other Income", "account_type": "Income"},
    # Expenses
    {"code": "5000", "name": "Food & Groceries", "account_type": "Expense"},
    {"code": "5010", "name": "Dining Out", "account_type": "Expense"},
    {"code": "5020", "name": "Transport", "account_type": "Expense"},
    {"code": "5030", "name": "Fuel", "account_type": "Expense"},
    {"code": "5040", "name": "Utilities", "account_type": "Expense"},
    {"code": "5050", "name": "Internet & Phone", "account_type": "Expense"},
    {"code": "5060", "name": "Education", "account_type": "Expense"},
    {"code": "5070", "name": "Medical", "account_type": "Expense"},
    {"code": "5080", "name": "Family Support", "account_type": "Expense"},
    {"code": "5090", "name": "Housemaid / Domestic Help", "account_type": "Expense"},
    {"code": "5100", "name": "Insurance", "account_type": "Expense"},
    {"code": "5110", "name": "Bank Charges", "account_type": "Expense"},
    {"code": "5120", "name": "Charity", "account_type": "Expense"},
    {"code": "5130", "name": "Miscellaneous", "account_type": "Expense"},
]


# ---------------------------------------------------------------------------
# Default budget categories mapped to expense account names
# ---------------------------------------------------------------------------

DEFAULT_BUDGET_CATEGORIES: list[dict[str, Any]] = [
    {"name": "Food & Groceries", "account_name": "Food & Groceries", "budgeted_amount": Decimal("300.000")},
    {"name": "Dining Out", "account_name": "Dining Out", "budgeted_amount": Decimal("100.000")},
    {"name": "Transport", "account_name": "Transport", "budgeted_amount": Decimal("80.000")},
    {"name": "Fuel", "account_name": "Fuel", "budgeted_amount": Decimal("120.000")},
    {"name": "Utilities", "account_name": "Utilities", "budgeted_amount": Decimal("70.000")},
    {"name": "Internet & Phone", "account_name": "Internet & Phone", "budgeted_amount": Decimal("40.000")},
    {"name": "Education", "account_name": "Education", "budgeted_amount": Decimal("200.000")},
    {"name": "Medical", "account_name": "Medical", "budgeted_amount": Decimal("50.000")},
    {"name": "Family Support", "account_name": "Family Support", "budgeted_amount": Decimal("150.000")},
    {"name": "Housemaid / Domestic Help", "account_name": "Housemaid / Domestic Help", "budgeted_amount": Decimal("100.000")},
    {"name": "Insurance", "account_name": "Insurance", "budgeted_amount": Decimal("60.000")},
    {"name": "Bank Charges", "account_name": "Bank Charges", "budgeted_amount": Decimal("20.000")},
    {"name": "Charity", "account_name": "Charity", "budgeted_amount": Decimal("50.000")},
    {"name": "Miscellaneous", "account_name": "Miscellaneous", "budgeted_amount": Decimal("80.000")},
]


# ---------------------------------------------------------------------------
# Default notification preferences
# ---------------------------------------------------------------------------

DEFAULT_NOTIFICATION_PREFS: list[dict[str, Any]] = [
    # In-app only by default; email disabled until SMTP is configured
    {"notification_type": NotificationType.BUDGET_ALERT, "in_app": True, "email": False, "push": False, "sms": False},
    {"notification_type": NotificationType.GOAL_MILESTONE, "in_app": True, "email": False, "push": False, "sms": False},
    {"notification_type": NotificationType.BILL_DUE, "in_app": True, "email": False, "push": False, "sms": False},
    {"notification_type": NotificationType.AI_INSIGHT, "in_app": True, "email": False, "push": False, "sms": False},
    {"notification_type": NotificationType.AI_RECOMMENDATION, "in_app": True, "email": False, "push": False, "sms": False},
    {"notification_type": NotificationType.ANOMALY_DETECTED, "in_app": True, "email": False, "push": False, "sms": False},
    {"notification_type": NotificationType.SUBSCRIPTION_RENEWAL, "in_app": True, "email": False, "push": False, "sms": False},
    {"notification_type": NotificationType.SYSTEM, "in_app": True, "email": False, "push": False, "sms": False},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_temp_password(length: int = 20) -> str:
    """Generate a cryptographically secure temporary password.

    bcrypt truncates passwords longer than 72 bytes, so keep the generated
    password well under that limit.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_+="
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def _get_or_create(
    db: AsyncSession,
    model_cls: type,
    filters: dict[str, Any],
    defaults: dict[str, Any] | None = None,
) -> tuple[Any, bool]:
    """Async get-or-create helper.

    Returns (instance, created).
    """
    stmt = select(model_cls)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model_cls, key) == value)
    result = await db.execute(stmt)
    instance = result.scalar_one_or_none()
    if instance is not None:
        return instance, False

    instance = model_cls(**filters, **(defaults or {}))
    db.add(instance)
    await db.flush()
    await db.refresh(instance)
    return instance, True


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

async def seed_development_organization(db: AsyncSession) -> Organization:
    """Create the development tenant if it does not exist."""
    plan = SubscriptionPlan.FAMILY
    config = PLAN_CONFIGS[plan.value]

    org, created = await _get_or_create(
        db,
        Organization,
        filters={"slug": "dev-family"},
        defaults={
            "name": "Development Family",
            "description": "Development and testing tenant. Not for production use.",
            "plan": plan,
            "status": SubscriptionStatus.ACTIVE,
            "max_users": config["max_users"],
            "max_transactions": config["max_transactions"],
            "max_ai_requests_per_day": config["max_ai_requests_per_day"],
            "max_storage_mb": config["max_storage_mb"],
        },
    )
    if created:
        # Record a subscription history row for audit consistency.
        # tenant_subscriptions is organization-scoped, so set RLS context.
        await set_tenant_context_async(db, org.id)
        db.add(
            TenantSubscription(
                organization_id=org.id,
                plan=plan,
                status=SubscriptionStatus.ACTIVE,
                started_at=datetime.utcnow(),
                ends_at=None,
                amount=Decimal("0.00"),
                currency="OMR",
            )
        )
        await db.flush()

    return org


def _prepare_password_for_hash(password: str) -> str:
    """Ensure a password fits bcrypt's 72-byte limit.

    bcrypt silently truncates passwords longer than 72 bytes. To avoid the
    modern bcrypt error, we truncate explicitly and warn when this happens.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        print(
            "WARNING: DEV_SUPERUSER_PASSWORD exceeds bcrypt's 72-byte limit; "
            "truncating before hashing."
        )
        return encoded[:72].decode("utf-8", errors="ignore")
    return password


async def seed_development_superuser(db: AsyncSession, org: Organization) -> tuple[User, str | None]:
    """Create or update the development super-admin user.

    Email is read from DEV_SUPERUSER_EMAIL. Password is read from
    DEV_SUPERUSER_PASSWORD; if missing, a temporary password is generated only
    when creating the user and returned so the caller can print it once.
    """
    settings = get_settings()
    email = os.getenv("DEV_SUPERUSER_EMAIL", "dev@example.local")
    password = os.getenv("DEV_SUPERUSER_PASSWORD")
    temp_password: str | None = None

    auth_service = AuthService(db)

    # Generate a temp password only if we will actually create the user and no
    # env password was supplied.
    if not password:
        temp_password = _generate_temp_password()
        password_to_hash = temp_password
    else:
        password_to_hash = _prepare_password_for_hash(password)

    user, created = await _get_or_create(
        db,
        User,
        filters={"email": email},
        defaults={
            "hashed_password": auth_service.hash_password(password_to_hash),
            "first_name": "Development",
            "last_name": "Superuser",
            "is_active": True,
            "is_email_verified": True,
            "is_superuser": True,
            "organization_id": org.id,
            "role": UserRole.OWNER,
            "currency": "OMR",
            "language": "en",
            "timezone": "Asia/Muscat",
            "theme": "light",
        },
    )

    if not created:
        # Ensure the existing dev user remains a super admin in the dev org.
        user.is_superuser = True
        user.organization_id = org.id
        user.role = UserRole.OWNER
        # Only update the password if an explicit env password was provided.
        if password:
            user.hashed_password = auth_service.hash_password(_prepare_password_for_hash(password))
        await db.flush()
        await db.refresh(user)
        # Do not return a temp password for an existing user.
        temp_password = None

    return user, temp_password


async def seed_chart_of_accounts(db: AsyncSession, tenant_id: int) -> list[Account]:
    """Seed the default Chart of Accounts under the given tenant."""
    await set_tenant_context_async(db, tenant_id)

    created_accounts: list[Account] = []
    account_by_code: dict[str, Account] = {}

    for data in CHART_OF_ACCOUNTS:
        account, created = await _get_or_create(
            db,
            Account,
            filters={"tenant_id": tenant_id, "code": data["code"]},
            defaults={
                "name": data["name"],
                "account_type": data["account_type"],
                "is_active": True,
                "is_bank_account": data.get("is_bank_account", False),
                "is_cash_account": data.get("is_cash_account", False),
                "is_credit_card": data.get("is_credit_card", False),
            },
        )
        if created:
            created_accounts.append(account)
        account_by_code[data["code"]] = account

    await db.flush()
    return list(account_by_code.values())


async def seed_default_budget(
    db: AsyncSession,
    tenant_id: int,
    accounts: list[Account],
) -> Budget | None:
    """Seed a default monthly budget with categories linked to expense accounts."""
    await set_tenant_context_async(db, tenant_id)

    account_by_name = {acc.name: acc for acc in accounts}
    today = date.today()
    # Start of current month to end of current month.
    start_date = today.replace(day=1)
    if today.month == 12:
        end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    total_budgeted = sum(cat["budgeted_amount"] for cat in DEFAULT_BUDGET_CATEGORIES)

    budget, created = await _get_or_create(
        db,
        Budget,
        filters={"tenant_id": tenant_id, "name": "Monthly Household Budget"},
        defaults={
            "period": BudgetPeriod.MONTHLY,
            "start_date": start_date,
            "end_date": end_date,
            "total_budgeted": total_budgeted,
            "total_actual": Decimal("0.000"),
            "is_active": True,
        },
    )

    if created:
        for cat_data in DEFAULT_BUDGET_CATEGORIES:
            account = account_by_name.get(cat_data["account_name"])
            db.add(
                BudgetCategory(
                    budget_id=budget.id,
                    name=cat_data["name"],
                    account_id=account.id if account else None,
                    budgeted_amount=cat_data["budgeted_amount"],
                    actual_amount=Decimal("0.000"),
                    alert_threshold=Decimal("80.00"),
                )
            )
        await db.flush()
        await db.refresh(budget)

    return budget


async def seed_notification_settings(db: AsyncSession, user: User) -> list[NotificationSetting]:
    """Seed safe default notification preferences for the user."""
    created_settings: list[NotificationSetting] = []

    for pref in DEFAULT_NOTIFICATION_PREFS:
        setting, created = await _get_or_create(
            db,
            NotificationSetting,
            filters={"user_id": user.id, "notification_type": pref["notification_type"]},
            defaults={
                "in_app": pref["in_app"],
                "email": pref["email"],
                "push": pref["push"],
                "sms": pref["sms"],
            },
        )
        if created:
            created_settings.append(setting)

    await db.flush()
    return created_settings


async def seed_system_event(db: AsyncSession, org: Organization, user: User) -> SystemEvent:
    """Record that default seed data was applied."""
    event = SystemEvent(
        event_type="info",
        source="seed_default_data",
        message="Default development seed data applied.",
        details_json=f'{{"organization_id": {org.id}, "organization_slug": "{org.slug}", "user_id": {user.id}}}',
        severity="info",
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event


async def seed_all_default_data(
    db: AsyncSession,
    *,
    print_temp_password: bool = True,
) -> dict[str, Any]:
    """Run the complete default seed process idempotently.

    Returns a summary dict with created/found IDs and any temporary password.
    """
    summary: dict[str, Any] = {
        "organization": None,
        "user": None,
        "accounts_count": 0,
        "budget": None,
        "notification_settings_count": 0,
        "temp_password": None,
    }

    # 1. Development tenant.
    org = await seed_development_organization(db)
    summary["organization"] = {"id": org.id, "slug": org.slug, "name": org.name}

    # 2. Development super-admin (global user table).
    user, temp_password = await seed_development_superuser(db, org)
    summary["user"] = {"id": user.id, "email": user.email, "is_superuser": user.is_superuser}
    summary["temp_password"] = temp_password

    if print_temp_password and temp_password:
        print("\n" + "=" * 70)
        print("DEVELOPMENT SUPERUSER PASSWORD GENERATED")
        print("=" * 70)
        print(f"Email:    {user.email}")
        print(f"Password: {temp_password}")
        print("Store this password securely. It will not be shown again.")
        print("=" * 70 + "\n")

    # 3. Chart of Accounts (tenant-scoped).
    accounts = await seed_chart_of_accounts(db, org.id)
    summary["accounts_count"] = len(accounts)

    # 4. Default budget and categories (tenant-scoped).
    budget = await seed_default_budget(db, org.id, accounts)
    if budget:
        summary["budget"] = {"id": budget.id, "name": budget.name}

    # 5. Notification settings (user-scoped global table).
    notification_settings = await seed_notification_settings(db, user)
    summary["notification_settings_count"] = len(notification_settings)

    # 6. System audit event.
    await seed_system_event(db, org, user)

    # Clear tenant context before returning.
    await clear_tenant_context_async(db)

    return summary
