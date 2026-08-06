# MAREF Database Migrations

Format: `<version>_<description>.sql`
Revert: `<version>_<description>.revert.sql`

Example:
  - `001_create_governance_tables.sql`
  - `001_create_governance_tables.revert.sql`

Usage:
  python scripts/migration.py --upgrade    # Apply pending
  python scripts/migration.py --downgrade  # Rollback last
