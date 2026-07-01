#!/usr/bin/env python3
"""Safe database inspection script for PF project.

Usage:
    python scripts/inspect_db.py

Requires DATABASE_URL environment variable or .env file.
"""
import os
import sys

# Load .env if present
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text, inspect


def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    # Use sync driver for inspection
    sync_url = db_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    inspector = inspect(engine)

    print("=" * 60)
    print("PF DATABASE INSPECTION")
    print("=" * 60)

    with engine.connect() as conn:
        # PostgreSQL version
        version = conn.execute(text("SELECT version()")).scalar()
        print(f"\nPostgreSQL: {version.split()[0]} {version.split()[1]}")

        # Tables
        tables = inspector.get_table_names(schema="public")
        print(f"\n--- TABLES ({len(tables)}) ---")
        for t in sorted(tables):
            cols = inspector.get_columns(t, schema="public")
            fks = inspector.get_foreign_keys(t, schema="public")
            idxs = inspector.get_indexes(t, schema="public")
            pks = inspector.get_pk_constraint(t, schema="public")
            tenant_col = "YES" if any(c["name"] == "tenant_id" for c in cols) else "NO"
            print(f"  {t}: {len(cols)} cols, {len(fks)} FKs, {len(idxs)} idxs, tenant_id={tenant_col}")

        # Enums
        enums = conn.execute(text(
            "SELECT typname FROM pg_type WHERE typtype = 'e' ORDER BY typname"
        )).fetchall()
        print(f"\n--- ENUMS ({len(enums)}) ---")
        for e in enums:
            print(f"  {e[0]}")

        # Alembic
        try:
            v = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            print(f"\n--- ALEMBIC ---")
            print(f"  Current revision: {v}")
        except Exception as ex:
            print(f"\n--- ALEMBIC ---")
            print(f"  ERROR: {ex}")

        # RLS status
        print(f"\n--- RLS STATUS ---")
        rls = conn.execute(text(
            "SELECT relname, relrowsecurity FROM pg_class "
            "WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' "
            "ORDER BY relname"
        )).fetchall()
        rls_enabled = sum(1 for _, enabled in rls if enabled)
        print(f"  Total tables: {len(rls)}")
        print(f"  RLS enabled: {rls_enabled}")
        print(f"  RLS disabled: {len(rls) - rls_enabled}")
        if rls_enabled == 0:
            print("  WARNING: No tables have RLS enabled!")

        # Row counts (safe, no sensitive data exposed)
        print(f"\n--- ROW COUNTS ---")
        for t in sorted(tables):
            try:
                cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                print(f"  {t}: {cnt}")
            except Exception as ex:
                print(f"  {t}: ERROR - {ex}")

    print("\n" + "=" * 60)
    print("Inspection complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
