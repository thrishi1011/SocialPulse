"""
backend/migrations.py

Lightweight startup migration helper that detects schema evolution on existing databases.
SQLAlchemy's `Base.metadata.create_all` creates new tables, but does not add newly defined
columns to tables that already exist. This helper inspects existing tables and applies
idempotent ALTER TABLE operations compatible with both SQLite and PostgreSQL.
"""
import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("socialpulse.migrations")


def run_startup_migrations(engine: Engine):
    """
    Inspect existing tables for missing columns and apply ALTER TABLE statements.
    Must be called after Base.metadata.create_all(bind=engine).
    """
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())

        with engine.begin() as conn:
            # 1. Check trending_items.topic_id
            if "trending_items" in existing_tables:
                existing_cols = {col["name"] for col in inspector.get_columns("trending_items")}
                if "topic_id" not in existing_cols:
                    logger.info("Applying migration: Adding 'topic_id' to 'trending_items' table...")
                    conn.execute(text("ALTER TABLE trending_items ADD COLUMN topic_id INTEGER;"))
                    try:
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trending_items_topic_id ON trending_items (topic_id);"))
                    except Exception as idx_err:
                        logger.debug(f"Index creation notice: {idx_err}")
                    logger.info("Migration complete: 'topic_id' column added.")

            # 2. Ensure comments table exists
            from backend.models import Comment
            Comment.__table__.create(bind=conn, checkfirst=True)

    except Exception as e:
        logger.error(f"Error during startup migrations: {e}", exc_info=True)
        # Non-fatal error logging so application startup continues if already migrated
