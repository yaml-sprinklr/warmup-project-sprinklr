"""
Database connection and instrumentation with Prometheus metrics
"""

import time
import re
from contextlib import contextmanager
from typing import Generator

from sqlmodel import create_engine, Session
from sqlalchemy import event, pool

from app.core.config import settings
from app.core.metrics import (
    db_pool_in_use,
    db_pool_available,
    db_pool_waiters,
    db_pool_wait_seconds,
    db_query_duration_seconds,
    db_queries_total,
    db_query_errors_total,
)

# Create engine with connection pooling
engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),  # type: ignore
    pool_size=10,  # Maximum number of connections to keep in pool
    max_overflow=20,  # Maximum connections that can be created beyond pool_size
    pool_pre_ping=True,  # Verify connections before using them
    pool_recycle=3600,  # Recycle connections after 1 hour
)


# =============================================================================
# CONNECTION POOL METRICS
# =============================================================================


def update_pool_metrics():
    """Update connection pool metrics"""
    pool_status = engine.pool.status()  # type: ignore
    
    # Parse pool status string (format: "Pool size: X  Connections in pool: Y  Current Overflow: Z  Current Checked out connections: W")
    # This is a bit hacky but sqlalchemy doesn't expose these directly
    if hasattr(engine.pool, "size"):
        # Get actual pool statistics
        pool_obj = engine.pool  # type: ignore
        checked_out = pool_obj.checkedout() if hasattr(pool_obj, "checkedout") else 0
        size = pool_obj.size() if hasattr(pool_obj, "size") else 0
        overflow = pool_obj.overflow() if hasattr(pool_obj, "overflow") else 0
        
        in_use = checked_out
        available = size - checked_out + overflow
        
        db_pool_in_use.set(in_use)
        db_pool_available.set(available)


@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Update metrics when connection is created"""
    update_pool_metrics()


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """Track connection checkout timing and update metrics"""
    connection_record.info["checkout_start"] = time.time()
    update_pool_metrics()


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_conn, connection_record):
    """Update metrics when connection is returned to pool"""
    # Track wait time if checkout_start was recorded
    if "checkout_start" in connection_record.info:
        wait_time = time.time() - connection_record.info["checkout_start"]
        db_pool_wait_seconds.observe(wait_time)
        del connection_record.info["checkout_start"]
    
    update_pool_metrics()


# =============================================================================
# QUERY METRICS
# =============================================================================


def _extract_operation_and_table(statement: str) -> tuple[str, str]:
    """
    Extract operation type and table name from SQL statement
    
    Returns:
        Tuple of (operation, table) where operation is select/insert/update/delete
    """
    # Normalize the statement (lowercase, remove extra whitespace)
    normalized = " ".join(statement.lower().split())
    
    # Extract operation
    if normalized.startswith("select"):
        operation = "select"
    elif normalized.startswith("insert"):
        operation = "insert"
    elif normalized.startswith("update"):
        operation = "update"
    elif normalized.startswith("delete"):
        operation = "delete"
    else:
        operation = "other"
    
    # Extract table name (simplified - just get first table mentioned)
    # This regex looks for FROM <table> or INTO <table> or UPDATE <table>
    table_match = re.search(
        r"(?:from|into|update|join)\s+([a-z_][a-z0-9_]*)",
        normalized
    )
    table = table_match.group(1) if table_match else "unknown"
    
    return operation, table


@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Track query start time"""
    context._query_start_time = time.time()


@event.listens_for(engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Record query metrics after execution"""
    if hasattr(context, "_query_start_time"):
        duration = time.time() - context._query_start_time
        operation, table = _extract_operation_and_table(statement)
        
        db_query_duration_seconds.labels(
            operation=operation,
            table=table
        ).observe(duration)
        
        db_queries_total.labels(operation=operation).inc()


@event.listens_for(engine, "handle_error")
def handle_error(exception_context):
    """Track database errors"""
    exception = exception_context.original_exception
    error_type = type(exception).__name__.lower()
    
    # Categorize common error types
    if "timeout" in error_type:
        error_category = "timeout"
    elif "constraint" in error_type or "integrity" in error_type:
        error_category = "constraint"
    elif "connection" in error_type:
        error_category = "connection"
    else:
        error_category = "other"
    
    db_query_errors_total.labels(error_type=error_category).inc()


# =============================================================================
# INSTRUMENTED SESSION CONTEXT MANAGER
# =============================================================================


@contextmanager
def get_instrumented_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions with automatic metric tracking
    
    Usage:
        with get_instrumented_session() as session:
            session.exec(...)
    """
    wait_start = time.time()
    session = Session(engine)
    wait_duration = time.time() - wait_start
    db_pool_wait_seconds.observe(wait_duration)
    
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
        update_pool_metrics()
