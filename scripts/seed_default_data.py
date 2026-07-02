#!/usr/bin/env python3
"""CLI entry point for seeding default platform and development data.

Usage:
    python scripts/seed_default_data.py --dev

The script is idempotent: running it multiple times will not create duplicates.

Environment variables:
    DEV_SUPERUSER_EMAIL     Email for the development super-admin (optional).
    DEV_SUPERUSER_PASSWORD  Password for the development super-admin (optional).
                            If omitted, a secure temporary password is generated
                            and printed once to the console.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Allow imports from the project root.
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Load environment before importing app modules.
load_dotenv(dotenv_path=project_root / ".env")

# The async SQLAlchemy engine requires an async driver. If DATABASE_URL uses the
# synchronous psycopg2 scheme, convert it to asyncpg for this script.
_database_url = os.getenv("DATABASE_URL", "")
if _database_url.startswith("postgresql://"):
    os.environ["DATABASE_URL"] = _database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

from app.models.database import _get_engine, _get_session_factory, close_db
from app.seeds import seed_all_default_data


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed default platform and development data.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        default=False,
        help="Seed development tenant, super-admin, chart of accounts, and defaults.",
    )
    args = parser.parse_args()

    if not args.dev:
        print("This seed script currently only supports --dev mode.")
        print("Run with: python scripts/seed_default_data.py --dev")
        return 1

    engine = _get_engine()
    session_factory = _get_session_factory()

    async with session_factory() as db:
        try:
            summary = await seed_all_default_data(db, print_temp_password=True)
            await db.commit()

            print("Seed completed successfully.")
            print(f"  Organization: {summary['organization']['name']} (id={summary['organization']['id']})")
            print(f"  User:         {summary['user']['email']} (id={summary['user']['id']})")
            print(f"  Accounts:     {summary['accounts_count']}")
            print(f"  Budget:       {summary['budget']['name'] if summary['budget'] else 'already existed'}")
            print(f"  Notification settings: {summary['notification_settings_count']}")

            if summary.get("temp_password"):
                print("\nA temporary password was generated and printed above.")
        except Exception as exc:
            await db.rollback()
            print(f"Seed failed: {exc}", file=sys.stderr)
            return 1
        finally:
            await close_db()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
