"""Default seed data for the PF platform.

This package contains idempotent seed logic for development and default
platform data. It never inserts real personal financial data and respects
PostgreSQL RLS tenant context for all tenant-scoped rows.
"""

from app.seeds.default_data import seed_all_default_data

__all__ = ["seed_all_default_data"]
