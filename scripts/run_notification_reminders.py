"""Development/script runner for notification reminders.

This script generates bill and subscription reminders for a tenant. It is
intended for local development and manual testing, not as a production
scheduler (use Celery for production).

Usage:
    python scripts/run_notification_reminders.py --tenant-id 1
    python scripts/run_notification_reminders.py --tenant-id 1 --send-emails
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(".env")

# Ensure app imports work when running from scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.models.database import async_session
from app.models import User
from app.notifications import NotificationDeliveryService


async def main():
    parser = argparse.ArgumentParser(description="Run notification reminders for a tenant")
    parser.add_argument("--tenant-id", type=int, required=True, help="Tenant/organization ID")
    parser.add_argument("--send-emails", action="store_true", help="Send pending email notifications after generating reminders")
    args = parser.parse_args()

    async with async_session() as db:
        # Pick the first owner/admin user in the tenant to act as the reminder target.
        result = await db.execute(
            select(User)
            .where(User.organization_id == args.tenant_id)
            .order_by(User.id)
            .limit(1)
        )
        user = result.scalar_one_or_none()
        if user is None:
            print(f"No user found for tenant {args.tenant_id}")
            sys.exit(1)

        service = NotificationDeliveryService(db, tenant_id=args.tenant_id)
        reminder_result = await service.generate_reminders(user)
        print("Reminders generated:", reminder_result)

        if args.send_emails:
            email_result = await service.send_pending_email_notifications()
            print("Pending emails sent:", email_result)


if __name__ == "__main__":
    asyncio.run(main())
