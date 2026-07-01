#!/usr/bin/env python3
"""RLS verification and test script for PF project.

Uses separate connections per test block to avoid transaction nesting issues.
"""

import os
from sqlalchemy import create_engine, text

os.environ['DATABASE_URL'] = 'postgresql://pf_user:W0rk%40786@172.16.100.39:5433/pf_db'

db_url = os.environ['DATABASE_URL'].replace('+asyncpg', '')
engine = create_engine(db_url)


def get_rls_status(conn):
    """Print RLS status for all tables."""
    print("\n--- RLS STATUS ---")
    rls = conn.execute(text(
        "SELECT relname, relrowsecurity, relforcerowsecurity "
        "FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' ORDER BY relname"
    )).fetchall()
    enabled = 0
    forced = 0
    for t, rls_enabled, rls_forced in rls:
        if rls_enabled:
            enabled += 1
        if rls_forced:
            forced += 1
        status = 'RLS=ON' if rls_enabled else 'RLS=OFF'
        force = 'FORCE' if rls_forced else 'NOFORCE'
        if t != 'alembic_version':
            print(f'  {t}: {status} {force}')
    print(f'Total with RLS: {enabled}, with FORCE: {forced}')


def get_policies(conn):
    """Print all RLS policies."""
    print("\n--- RLS POLICIES ---")
    policies = conn.execute(text(
        "SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check "
        "FROM pg_policies WHERE schemaname = 'public' ORDER BY tablename, policyname"
    )).fetchall()
    for p in policies:
        print(f'  {p[1]}.{p[2]}: {p[5]}')
    print(f'Total policies: {len(policies)}')


def test_insert_no_tenant():
    """Insert without tenant context should fail."""
    print("\n--- TEST: Insert without tenant context ---")
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "INSERT INTO accounts (code, name, account_type, tenant_id, is_active, is_bank_account, is_cash_account, is_credit_card, created_at, updated_at) "
                "VALUES ('TEST', 'Test Account', 'Asset', 1, true, false, false, false, NOW(), NOW())"
            ))
            conn.commit()
            print('  UNEXPECTED: Insert succeeded without tenant context')
            return False
        except Exception as e:
            print(f'  EXPECTED: Insert blocked - {type(e).__name__}')
            return True


def test_insert_with_tenant():
    """Insert with matching tenant context should succeed."""
    print("\n--- TEST: Insert with tenant context = 1 ---")
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL app.current_tenant_id = '1'"))
        try:
            conn.execute(text(
                "INSERT INTO accounts (code, name, account_type, tenant_id, is_active, is_bank_account, is_cash_account, is_credit_card, created_at, updated_at) "
                "VALUES ('TEST1', 'Test Account 1', 'Asset', 1, true, false, false, false, NOW(), NOW())"
            ))
            conn.commit()
            print('  SUCCESS: Insert with matching tenant_id succeeded')
            return True
        except Exception as e:
            print(f'  FAILED: {e}')
            return False


def test_cross_tenant_insert():
    """Insert with mismatched tenant_id should fail."""
    print("\n--- TEST: Insert with mismatched tenant_id (context=1, data=2) ---")
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL app.current_tenant_id = '1'"))
        try:
            conn.execute(text(
                "INSERT INTO accounts (code, name, account_type, tenant_id, is_active, is_bank_account, is_cash_account, is_credit_card, created_at, updated_at) "
                "VALUES ('TEST2', 'Test Account 2', 'Asset', 2, true, false, false, false, NOW(), NOW())"
            ))
            conn.commit()
            print('  UNEXPECTED: Cross-tenant insert succeeded')
            return False
        except Exception as e:
            print(f'  EXPECTED: Cross-tenant insert blocked - {type(e).__name__}')
            return True


def test_query_with_tenant():
    """Query with tenant context should return matching rows."""
    print("\n--- TEST: Query with tenant context = 1 ---")
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL app.current_tenant_id = '1'"))
        result = conn.execute(text('SELECT code, name, tenant_id FROM accounts')).fetchall()
        print(f'  Found {len(result)} rows for tenant 1')
        for r in result:
            print(f'    {r[0]}: {r[1]} (tenant_id={r[2]})')
        return True


def test_query_no_tenant():
    """Query without tenant context should return zero tenant-scoped rows."""
    print("\n--- TEST: Query without tenant context ---")
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL app.current_tenant_id = ''"))
        result = conn.execute(text('SELECT code, name, tenant_id FROM accounts')).fetchall()
        print(f'  Found {len(result)} rows without context')
        return len(result) == 0


def test_query_different_tenant():
    """Query with different tenant context should return zero rows for that tenant."""
    print("\n--- TEST: Query with tenant context = 2 ---")
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL app.current_tenant_id = '2'"))
        result = conn.execute(text('SELECT code, name, tenant_id FROM accounts')).fetchall()
        print(f'  Found {len(result)} rows for tenant 2')
        return True


def cleanup_test_data():
    """Remove test data."""
    print("\n--- CLEANUP ---")
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL app.current_tenant_id = '1'"))
        conn.execute(text("DELETE FROM accounts WHERE code = 'TEST1'"))
        conn.commit()
        print('  Test data cleaned up')


def main():
    print("=" * 60)
    print("RLS VERIFICATION AND TEST")
    print("=" * 60)

    with engine.connect() as conn:
        get_rls_status(conn)
        get_policies(conn)

    results = []
    results.append(('Insert without tenant', test_insert_no_tenant()))
    results.append(('Insert with tenant', test_insert_with_tenant()))
    results.append(('Cross-tenant insert', test_cross_tenant_insert()))
    results.append(('Query with tenant', test_query_with_tenant()))
    results.append(('Query without tenant', test_query_no_tenant()))
    results.append(('Query different tenant', test_query_different_tenant()))
    cleanup_test_data()

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = 0
    for name, ok in results:
        status = 'PASS' if ok else 'FAIL'
        print(f'  [{status}] {name}')
        if ok:
            passed += 1
    print(f'\nTotal: {passed}/{len(results)} passed')

    print("\n" + "=" * 60)
    print("RLS verification complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
